from __future__ import annotations

import datetime as dt
import decimal
import pathlib

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine


@pytest.fixture
def engine(tmp_path: pathlib.Path) -> Engine:
    database = tmp_path / "source.sqlite"
    result = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    events = sa.Table(
        "events",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("amount", sa.Numeric(10, 2)),
        sa.Column("created_at", sa.DateTime),
        sa.Column("payload", sa.LargeBinary),
        sa.Column("optional", sa.String),
    )
    metadata.create_all(result)
    with result.begin() as connection:
        connection.execute(
            events.insert(),
            [
                {
                    "id": 1,
                    "name": "alpha",
                    "amount": decimal.Decimal("12.30"),
                    "created_at": dt.datetime(2026, 1, 2, 3, 4, 5),
                    "payload": b"hello",
                    "optional": None,
                },
                {
                    "id": 2,
                    "name": "bravo",
                    "amount": decimal.Decimal("0.01"),
                    "created_at": dt.datetime(2026, 2, 3, 4, 5, 6),
                    "payload": b"world",
                    "optional": "present",
                },
            ],
        )
    yield result
    result.dispose()
