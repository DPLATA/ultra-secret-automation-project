"""Add queries log table + grants for mlbsims_llm role.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-27

The queries table logs every user question the embedded LLM service answers.
Used for (1) rate-limit lookups (per ip_hash, last 24h) and (2) content-roadmap
analysis ("what are people asking about?").

The mlbsims_llm Postgres role is created in terraform (random password stored
in tfstate). This migration only grants it the permissions it needs.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CREATE_TABLE_SQL = """
CREATE TABLE queries (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_hash       TEXT,
    question      TEXT NOT NULL,
    generated_sql TEXT,
    rows_returned INTEGER,
    status        TEXT NOT NULL,
    latency_ms    INTEGER,
    model         TEXT,
    cached        BOOLEAN NOT NULL DEFAULT FALSE
);

-- Hot path for rate limiting: count WHERE ip_hash = ? AND ts > now() - 24h
CREATE INDEX idx_queries_ip_ts ON queries (ip_hash, ts DESC);

-- For weekly content-roadmap queries
CREATE INDEX idx_queries_ts ON queries (ts DESC);

-- For debugging: filter by failure status
CREATE INDEX idx_queries_status ON queries (status) WHERE status != 'ok';
"""


GRANTS_SQL = """
-- mlbsims_llm needs:
--   SELECT on pitches (to run user queries)
--   INSERT + SELECT on queries (write logs + read for rate limiting)
--   USAGE + SELECT on the queries id sequence (BIGSERIAL needs this)
GRANT USAGE ON SCHEMA public TO mlbsims_llm;
GRANT SELECT ON pitches TO mlbsims_llm;
GRANT SELECT, INSERT ON queries TO mlbsims_llm;
GRANT USAGE, SELECT ON SEQUENCE queries_id_seq TO mlbsims_llm;

-- Also let mlbsims_reader peek at the queries log (for ad-hoc analysis from DBeaver)
GRANT SELECT ON queries TO mlbsims_reader;
"""


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS queries;")
