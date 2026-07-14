"""High-level database export service."""

from __future__ import annotations

import contextlib
import dataclasses
import os
import pathlib
import time
import uuid
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import URL, Engine
from sqlalchemy.sql.elements import TextClause

from data_mover.exceptions import (
    ConfigurationError,
    DataMoverError,
    DestinationExistsError,
    ExportError,
)
from data_mover.formats import ExportFormat
from data_mover.writers import RowWriter, create_writer


@dataclasses.dataclass(frozen=True, slots=True)
class ExportResult:
    """Summary returned after a successful export."""

    destination: pathlib.Path
    output_format: ExportFormat
    row_count: int
    columns: tuple[str, ...]
    elapsed_seconds: float


class DataMover:
    """Export SQLAlchemy query results into portable files.

    The class owns engines created from a URL and disposes them on ``close``. An
    externally supplied engine remains owned by its caller.
    """

    def __init__(
        self,
        source: str | URL | Engine,
        *,
        connect_args: Mapping[str, Any] | None = None,
    ) -> None:
        if isinstance(source, Engine):
            if connect_args:
                raise ConfigurationError("connect_args cannot be used with an existing Engine")
            self._engine = source
            self._owns_engine = False
        else:
            if not str(source).strip():
                raise ConfigurationError("database URL cannot be empty")
            try:
                self._engine = sa.create_engine(
                    source,
                    connect_args=dict(connect_args or {}),
                    hide_parameters=True,
                    pool_pre_ping=True,
                )
            except (sa.exc.SQLAlchemyError, ImportError) as exc:
                raise ConfigurationError(
                    "could not create the database engine; check the URL and installed driver"
                ) from exc
            self._owns_engine = True
        self._closed = False

    @classmethod
    def from_env(cls, variable: str = "DATABASE_URL") -> DataMover:
        """Create a mover from a database URL stored in an environment variable."""
        if not variable or not variable.strip():
            raise ConfigurationError("environment variable name cannot be empty")
        value = os.environ.get(variable)
        if not value:
            raise ConfigurationError(f"environment variable {variable!r} is not set")
        return cls(value)

    @property
    def engine(self) -> Engine:
        """The underlying SQLAlchemy engine."""
        self._ensure_open()
        return self._engine

    def close(self) -> None:
        """Release resources owned by this instance."""
        if not self._closed and self._owns_engine:
            self._engine.dispose()
        self._closed = True

    def __enter__(self) -> DataMover:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def export_table(
        self,
        table: str,
        destination: str | os.PathLike[str],
        *,
        schema: str | None = None,
        output_format: ExportFormat | str | None = None,
        chunk_size: int = 10_000,
        overwrite: bool = False,
    ) -> ExportResult:
        """Reflect and export a table without interpolating its identifier."""
        self._ensure_open()
        if not table or not table.strip():
            raise ConfigurationError("table name cannot be empty")
        metadata = sa.MetaData()
        try:
            reflected = sa.Table(table, metadata, schema=schema, autoload_with=self._engine)
        except sa.exc.SQLAlchemyError as exc:
            raise ExportError(f"could not reflect table {table!r}") from exc
        return self._export(
            sa.select(reflected),
            destination,
            parameters=None,
            output_format=output_format,
            chunk_size=chunk_size,
            overwrite=overwrite,
        )

    def export_query(
        self,
        query: str | TextClause,
        destination: str | os.PathLike[str],
        *,
        parameters: Mapping[str, Any] | None = None,
        output_format: ExportFormat | str | None = None,
        chunk_size: int = 10_000,
        overwrite: bool = False,
    ) -> ExportResult:
        """Export a parameterized SQL query.

        The query is trusted input. Data Mover does not attempt to parse or sandbox
        SQL; use a read-only database account.
        """
        self._ensure_open()
        statement = sa.text(query) if isinstance(query, str) else query
        if not str(statement).strip():
            raise ConfigurationError("query cannot be empty")
        return self._export(
            statement,
            destination,
            parameters=parameters,
            output_format=output_format,
            chunk_size=chunk_size,
            overwrite=overwrite,
        )

    def _export(
        self,
        statement: Any,
        destination: str | os.PathLike[str],
        *,
        parameters: Mapping[str, Any] | None,
        output_format: ExportFormat | str | None,
        chunk_size: int,
        overwrite: bool,
    ) -> ExportResult:
        if chunk_size < 1:
            raise ConfigurationError("chunk_size must be greater than zero")

        output = pathlib.Path(destination).expanduser()
        try:
            if output.exists() and output.is_dir():
                raise ConfigurationError(f"destination is a directory: {output}")
            if output.exists() and not overwrite:
                raise DestinationExistsError(
                    f"destination already exists: {output}; pass overwrite=True to replace it"
                )
            output.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"could not prepare export destination {output}") from exc
        resolved_format = ExportFormat.parse(output_format, output)
        temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")

        started = time.monotonic()
        writer: RowWriter | None = None
        row_count = 0
        columns: tuple[str, ...] = ()
        try:
            with self._engine.connect() as connection:
                result = connection.execution_options(stream_results=True).execute(
                    statement, dict(parameters or {})
                )
                columns = tuple(str(key) for key in result.keys())  # noqa: SIM118
                if len(columns) != len(set(columns)):
                    raise ExportError(
                        "query result columns must have unique names; add SQL aliases"
                    )
                writer = create_writer(resolved_format, temporary, columns)
                mappings = result.mappings()
                while batch := mappings.fetchmany(chunk_size):
                    rows = [dict(row) for row in batch]
                    writer.write(rows)
                    row_count += len(rows)
            writer.close()
            writer = None
            temporary.replace(output)
        except DataMoverError:
            raise
        except sa.exc.SQLAlchemyError as exc:
            raise ExportError(
                "database query failed; inspect the chained exception locally"
            ) from exc
        except OSError as exc:
            raise ExportError(f"could not write export to {output}") from exc
        except Exception as exc:
            raise ExportError("could not serialize the database result") from exc
        finally:
            if writer is not None:
                with contextlib.suppress(Exception):
                    writer.close()
            temporary.unlink(missing_ok=True)

        return ExportResult(
            destination=output,
            output_format=resolved_format,
            row_count=row_count,
            columns=columns,
            elapsed_seconds=time.monotonic() - started,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise ConfigurationError("DataMover is closed")
