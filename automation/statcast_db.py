"""Cloud SQL connection + idempotent UPSERT helpers for the Statcast pitches table.

Reads connection settings from environment variables — source ``secrets/cloudsql.env``
before importing (the cron entry points do this automatically).
"""
from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

REQUIRED_ENV = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_WRITER_USER", "DB_WRITER_PASSWORD")
PRIMARY_KEY = ("game_pk", "at_bat_number", "pitch_number")


def make_engine() -> Engine:
    missing = [k for k in REQUIRED_ENV if k not in os.environ]
    if missing:
        raise RuntimeError(
            f"Missing env vars: {missing}. Source secrets/cloudsql.env before running."
        )
    url = (
        "postgresql+psycopg2://"
        f"{os.environ['DB_WRITER_USER']}:{os.environ['DB_WRITER_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}"
        f"/{os.environ['DB_NAME']}"
    )
    return create_engine(url, pool_pre_ping=True)


def upsert_pitches(engine: Engine, df: pd.DataFrame, chunk_size: int = 1000) -> int:
    """Insert df rows into pitches; skip rows that conflict on the composite PK.

    Returns the number of newly-inserted rows (existing rows are silently skipped,
    which is what we want for re-runs and overlapping pulls).
    """
    if df.empty:
        return 0

    meta = MetaData()
    pitches = Table("pitches", meta, autoload_with=engine)

    # psycopg2 chokes on pandas pd.NA; coerce everything to object + map NA → None.
    df = df.astype(object).where(pd.notna(df), None)
    records = df.to_dict("records")

    inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            stmt = insert(pitches).values(chunk).on_conflict_do_nothing(
                index_elements=list(PRIMARY_KEY)
            )
            result = conn.execute(stmt)
            inserted += result.rowcount or 0
    return inserted
