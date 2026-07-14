from __future__ import annotations

import pathlib

import pytest
import sqlalchemy as sa

from data_mover import DataMover, ExportError, ExportFormat

pa = pytest.importorskip("pyarrow")
ipc = pytest.importorskip("pyarrow.ipc")
parquet = pytest.importorskip("pyarrow.parquet")


def read_arrow(path: pathlib.Path, output_format: ExportFormat):
    if output_format is ExportFormat.PARQUET:
        return parquet.read_table(path)
    with ipc.open_file(path) as reader:
        return reader.read_all()


@pytest.mark.parametrize("output_format", [ExportFormat.PARQUET, ExportFormat.FEATHER])
def test_arrow_export(
    engine: sa.Engine, tmp_path: pathlib.Path, output_format: ExportFormat
) -> None:
    destination = tmp_path / f"events.{output_format.value}"
    with DataMover(engine) as mover:
        result = mover.export_query(
            "SELECT id, name, optional FROM events ORDER BY id",
            destination,
            output_format=output_format,
            chunk_size=1,
        )
    table = read_arrow(destination, output_format)
    assert result.row_count == 2
    assert table.to_pylist() == [
        {"id": 1, "name": "alpha", "optional": None},
        {"id": 2, "name": "bravo", "optional": "present"},
    ]


@pytest.mark.parametrize("output_format", [ExportFormat.PARQUET, ExportFormat.FEATHER])
def test_empty_arrow_export(
    engine: sa.Engine, tmp_path: pathlib.Path, output_format: ExportFormat
) -> None:
    destination = tmp_path / f"empty.{output_format.value}"
    with DataMover(engine) as mover:
        mover.export_query(
            "SELECT id, name FROM events WHERE 0",
            destination,
            output_format=output_format,
        )
    table = read_arrow(destination, output_format)
    assert table.column_names == ["id", "name"]
    assert table.num_rows == 0


@pytest.mark.parametrize("output_format", [ExportFormat.PARQUET, ExportFormat.FEATHER])
def test_incompatible_arrow_chunks_fail_atomically(
    engine: sa.Engine, tmp_path: pathlib.Path, output_format: ExportFormat
) -> None:
    destination = tmp_path / f"mixed.{output_format.value}"
    with (
        DataMover(engine) as mover,
        pytest.raises(ExportError, match="could not serialize"),
    ):
        mover.export_query(
            "SELECT 1 AS value UNION ALL SELECT 'not-an-integer' AS value",
            destination,
            output_format=output_format,
            chunk_size=1,
        )
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.tmp"))
