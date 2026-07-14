from __future__ import annotations

import json
import pathlib

import pytest
import sqlalchemy as sa

from data_mover.cli import main


def _database(tmp_path: pathlib.Path) -> str:
    path = tmp_path / "cli.sqlite"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE items (id INTEGER, name TEXT)"))
        connection.execute(sa.text("INSERT INTO items VALUES (1, 'one'), (2, 'two')"))
    engine.dispose()
    return f"sqlite:///{path}"


def test_cli_table_export(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLI_DATABASE_URL", _database(tmp_path))
    destination = tmp_path / "items.json"
    code = main(
        [
            "export",
            "--url-env",
            "CLI_DATABASE_URL",
            "--table",
            "items",
            str(destination),
        ]
    )
    assert code == 0
    assert "exported 2 rows" in capsys.readouterr().out
    assert json.loads(destination.read_text()) == [
        {"id": 1, "name": "one"},
        {"id": 2, "name": "two"},
    ]


def test_cli_query_file_and_parameters(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLI_DATABASE_URL", _database(tmp_path))
    query = tmp_path / "query.sql"
    query.write_text("SELECT name FROM items WHERE id = :id")
    destination = tmp_path / "item.jsonl"
    assert (
        main(
            [
                "export",
                "--url-env",
                "CLI_DATABASE_URL",
                "--query-file",
                str(query),
                "--param",
                "id=2",
                "--quiet",
                str(destination),
            ]
        )
        == 0
    )
    assert json.loads(destination.read_text()) == {"name": "two"}


@pytest.mark.parametrize(
    "arguments",
    [
        ["--url-env", "MISSING", "--table", "items", "out.csv"],
        ["--url", "sqlite://", "--query", "SELECT 1", "--param", "bad", "out.csv"],
        [
            "--url",
            "sqlite://",
            "--query",
            "SELECT 1",
            "--param",
            "x=1",
            "--param",
            "x=2",
            "out.csv",
        ],
        ["--url", "sqlite://", "--table", "items", "--param", "x=1", "out.csv"],
        ["--url", "sqlite://", "--query", "SELECT 1", "--schema", "main", "out.csv"],
    ],
)
def test_cli_reports_expected_errors(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["export", *arguments]) == 2
    assert "data-mover: error:" in capsys.readouterr().err


def test_cli_reports_missing_query_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "export",
                "--url",
                "sqlite://",
                "--query-file",
                "/does/not/exist.sql",
                "out.csv",
            ]
        )
        == 2
    )
    assert "No such file" in capsys.readouterr().err
