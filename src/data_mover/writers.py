"""Chunked result writers used by :class:`data_mover.DataMover`."""

from __future__ import annotations

import csv
import json
import pathlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from data_mover.exceptions import OptionalDependencyError
from data_mover.formats import ExportFormat, csv_value, jsonable

Row = Mapping[str, Any]


class RowWriter(Protocol):
    """Internal protocol implemented by format-specific writers."""

    def write(self, rows: Sequence[Row]) -> None: ...

    def close(self) -> None: ...


class _CsvWriter:
    def __init__(self, path: pathlib.Path, columns: Sequence[str]) -> None:
        self._file = path.open("w", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=columns, extrasaction="raise")
        self._writer.writeheader()

    def write(self, rows: Sequence[Row]) -> None:
        self._writer.writerows(
            {key: csv_value(value) for key, value in row.items()} for row in rows
        )

    def close(self) -> None:
        self._file.close()


class _JsonLinesWriter:
    def __init__(self, path: pathlib.Path, columns: Sequence[str]) -> None:
        del columns
        self._file = path.open("w", encoding="utf-8", newline="\n")

    def write(self, rows: Sequence[Row]) -> None:
        for row in rows:
            json.dump(jsonable(row), self._file, ensure_ascii=False, separators=(",", ":"))
            self._file.write("\n")

    def close(self) -> None:
        self._file.close()


class _JsonWriter:
    def __init__(self, path: pathlib.Path, columns: Sequence[str]) -> None:
        del columns
        self._file = path.open("w", encoding="utf-8", newline="\n")
        self._file.write("[")
        self._first = True

    def write(self, rows: Sequence[Row]) -> None:
        for row in rows:
            if not self._first:
                self._file.write(",")
            json.dump(jsonable(row), self._file, ensure_ascii=False, separators=(",", ":"))
            self._first = False

    def close(self) -> None:
        self._file.write("]\n")
        self._file.close()


def _import_pyarrow() -> tuple[Any, Any, Any]:
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.ipc as ipc  # type: ignore[import-untyped]
        import pyarrow.parquet as parquet  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OptionalDependencyError(
            "Parquet and Feather exports require the 'arrow' extra: "
            "python -m pip install 'data-mover[arrow]'"
        ) from exc
    return pa, ipc, parquet


class _ParquetWriter:
    def __init__(self, path: pathlib.Path, columns: Sequence[str]) -> None:
        self._path = path
        self._columns = columns
        self._writer: Any | None = None
        self._schema: Any | None = None
        self._string_columns: set[str] = set()
        self._pa, _, self._parquet = _import_pyarrow()

    def write(self, rows: Sequence[Row]) -> None:
        values = [dict(jsonable(row)) for row in rows]
        if self._schema is None:
            inferred = self._pa.Table.from_pylist(values)
            self._string_columns = {
                field.name for field in inferred.schema if self._pa.types.is_null(field.type)
            }
            self._schema = self._pa.schema(
                [
                    self._pa.field(field.name, self._pa.string())
                    if field.name in self._string_columns
                    else field
                    for field in inferred.schema
                ]
            )
        for row in values:
            for column in self._string_columns:
                if row[column] is not None:
                    row[column] = str(row[column])
        table = self._pa.Table.from_pylist(values, schema=self._schema)
        if self._writer is None:
            self._writer = self._parquet.ParquetWriter(self._path, table.schema, compression="zstd")
        self._writer.write_table(table)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            return
        empty = self._pa.table(
            {column: self._pa.array([], type=self._pa.null()) for column in self._columns}
        )
        self._parquet.write_table(empty, self._path, compression="zstd")


class _FeatherWriter:
    def __init__(self, path: pathlib.Path, columns: Sequence[str]) -> None:
        self._path = path
        self._columns = columns
        self._sink: Any | None = None
        self._writer: Any | None = None
        self._schema: Any | None = None
        self._string_columns: set[str] = set()
        self._pa, self._ipc, _ = _import_pyarrow()
        self._options = self._ipc.IpcWriteOptions(compression="lz4")

    def write(self, rows: Sequence[Row]) -> None:
        values = [dict(jsonable(row)) for row in rows]
        if self._schema is None:
            inferred = self._pa.Table.from_pylist(values)
            self._string_columns = {
                field.name for field in inferred.schema if self._pa.types.is_null(field.type)
            }
            self._schema = self._pa.schema(
                [
                    self._pa.field(field.name, self._pa.string())
                    if field.name in self._string_columns
                    else field
                    for field in inferred.schema
                ]
            )
        for row in values:
            for column in self._string_columns:
                if row[column] is not None:
                    row[column] = str(row[column])
        table = self._pa.Table.from_pylist(values, schema=self._schema)
        if self._writer is None:
            self._sink = self._pa.OSFile(str(self._path), "wb")
            self._writer = self._ipc.new_file(self._sink, table.schema, options=self._options)
        self._writer.write_table(table)

    def close(self) -> None:
        if self._writer is None:
            empty = self._pa.table(
                {column: self._pa.array([], type=self._pa.null()) for column in self._columns}
            )
            self._sink = self._pa.OSFile(str(self._path), "wb")
            self._writer = self._ipc.new_file(self._sink, empty.schema, options=self._options)
        self._writer.close()
        assert self._sink is not None
        self._sink.close()


def create_writer(
    output_format: ExportFormat, path: pathlib.Path, columns: Iterable[str]
) -> RowWriter:
    """Create a writer for one export operation."""
    normalized_columns = tuple(columns)
    if output_format is ExportFormat.CSV:
        return _CsvWriter(path, normalized_columns)
    if output_format is ExportFormat.JSON:
        return _JsonWriter(path, normalized_columns)
    if output_format is ExportFormat.JSONL:
        return _JsonLinesWriter(path, normalized_columns)
    if output_format is ExportFormat.PARQUET:
        return _ParquetWriter(path, normalized_columns)
    return _FeatherWriter(path, normalized_columns)
