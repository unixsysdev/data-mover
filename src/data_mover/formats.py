"""Output format discovery and value normalization."""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import decimal
import enum
import json
import math
import pathlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from data_mover.exceptions import ConfigurationError


class ExportFormat(str, enum.Enum):
    """Formats supported by the export pipeline."""

    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    PARQUET = "parquet"
    FEATHER = "feather"

    @classmethod
    def parse(cls, value: ExportFormat | str | None, destination: pathlib.Path) -> ExportFormat:
        """Resolve an explicit format or infer one from a destination suffix."""
        if isinstance(value, cls):
            return value
        if value is not None:
            normalized = value.strip().lower()
            if normalized == "ndjson":
                normalized = cls.JSONL.value
            try:
                return cls(normalized)
            except ValueError as exc:
                supported = ", ".join(item.value for item in cls)
                raise ConfigurationError(
                    f"unsupported output format {value!r}; choose one of: {supported}"
                ) from exc

        suffix = destination.suffix.lower().lstrip(".")
        aliases = {"ndjson": cls.JSONL, "pq": cls.PARQUET, "arrow": cls.FEATHER}
        if suffix in aliases:
            return aliases[suffix]
        try:
            return cls(suffix)
        except ValueError as exc:
            raise ConfigurationError(
                "cannot infer the output format; use --format or a supported file suffix"
            ) from exc


def jsonable(value: Any) -> Any:
    """Convert common database values into deterministic JSON-compatible values."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [jsonable(item) for item in value]
    return str(value)


def csv_value(value: Any) -> str | int | float | bool:
    """Normalize a database value for Python's CSV writer."""
    normalized = jsonable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, (dict, list)):
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if isinstance(normalized, (str, int, float, bool)):
        return normalized
    return str(normalized)
