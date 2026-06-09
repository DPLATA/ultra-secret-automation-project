"""Fetch yesterday's MLB games and their pre-cut highlight clips from
the MLB Stats API.

Three layers, intentionally separated so the orchestrator can decide what
to download before doing any heavy I/O:
  - fetch_schedule(date)      -> GameMeta per Final game
  - fetch_highlights(game_pk) -> Highlight per pre-cut clip, chronological
  - download_highlight(...)   -> idempotent stream-download to disk

Highlights carry enough metadata to filter by taxonomy keywords (for the
league-wide pitcher reel) and to resolve a downloadable mp4 url.
"""

import logging
import os
import re
import shutil
from dataclasses import dataclass
from typing import Optional

import requests

log = logging.getLogger(__name__)

STATSAPI_BASE = "https://statsapi.mlb.com/api/v1"
REQUEST_TIMEOUT = 30
DOWNLOAD_CHUNK_SIZE = 1 << 16  # 64 KiB

# Playback "name" values in order of preference. mp4Avc is ~4000K H.264 at
# 720p and is present on every highlight-tagged item; highBit (~16000K) is
# pristine but only present on ~half. We skip hlsCloud / HTTP_CLOUD_WIRED*
# (.m3u8 streams) because we want one file per clip to feed ffmpeg concat.
PREFERRED_PLAYBACK_NAMES = ("mp4Avc", "highBit")

# Taxonomy values that identify true pitching highlights. Used by the
# pitcher reel to filter across all games for the date.
PITCHING_TAXONOMY_VALUES = frozenset({
    "pitching",
    "highlight-reel-pitching",
    "highlight-reel-starting-pitching",
    "highlight-reel-relief-pitching",
})


@dataclass(frozen=True)
class GameMeta:
    game_pk: int
    date: str
    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int
    status: str

    @property
    def slug(self) -> str:
        return f"{_team_slug(self.away_team)}_at_{_team_slug(self.home_team)}"


@dataclass(frozen=True)
class Highlight:
    highlight_id: str
    game_pk: int
    date_iso: str
    headline: str
    description: str
    duration_seconds: int
    taxonomy: tuple[str, ...]
    player_ids: tuple[int, ...]
    playback_url: str

    @property
    def is_pitching(self) -> bool:
        return any(t in PITCHING_TAXONOMY_VALUES for t in self.taxonomy)


def _team_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name).lower()


def _parse_duration(d: Optional[str]) -> int:
    """Parse MLB's HH:MM:SS (or MM:SS) duration string. Returns 0 if malformed
    — duration is decorative metadata; we re-probe locally with ffprobe before
    using it for pacing decisions."""
    if not d:
        return 0
    try:
        parts = [int(x) for x in d.split(":")]
    except (ValueError, AttributeError):
        return 0
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _best_playback_url(playbacks: list[dict]) -> Optional[str]:
    by_name = {pb.get("name"): pb.get("url") for pb in playbacks}
    for name in PREFERRED_PLAYBACK_NAMES:
        url = by_name.get(name)
        if url:
            return url
    return None


def fetch_schedule(date_str: str) -> list[GameMeta]:
    """Return all Final regular-season games on `date_str` (YYYY-MM-DD).

    Non-Final games (Postponed, Suspended, in-progress) are filtered out —
    they have no highlight reel to publish.
    """
    r = requests.get(
        f"{STATSAPI_BASE}/schedule",
        params={"sportId": 1, "date": date_str},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    games: list[GameMeta] = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            status = g.get("status", {}).get("detailedState", "")
            if status != "Final":
                continue
            games.append(GameMeta(
                game_pk=g["gamePk"],
                date=date_str,
                home_team=g["teams"]["home"]["team"]["name"],
                away_team=g["teams"]["away"]["team"]["name"],
                home_team_id=g["teams"]["home"]["team"]["id"],
                away_team_id=g["teams"]["away"]["team"]["id"],
                status=status,
            ))
    return games


def fetch_highlights(game_pk: int) -> list[Highlight]:
    """Return per-clip highlights for one game, chronologically ordered.

    Excludes non-clip media (recap articles, condensed games, data-vis
    assets) by requiring the 'highlight' taxonomy tag — without it the
    /content endpoint mixes in things like 17 actual clips alongside
    23 non-clip items per game. Returns [] on any failure so one bad game
    doesn't abort the run.
    """
    try:
        r = requests.get(
            f"{STATSAPI_BASE}/game/{game_pk}/content",
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException:
        log.exception("content endpoint failed for game_pk=%s", game_pk)
        return []

    items = data.get("highlights", {}).get("highlights", {}).get("items", []) or []
    out: list[Highlight] = []
    for item in items:
        kws = item.get("keywordsAll") or []
        taxonomy = tuple(
            k.get("value", "") for k in kws if k.get("type") == "taxonomy"
        )
        if "highlight" not in taxonomy:
            continue
        url = _best_playback_url(item.get("playbacks") or [])
        if not url:
            log.debug(
                "no mp4 playback for highlight id=%s game_pk=%s",
                item.get("id"), game_pk,
            )
            continue
        player_ids = tuple(
            int(k["value"]) for k in kws
            if k.get("type") == "player_id"
            and str(k.get("value", "")).isdigit()
        )
        out.append(Highlight(
            highlight_id=str(item.get("id") or item.get("mediaPlaybackId") or url),
            game_pk=game_pk,
            date_iso=item.get("date", "") or "",
            headline=item.get("headline", "") or "",
            description=item.get("description", "") or "",
            duration_seconds=_parse_duration(item.get("duration")),
            taxonomy=taxonomy,
            player_ids=player_ids,
            playback_url=url,
        ))
    out.sort(key=lambda h: h.date_iso)
    return out


def download_highlight(highlight: Highlight, dest_dir: str) -> str:
    """Stream-download a highlight's mp4 into `dest_dir`; return the file path.

    Idempotent: if the file already exists with non-zero size, returns the
    path without re-downloading. Atomic via .part rename so a crash mid-
    download doesn't leave a corrupt file that later runs treat as done.
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{highlight.highlight_id}.mp4")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    tmp = dest + ".part"
    with requests.get(
        highlight.playback_url, stream=True, timeout=REQUEST_TIMEOUT,
    ) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
    shutil.move(tmp, dest)
    return dest
