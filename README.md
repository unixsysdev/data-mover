# Data Mover

[![CI](https://github.com/unixsysdev/data-mover/actions/workflows/ci.yml/badge.svg)](https://github.com/unixsysdev/data-mover/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Reliable, chunked database exports from any SQLAlchemy-supported database to
CSV, JSON, JSON Lines, Parquet, or Feather.

Data Mover is intentionally small: a typed Python API and a credential-safe CLI,
with no web server, no stored connection profiles, and no hidden state.

## Why Data Mover?

- **Database-portable** — works with PostgreSQL, MySQL, SQLite, SQL Server,
  Oracle, and other SQLAlchemy dialects.
- **Memory-bounded** — fetches rows in configurable chunks instead of loading a
  complete result set into memory.
- **Atomic** — writes to a temporary file and moves it into place only after a
  successful export.
- **Safe identifiers** — table exports use SQLAlchemy reflection rather than
  interpolating table names into SQL.
- **Parameterized queries** — query values are passed separately to the driver.
- **Credential-conscious** — the CLI can read a DSN from an environment variable
  and never prints it.
- **Predictable serialization** — dates use ISO 8601, decimals preserve precision,
  UUIDs become strings, and binary values use Base64.

## Installation

```bash
python -m pip install data-mover
```

For Parquet and Feather support:

```bash
python -m pip install 'data-mover[arrow]'
```

Database drivers are deliberately left to the application. For example:

```bash
python -m pip install psycopg[binary]  # PostgreSQL
python -m pip install pymysql          # MySQL
```

## CLI

Export a table using a DSN stored outside shell history:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost/analytics'
data-mover export --url-env DATABASE_URL --table events ./exports/events.parquet
```

Export a parameterized query:

```bash
data-mover export \
  --url-env DATABASE_URL \
  --query-file active-users.sql \
  --param since=2026-01-01 \
  --format jsonl \
  ./exports/active-users.jsonl
```

Useful options:

```text
--table NAME              Export a reflected table
--query SQL               Export a query (may be visible in shell history)
--query-file PATH         Read SQL from a UTF-8 file
--schema NAME             Optional database schema for --table
--param KEY=VALUE         Bind a query parameter; repeat as needed
--format FORMAT           csv, json, jsonl, parquet, or feather
--chunk-size ROWS         Rows fetched per batch (default: 10,000)
--overwrite               Replace an existing destination atomically
```

The output format is inferred from the destination suffix when `--format` is
omitted. Use `.ndjson` as an alias for JSON Lines.

## Python API

```python
from data_mover import DataMover

with DataMover("sqlite:///analytics.db") as mover:
    result = mover.export_table(
        "events",
        "exports/events.csv",
        chunk_size=25_000,
    )

print(f"exported {result.row_count:,} rows to {result.destination}")
```

Parameterized queries use SQLAlchemy's `text()` semantics:

```python
with DataMover.from_env("DATABASE_URL") as mover:
    result = mover.export_query(
        "SELECT id, created_at FROM events WHERE created_at >= :since",
        "exports/recent.jsonl",
        parameters={"since": "2026-01-01"},
        overwrite=True,
    )
```

An existing SQLAlchemy `Engine` can be supplied; Data Mover will not dispose an
engine it does not own.

## Serialization contract

| Python value | CSV | JSON/JSONL/Arrow |
|---|---|---|
| `None` | empty field | `null` |
| date/time | ISO 8601 | ISO 8601 string |
| `Decimal` | exact decimal text | exact decimal text |
| UUID | canonical text | canonical text |
| bytes | Base64 text | Base64 text |
| mapping/sequence | compact JSON | native JSON value |

CSV always includes a header, including for an empty result. JSON is a single
array; JSON Lines emits one object per line. Parquet uses Zstandard compression,
and Feather uses LZ4 compression. Arrow schemas are inferred from the first
non-empty chunk; a column containing only nulls in that chunk is conservatively
encoded as a nullable string column so later chunks remain writable.

## Security model

Data Mover is an export tool, not a SQL sandbox. A raw query has the permissions
of the database account that executes it. Use a dedicated read-only database
role and never expose the CLI as an unauthenticated service. See
[SECURITY.md](SECURITY.md) for operational guidance.

## Development

```bash
python -m pip install -e '.[dev,arrow]'
ruff check .
ruff format --check .
mypy src
pytest
python -m build
python -m twine check dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).
