"""Daily incremental Statcast pull — cron entry point.

Pulls a single day of pitches from baseballsavant via pybaseball and UPSERTs into
Cloud SQL. Defaults to yesterday; pass an ISO date to backfill a specific day.

    python -m automation.statcast_pull             # yesterday
    python -m automation.statcast_pull 2026-05-20  # specific date

Statcast typically lags 3-4 hours behind the final out; West Coast games are
usually official by ~5am ET, so schedule the cron after that.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pybaseball  # noqa: E402

from automation.statcast_db import make_engine, upsert_pitches  # noqa: E402


def pull_one_day(date: dt.date) -> tuple[int, int]:
    """Returns (rows_fetched, rows_inserted)."""
    pybaseball.cache.enable()
    df = pybaseball.statcast(
        start_dt=date.isoformat(),
        end_dt=date.isoformat(),
        verbose=False,
    )
    if df.empty:
        return 0, 0
    engine = make_engine()
    return len(df), upsert_pitches(engine, df)


def main() -> int:
    if len(sys.argv) > 1:
        target = dt.date.fromisoformat(sys.argv[1])
    else:
        target = dt.date.today() - dt.timedelta(days=1)

    print(f"[statcast_pull] target date: {target}", flush=True)
    fetched, inserted = pull_one_day(target)
    print(f"[statcast_pull] fetched={fetched} inserted={inserted}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
