"""Download a pitcher's clips for a single game from baseballsavant.

Idempotent: skips work the state store has already seen, and skips downloads
where the on-disk file already exists (so a crash mid-run loses nothing).
Per-clip results are emitted via an optional `on_clip_recorded` callback
so the caller can persist state incrementally.
"""

import csv
import logging
import math
import os
import shutil
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from video_scraper.convert_video_to_9_16_aspect_ratio import (
    convert_to_nine_sixteen_aspect_ratio,
)
from video_scraper.parser import get_video_src_from_url

log = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT_SECONDS = 30
DOWNLOAD_CHUNK_SIZE = 1 << 16  # 64 KiB


@dataclass
class ClipRecord:
    play_id: str
    game_pk: int
    game_date: str  # YYYY-MM-DD of the game itself, NOT when we scraped it
    pitcher_name: str
    batter_name: str
    team_fielding: str
    team_batting: str
    pitch_name: str
    call_name: str
    call_type: str  # "strike" or "ball"
    speed_mph: int
    landscape_path: str
    portrait_path: Optional[str]  # None when portrait conversion was skipped
    caption: str


def _classify_call(call_name: str) -> str:
    return "strike" if "strike" in call_name.lower() else "ball"


def _stream_download(url: str, dest_path: str) -> None:
    """Download `url` to `dest_path` with timeout + atomic rename on success."""
    tmp_path = dest_path + ".part"
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as r:
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
    shutil.move(tmp_path, dest_path)


def download_pitcher_videos(
    game_pk: int,
    pitcher_name: str,
    video_folder: str,
    team_id: int,
    game_date: str,
    seen_play_id: Optional[Callable[[str], bool]] = None,
    on_clip_recorded: Optional[Callable[[ClipRecord], None]] = None,
    skip_portrait_for_ball: bool = False,
) -> list[ClipRecord]:
    """Download every (new) clip for `pitcher_name` in `game_pk`.

    Args:
        seen_play_id: returns True if a play_id is already persisted; skipped if so.
        on_clip_recorded: invoked after each clip is fully downloaded + converted.
            Use this to commit state incrementally (so a crash mid-run is recoverable).
        skip_portrait_for_ball: if True, do not produce a 9:16 portrait copy for
            non-strike calls. Saves a lot of ffmpeg time when Shorts are strikes-only.
    """
    seen_play_id = seen_play_id or (lambda _pid: False)

    response = requests.get(
        f"https://baseballsavant.mlb.com/gf?game_pk={game_pk}",
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    team_name = "team_home" if team_id == data["team_home_id"] else "team_away"
    entries = [e for e in data[team_name] if e["pitcher_name"] == pitcher_name]
    if not entries:
        log.info("no plays for %s in game_pk=%s", pitcher_name, game_pk)
        return []

    csv_file = os.path.join(video_folder, f"{pitcher_name}.csv")
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)

    records: list[ClipRecord] = []
    with open(csv_file, mode="a", newline="") as f:
        writer = csv.writer(f)
        for counter, entry in enumerate(entries):
            play_id = entry["play_id"]
            if seen_play_id(play_id):
                log.debug("skipping already-recorded play_id=%s", play_id)
                continue

            start_speed = entry.get("start_speed") or 0
            rounded_speed = (
                math.ceil(start_speed)
                if start_speed % 1 >= 0.5
                else math.floor(start_speed)
            )
            call_type = _classify_call(entry["call_name"])
            caption = (
                f"{entry['pitcher_name']} vs. {entry['batter_name']} "
                f"{entry['pitch_name']} {rounded_speed} mph "
                f"{entry['call_name']} #shorts"
            )
            filename = (
                f"{entry['pitcher_name']} - {entry['batter_name']} - "
                f"{entry['team_fielding']} vs. {entry['team_batting']} "
                f"#{counter} {play_id}.mp4"
            )

            landscape_dir = os.path.join(
                video_folder, f"{game_pk}/landscape/{call_type}/{entry['pitch_name']}"
            )
            os.makedirs(landscape_dir, exist_ok=True)
            landscape_path = os.path.join(landscape_dir, filename)

            if os.path.exists(landscape_path) and os.path.getsize(landscape_path) > 0:
                log.debug("landscape already on disk, skipping download: %s", landscape_path)
            else:
                src = get_video_src_from_url(
                    f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id}"
                )
                if not src:
                    log.warning("could not resolve video src for play_id=%s", play_id)
                    continue
                try:
                    _stream_download(src, landscape_path)
                except requests.RequestException:
                    log.exception("download failed for play_id=%s", play_id)
                    continue

            portrait_path: Optional[str] = None
            need_portrait = not (skip_portrait_for_ball and call_type == "ball")
            if need_portrait:
                portrait_dir = os.path.join(
                    video_folder, f"{game_pk}/portrait/{call_type}/{entry['pitch_name']}"
                )
                expected_portrait = os.path.join(portrait_dir, filename)
                if os.path.exists(expected_portrait) and os.path.getsize(expected_portrait) > 0:
                    portrait_path = expected_portrait
                else:
                    try:
                        portrait_path = convert_to_nine_sixteen_aspect_ratio(
                            landscape_path, portrait_dir
                        )
                    except Exception:
                        log.exception("portrait conversion failed for play_id=%s", play_id)

            writer.writerow([filename, caption])
            record = ClipRecord(
                play_id=play_id,
                game_pk=int(game_pk),
                game_date=game_date,
                pitcher_name=entry["pitcher_name"],
                batter_name=entry["batter_name"],
                team_fielding=entry["team_fielding"],
                team_batting=entry["team_batting"],
                pitch_name=entry["pitch_name"],
                call_name=entry["call_name"],
                call_type=call_type,
                speed_mph=rounded_speed,
                landscape_path=landscape_path,
                portrait_path=portrait_path,
                caption=caption,
            )
            records.append(record)
            if on_clip_recorded is not None:
                try:
                    on_clip_recorded(record)
                except Exception:
                    log.exception("on_clip_recorded callback failed for play_id=%s", play_id)
    log.info("downloaded %d new clips for %s game_pk=%s", len(records), pitcher_name, game_pk)
    return records
