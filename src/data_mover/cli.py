"""Command-line interface for Data Mover."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from collections.abc import Sequence

from data_mover._version import __version__
from data_mover.exceptions import ConfigurationError, DataMoverError
from data_mover.formats import ExportFormat
from data_mover.mover import DataMover


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data-mover",
        description="Export a database table or query to a portable data file.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export", help="export a table or query")

    source = export.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="SQLAlchemy database URL; prefer --url-env")
    source.add_argument(
        "--url-env",
        metavar="VARIABLE",
        help="name of an environment variable containing the database URL",
    )

    selection = export.add_mutually_exclusive_group(required=True)
    selection.add_argument("--table", help="table to reflect and export")
    selection.add_argument("--query", help="SQL query; prefer --query-file")
    selection.add_argument("--query-file", type=pathlib.Path, help="UTF-8 file containing SQL")

    export.add_argument("destination", type=pathlib.Path)
    export.add_argument("--schema", help="schema used with --table")
    export.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="query parameter; repeat for multiple values",
    )
    export.add_argument("--format", choices=[item.value for item in ExportFormat])
    export.add_argument("--chunk-size", type=int, default=10_000)
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--quiet", action="store_true")
    return parser


def _parameters(values: Sequence[str]) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise ConfigurationError(f"invalid parameter {value!r}; expected KEY=VALUE")
        if key in parameters:
            raise ConfigurationError(f"duplicate query parameter: {key}")
        parameters[key] = item
    return parameters


def _database_url(args: argparse.Namespace) -> str:
    if args.url:
        return str(args.url)
    value = os.environ.get(args.url_env)
    if not value:
        raise ConfigurationError(f"environment variable {args.url_env!r} is not set")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    args = _parser().parse_args(argv)
    try:
        url = _database_url(args)
        parameters = _parameters(args.param)
        with DataMover(url) as mover:
            common = {
                "output_format": args.format,
                "chunk_size": args.chunk_size,
                "overwrite": args.overwrite,
            }
            if args.table:
                if parameters:
                    raise ConfigurationError("--param can only be used with a query")
                result = mover.export_table(
                    args.table, args.destination, schema=args.schema, **common
                )
            else:
                if args.schema:
                    raise ConfigurationError("--schema can only be used with --table")
                query = (
                    args.query_file.read_text(encoding="utf-8") if args.query_file else args.query
                )
                result = mover.export_query(
                    query, args.destination, parameters=parameters, **common
                )
        if not args.quiet:
            print(
                f"exported {result.row_count} rows to {result.destination} "
                f"as {result.output_format.value} in {result.elapsed_seconds:.3f}s"
            )
        return 0
    except (DataMoverError, OSError) as exc:
        print(f"data-mover: error: {exc}", file=sys.stderr)
        return 2


def entrypoint() -> None:
    """Console-script entry point."""
    raise SystemExit(main())
