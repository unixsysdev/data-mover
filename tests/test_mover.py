from __future__ import annotations

import csv
import json
import pathlib

import pytest
import sqlalchemy as sa

from data_mover import (
    ConfigurationError,
    DataMover,
    DestinationExistsError,
    ExportError,
    ExportFormat,
)


def test_export_table_to_csv(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    destination = tmp_path / "nested" / "events.csv"
    with DataMover(engine) as mover:
        result = mover.export_table("events", destination, chunk_size=1)

    assert result.row_count == 2
    assert result.output_format is ExportFormat.CSV
    assert result.columns == ("id", "name", "amount", "created_at", "payload", "optional")
    with destination.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0] == {
        "id": "1",
        "name": "alpha",
        "amount": "12.30",
        "created_at": "2026-01-02T03:04:05",
        "payload": "aGVsbG8=",
        "optional": "",
    }


def test_export_parameterized_query_to_jsonl(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    destination = tmp_path / "events.ndjson"
    with DataMover(engine) as mover:
        result = mover.export_query(
            "SELECT id, name FROM events WHERE id >= :minimum ORDER BY id",
            destination,
            parameters={"minimum": 2},
        )
    assert result.row_count == 1
    assert json.loads(destination.read_text().strip()) == {"id": 2, "name": "bravo"}


def test_export_json_is_valid_array(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    destination = tmp_path / "events.json"
    with DataMover(engine) as mover:
        mover.export_query("SELECT id FROM events ORDER BY id", destination, chunk_size=1)
    assert json.loads(destination.read_text()) == [{"id": 1}, {"id": 2}]


def test_empty_exports_remain_valid(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    json_path = tmp_path / "empty.json"
    csv_path = tmp_path / "empty.csv"
    with DataMover(engine) as mover:
        json_result = mover.export_query("SELECT id FROM events WHERE 0", json_path)
        csv_result = mover.export_query("SELECT id FROM events WHERE 0", csv_path)
    assert json_result.row_count == csv_result.row_count == 0
    assert json.loads(json_path.read_text()) == []
    assert csv_path.read_text() == "id\n"


def test_existing_destination_requires_overwrite(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    destination = tmp_path / "events.csv"
    destination.write_text("keep me")
    with DataMover(engine) as mover:
        with pytest.raises(DestinationExistsError):
            mover.export_table("events", destination)
        mover.export_table("events", destination, overwrite=True)
    assert destination.read_text() != "keep me"


def test_failed_query_does_not_leave_partial_file(
    engine: sa.Engine, tmp_path: pathlib.Path
) -> None:
    destination = tmp_path / "failed.csv"
    with DataMover(engine) as mover, pytest.raises(ExportError, match="database query failed"):
        mover.export_query("SELECT missing FROM events", destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_duplicate_columns_are_rejected(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    with DataMover(engine) as mover, pytest.raises(ExportError, match="unique names"):
        mover.export_query("SELECT 1 AS value, 2 AS value", tmp_path / "duplicate.json")


def test_invalid_requests_are_rejected(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    mover = DataMover(engine)
    with pytest.raises(ConfigurationError, match="table name"):
        mover.export_table("", tmp_path / "x.csv")
    with pytest.raises(ConfigurationError, match="query cannot"):
        mover.export_query("", tmp_path / "x.csv")
    with pytest.raises(ConfigurationError, match="chunk_size"):
        mover.export_query("SELECT 1", tmp_path / "x.csv", chunk_size=0)
    with pytest.raises(ConfigurationError, match="directory"):
        mover.export_query("SELECT 1", tmp_path)


def test_destination_setup_error_is_wrapped(
    engine: sa.Engine, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "nested" / "events.csv"

    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("sensitive operating-system detail")

    monkeypatch.setattr(pathlib.Path, "mkdir", fail)
    with DataMover(engine) as mover, pytest.raises(ExportError, match="prepare export"):
        mover.export_table("events", destination)


def test_reflection_error_is_sanitized(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    with DataMover(engine) as mover, pytest.raises(ExportError, match="could not reflect"):
        mover.export_table("does_not_exist", tmp_path / "x.csv")


def test_owned_and_external_engine_lifecycle(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    external = DataMover(engine)
    external.close()
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT 1")) == 1
    with pytest.raises(ConfigurationError, match="closed"):
        external.export_query("SELECT 1", tmp_path / "x.csv")

    owned = DataMover(f"sqlite:///{tmp_path / 'owned.sqlite'}")
    assert owned.engine is not None
    owned.close()
    with pytest.raises(ConfigurationError, match="closed"):
        _ = owned.engine


def test_connect_args_rejected_for_external_engine(engine: sa.Engine) -> None:
    with pytest.raises(ConfigurationError, match="connect_args"):
        DataMover(engine, connect_args={"timeout": 1})


def test_empty_source_and_missing_environment_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        DataMover("")
    monkeypatch.delenv("MISSING_DATABASE_URL", raising=False)
    with pytest.raises(ConfigurationError, match="is not set"):
        DataMover.from_env("MISSING_DATABASE_URL")
    with pytest.raises(ConfigurationError, match="name cannot be empty"):
        DataMover.from_env("")


def test_invalid_driver_error_is_sanitized() -> None:
    with pytest.raises(ConfigurationError, match="installed driver"):
        DataMover("unknown+dialect://user:secret@example.invalid/database")


def test_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'env.sqlite'}")
    with DataMover.from_env("TEST_DATABASE_URL") as mover:
        assert mover.engine.dialect.name == "sqlite"
