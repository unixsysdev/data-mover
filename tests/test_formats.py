from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import pathlib
import uuid

import pytest

from data_mover import ConfigurationError, ExportFormat
from data_mover.formats import csv_value, jsonable


@dataclasses.dataclass
class Example:
    value: int


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("out.csv", ExportFormat.CSV),
        ("out.json", ExportFormat.JSON),
        ("out.jsonl", ExportFormat.JSONL),
        ("out.ndjson", ExportFormat.JSONL),
        ("out.parquet", ExportFormat.PARQUET),
        ("out.pq", ExportFormat.PARQUET),
        ("out.feather", ExportFormat.FEATHER),
        ("out.arrow", ExportFormat.FEATHER),
    ],
)
def test_format_inference(path: str, expected: ExportFormat) -> None:
    assert ExportFormat.parse(None, pathlib.Path(path)) is expected


def test_explicit_ndjson_alias() -> None:
    assert ExportFormat.parse("ndjson", pathlib.Path("ignored")) is ExportFormat.JSONL


def test_unknown_format_is_actionable() -> None:
    with pytest.raises(ConfigurationError, match="unsupported output format"):
        ExportFormat.parse("xlsx", pathlib.Path("out.xlsx"))


def test_unknown_suffix_requires_explicit_format() -> None:
    with pytest.raises(ConfigurationError, match="cannot infer"):
        ExportFormat.parse(None, pathlib.Path("out.data"))


def test_jsonable_normalizes_database_values() -> None:
    identifier = uuid.UUID("12345678-1234-5678-1234-567812345678")
    value = {
        "decimal": decimal.Decimal("10.20"),
        "date": dt.date(2026, 1, 2),
        "time": dt.time(3, 4, 5),
        "datetime": dt.datetime(2026, 1, 2, 3, 4, 5),
        "duration": dt.timedelta(seconds=2.5),
        "uuid": identifier,
        "bytes": memoryview(b"hello"),
        "dataclass": Example(3),
        "tuple": (1, 2),
        "nan": float("nan"),
        "positive_infinity": float("inf"),
        "negative_infinity": float("-inf"),
    }
    assert jsonable(value) == {
        "decimal": "10.20",
        "date": "2026-01-02",
        "time": "03:04:05",
        "datetime": "2026-01-02T03:04:05",
        "duration": 2.5,
        "uuid": str(identifier),
        "bytes": "aGVsbG8=",
        "dataclass": {"value": 3},
        "tuple": [1, 2],
        "nan": "nan",
        "positive_infinity": "inf",
        "negative_infinity": "-inf",
    }


def test_csv_value_uses_compact_json_for_structures() -> None:
    assert csv_value(None) == ""
    assert csv_value({"nested": [1, 2]}) == '{"nested":[1,2]}'
