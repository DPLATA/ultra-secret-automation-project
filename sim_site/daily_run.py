"""Daily orchestrator for the MLB Sims static site.

Pipeline (single-pass, idempotent — safe to re-run):
  1. Fetch all completed regular-season games through end of day before target.
  2. Persist the game log to sim_site/data/games_<season>.csv.
  3. Compute team strengths (park-adjusted, season-to-date).
  4. Fetch the target date's scheduled slate.
  5. Poisson-simulate every scheduled game; write per-game JSON.
  6. Render the full static site to sim_site/site/.

Target date defaults to today (the cron's run date). Pass --date YYYY-MM-DD to
override for backfills or manual runs.

The script always exits 0 unless something catastrophic happens — partial
failures in one stage shouldn't prevent the site from rebuilding with whatever
data IS available. Exit code 0 is required so the cron's && chain into the
deploy step only proceeds on clean runs.

Logs go to <repo>/logs/sim_site_run-YYYY-MM-DD_HH-MM-SS.log (matches the
existing YouTube pipeline convention).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sim_site.pipeline import ingest, team_strengths, sim_games, render  # noqa: E402

log = logging.getLogger("sim_site.daily")


def setup_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / f"sim_site_run-{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.log"
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    handlers = [logging.FileHandler(logfile), logging.StreamHandler(sys.stdout)]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)
    return logfile


def run(target: dt.date) -> int:
    log.info("sim_site daily run starting, target=%s", target)

    # 1 + 2. Completed games through yesterday.
    through = target - dt.timedelta(days=1)
    games = ingest.fetch_games(target.year, through=through)
    log.info("ingest: loaded %d completed games through %s", len(games), through)
    csv_path = ingest.save(games, target.year)
    log.info("ingest: wrote %s", csv_path)

    if games.empty:
        log.warning("no completed games yet for season %d; rendering anyway", target.year)
        render.render(target)
        return 0

    # 3. Strengths.
    strengths = team_strengths.compute(games)
    log.info("strengths: %d teams, league_home_neutral=%.3f, league_away=%.3f",
             len(strengths),
             strengths.attrs["league_home_neutral"],
             strengths.attrs["league_away"])

    # 4. Slate.
    slate = ingest.fetch_slate(target)
    log.info("slate: %d games scheduled for %s", len(slate), target)

    # 5. Simulate.
    if not slate.empty:
        results = sim_games.simulate_slate(strengths, slate)
        paths = sim_games.save_games(results)
        log.info("sims: wrote %d game JSONs", len(paths))
    else:
        log.info("no games scheduled for %s; skipping simulation", target)

    # 6. Render.
    render.render(target)
    log.info("render: site written to %s", render.SITE_DIR)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MLB Sims daily pipeline.")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    target = dt.date.fromisoformat(args.date) if args.date else dt.date.today()

    logfile = setup_logging(REPO_ROOT / "logs")
    log.info("logfile=%s", logfile)

    try:
        return run(target)
    except Exception:
        log.exception("sim_site daily run failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
