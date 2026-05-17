"""Library functions for fetching a pitcher's recent Statcast data.

Originally an interactive script — kept as a library module so daily_run.py
can call `process_pitcher()`. The previous interactive flow is preserved
under `__main__` for one-off manual runs.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from pybaseball import playerid_lookup, statcast_pitcher

from constants import MLB_TEAMS_INFO
from video_scraper.downloader import ClipRecord, download_pitcher_videos

log = logging.getLogger(__name__)


def get_team_id_by_brief_name(brief_name: str) -> Optional[int]:
    for team in MLB_TEAMS_INFO:
        if team["Brief Name"] == brief_name:
            return team["Team ID"]
    return None


def lookup_mlbam_id(player_name: str) -> int:
    """Resolve a Baseball Savant player name to an MLBAM ID.

    Supports names with middle parts: first token is the first name, last
    token is the last name. Pitcher names with multi-word surnames (e.g.
    'De La Rosa') will need a manual override — not currently supported.
    """
    tokens = player_name.split()
    if len(tokens) < 2:
        raise ValueError(f"player name must have at least first and last: {player_name!r}")
    first, last = tokens[0], tokens[-1]
    info = playerid_lookup(last, first)
    if info.empty:
        raise LookupError(f"no MLBAM id for {player_name!r}")
    return int(info["key_mlbam"].iloc[0])


def get_pitching_stats(player_name: str, start_date: str, end_date: str):
    """Return (statcast DataFrame, [(game_pk, game_date), ...]) for the player/range.

    game_date is normalized to "YYYY-MM-DD" so callers can use it directly in
    filenames and metadata.
    """
    mlbam_id = lookup_mlbam_id(player_name)
    stats = statcast_pitcher(start_date, end_date, mlbam_id)
    games = (
        stats[["game_pk", "game_date"]]
        .drop_duplicates(subset=["game_pk"])
        .assign(game_date=lambda df: df["game_date"].astype(str).str[:10])
    )
    return stats, [(int(row.game_pk), row.game_date) for row in games.itertuples()]


def process_pitcher(
    name: str,
    team_brief_name: str,
    lookback_days: int,
    videos_dir: str,
    seen_play_id=None,
    on_clip_recorded=None,
    skip_portrait_for_ball: bool = False,
) -> list[ClipRecord]:
    """Fetch + download every new clip for one pitcher.

    Returns the list of `ClipRecord`s for clips that were newly downloaded
    this run. Plays already in the state store are skipped via `seen_play_id`.
    `on_clip_recorded` is invoked per clip immediately after download so the
    caller can commit state incrementally.
    """
    team_id = get_team_id_by_brief_name(team_brief_name)
    if team_id is None:
        raise ValueError(f"unknown team Brief Name: {team_brief_name!r}")

    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    stats, games = get_pitching_stats(
        name, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    )
    log.info("pitcher=%s games_in_window=%d", name, len(games))

    pitcher_video_folder = os.path.join(videos_dir, name)
    os.makedirs(pitcher_video_folder, exist_ok=True)

    new_clips: list[ClipRecord] = []
    for game_pk, game_date in games:
        try:
            new_clips.extend(
                download_pitcher_videos(
                    int(game_pk),
                    name,
                    pitcher_video_folder,
                    team_id,
                    game_date=game_date,
                    seen_play_id=seen_play_id,
                    on_clip_recorded=on_clip_recorded,
                    skip_portrait_for_ball=skip_portrait_for_ball,
                )
            )
        except Exception:
            log.exception(
                "download failed for pitcher=%s game_pk=%s date=%s",
                name, game_pk, game_date,
            )
    return new_clips


if __name__ == "__main__":
    # Legacy interactive entry point — useful for ad-hoc runs against
    # a single pitcher without touching pitchers.yaml.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    name = input("Enter the player's full name (e.g., Marcus Stroman): ")
    team = input("Enter the player's team Brief Name (e.g., Cubs): ")
    process_pitcher(name, team, lookback_days=7, videos_dir="videos")
