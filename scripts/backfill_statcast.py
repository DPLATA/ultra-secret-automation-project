"""One-off Statcast backfill, chunked weekly to stay within e2-micro RAM.

Iterates 7-day windows from --start to --end, fetches Statcast via pybaseball,
UPSERTs into Cloud SQL. Safe to re-run — conflicts on the composite PK are
silently skipped.

    python scripts/backfill_statcast.py                       # full 2026 season-to-date
    python scripts/backfill_statcast.py --start 2026-05-01 --end 2026-05-15

A full season backfill takes ~60-90 min. Run in tmux/screen on the e2-micro:

    tmux new -s backfill
    set -a; source secrets/cloudsql.env; set +a
    .venv/bin/python scripts/backfill_statcast.py
    # detach: Ctrl-b d   |   reattach: tmux attach -t backfill
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pybaseball  # noqa: E402

from automation.statcast_db import make_engine, upsert_pitches  # noqa: E402

SEASON_START = dt.date(2026, 3, 27)  # 2026 MLB Opening Day


def weekly_chunks(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        chunk_end = min(cur + dt.timedelta(days=6), end)
        yield cur, chunk_end
        cur = chunk_end + dt.timedelta(days=1)


def fetch_with_retry(start: dt.date, end: dt.date, max_attempts: int = 2):
    """pybaseball occasionally fails on transient HTTP errors — one retry is enough."""
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return pybaseball.statcast(
                start_dt=start.isoformat(),
                end_dt=end.isoformat(),
                verbose=False,
            )
        except Exception as e:
            last_err = e
            print(f"  WARN: pybaseball failed (attempt {attempt}/{max_attempts}): {e}", flush=True)
            time.sleep(10)
    raise last_err  # type: ignore[misc]


def backfill(start: dt.date, end: dt.date) -> None:
    pybaseball.cache.enable()
    engine = make_engine()

    chunks = list(weekly_chunks(start, end))
    total_fetched = 0
    total_inserted = 0
    t_start = time.time()

    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        t0 = time.time()
        print(f"[{i}/{len(chunks)}] {chunk_start} → {chunk_end}", flush=True)
        df = fetch_with_retry(chunk_start, chunk_end)
        rows = len(df)
        inserted = upsert_pitches(engine, df) if rows else 0
        total_fetched += rows
        total_inserted += inserted
        print(f"  fetched={rows} new={inserted} ({time.time() - t0:.1f}s)", flush=True)

    elapsed_min = (time.time() - t_start) / 60
    print(
        f"\nDone. fetched={total_fetched} inserted={total_inserted} "
        f"in {elapsed_min:.1f} min"
    )


def main() -> int:
    today = dt.date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        type=lambda s: dt.date.fromisoformat(s),
        default=SEASON_START,
        help="Inclusive start date (default: 2026 Opening Day)",
    )
    parser.add_argument(
        "--end",
        type=lambda s: dt.date.fromisoformat(s),
        default=today,
        help="Inclusive end date (default: today)",
    )
    args = parser.parse_args()

    if args.end < args.start:
        print("--end must be on or after --start", file=sys.stderr)
        return 2

    print(f"backfill range: {args.start} → {args.end}")
    backfill(args.start, args.end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
