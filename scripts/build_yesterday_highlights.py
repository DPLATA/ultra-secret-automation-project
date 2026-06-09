"""Build MLB highlight reels for yesterday's slate.

For each Final game on the target date, builds one chronological game reel
(every highlight-tagged clip from MLB's content endpoint), then builds one
league-wide pitcher reel from every pitching-tagged clip across the slate.
Outputs land under {compilations_dir}/highlights/{date}/.

Standalone — does NOT touch daily_run.py; safe to run mid-day without
re-fetching the pitcher slate.

Usage:
    .venv/bin/python scripts/build_yesterday_highlights.py
    .venv/bin/python scripts/build_yesterday_highlights.py --date 2026-05-24
    .venv/bin/python scripts/build_yesterday_highlights.py --skip-pitcher-reel
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from automation import config as config_mod, highlights_compiler  # noqa: E402
from video_scraper.mlb_content import fetch_highlights, fetch_schedule  # noqa: E402

log = logging.getLogger("build_yesterday_highlights")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build per-game highlight reels + daily pitcher reel."
    )
    parser.add_argument(
        "--date", default=None,
        help="Target date YYYY-MM-DD (default: yesterday).",
    )
    parser.add_argument(
        "--skip-pitcher-reel", action="store_true",
        help="Build per-game reels only, skip the daily pitcher reel.",
    )
    parser.add_argument(
        "--game-min-clips", type=int, default=3,
        help="Skip game reels with fewer than this many highlights (default 3).",
    )
    parser.add_argument(
        "--pitcher-min-clips", type=int, default=5,
        help="Skip pitcher reel if league-wide pitching clips < this (default 5).",
    )
    args = parser.parse_args()

    target_date = args.date or (date.today() - timedelta(days=1)).isoformat()

    cfg = config_mod.load(None)
    cfg.paths.ensure()

    log.info("fetching schedule for %s", target_date)
    games = fetch_schedule(target_date)
    if not games:
        log.warning("no Final games on %s — nothing to build", target_date)
        return 0
    log.info("found %d Final games", len(games))

    highlights_by_game: dict[int, list] = {}
    built_game_reels = []
    for game in games:
        try:
            highlights = fetch_highlights(game.game_pk)
            highlights_by_game[game.game_pk] = highlights
            log.info(
                "game_pk=%s %s: %d highlight clips",
                game.game_pk, game.slug, len(highlights),
            )
            built = highlights_compiler.build_game_reel(
                game=game,
                highlights=highlights,
                compilations_dir=cfg.paths.compilations_dir,
                videos_dir=cfg.paths.videos_dir,
                min_clips=args.game_min_clips,
            )
            if built is not None:
                built_game_reels.append(built)
        except Exception:
            log.exception(
                "game reel failed for game_pk=%s %s; continuing",
                game.game_pk, game.slug,
            )

    pitcher_reel = None
    if not args.skip_pitcher_reel:
        try:
            pitcher_reel = highlights_compiler.build_pitcher_reel(
                date=target_date,
                highlights_by_game=highlights_by_game,
                compilations_dir=cfg.paths.compilations_dir,
                videos_dir=cfg.paths.videos_dir,
                min_clips=args.pitcher_min_clips,
            )
        except Exception:
            log.exception("pitcher reel build failed")

    print()
    print("=" * 60)
    print(f"Date: {target_date}")
    print(f"Games: {len(games)} | Game reels built: {len(built_game_reels)}")
    for r in built_game_reels:
        print(f"  {r.output_path}  ({len(r.highlight_ids)} clips)")
    if pitcher_reel is not None:
        print(f"Pitcher reel: {pitcher_reel.output_path}  "
              f"({len(pitcher_reel.highlight_ids)} clips)")
    elif not args.skip_pitcher_reel:
        print("Pitcher reel: skipped (not enough pitching clips or build failed)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
