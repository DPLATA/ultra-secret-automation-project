"""Build MLB highlight reels from the MLB Stats API content endpoint.

Two builders, both reusing the ffmpeg concat-demuxer-with-reencode-fallback
helper from automation/compiler.py:

  - build_game_reel(game, highlights, ...) -> one mp4 per game, every
    highlight-tagged clip in chronological order.
  - build_pitcher_reel(date, highlights_by_game, ...) -> one mp4/day
    containing every pitching-tagged clip across the slate.

Downloads are delegated to video_scraper.mlb_content. Outputs go under
{compilations_dir}/highlights/{date}/.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from automation.compiler import _ffmpeg_concat_demuxer, _ffprobe_duration
from video_scraper.mlb_content import (
    GameMeta, Highlight, download_highlight,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuiltHighlightReel:
    kind: str  # "game_reel" | "pitcher_reel"
    output_path: Path
    game_pk: Optional[int]  # None for pitcher reel
    date: str
    highlight_ids: list[str]


def _download_all(
    highlights: Iterable[Highlight], dest_dir: Path,
) -> list[tuple[Highlight, str]]:
    """Download every highlight to dest_dir; skip any that fail.

    Returns (highlight, local_path) pairs in input order, omitting failures
    so one bad clip doesn't sink a whole reel.
    """
    out: list[tuple[Highlight, str]] = []
    for h in highlights:
        try:
            path = download_highlight(h, str(dest_dir))
            out.append((h, path))
        except Exception:
            log.exception(
                "download failed for highlight %s game_pk=%s; skipping",
                h.highlight_id, h.game_pk,
            )
    return out


def build_game_reel(
    game: GameMeta,
    highlights: list[Highlight],
    compilations_dir: Path,
    videos_dir: Path,
    min_clips: int = 3,
) -> Optional[BuiltHighlightReel]:
    """Build one mp4 with every highlight from `game`, chronological order.

    Skips games with fewer than `min_clips` highlights — a 2-clip "reel"
    looks broken. Returns None for skipped or failed games.
    """
    if len(highlights) < min_clips:
        log.info(
            "skip game reel for %s: %d clips < min %d",
            game.slug, len(highlights), min_clips,
        )
        return None

    clip_cache = videos_dir / "highlights" / game.date / str(game.game_pk)
    downloaded = _download_all(highlights, clip_cache)
    if len(downloaded) < min_clips:
        log.warning(
            "skip game reel for %s: only %d/%d clips downloaded ok",
            game.slug, len(downloaded), len(highlights),
        )
        return None

    out_dir = compilations_dir / "highlights" / game.date
    out_path = out_dir / f"{game.slug}.mp4"
    _ffmpeg_concat_demuxer([p for _, p in downloaded], out_path)
    log.info(
        "built game reel: %s (%d clips, %.0fs)",
        out_path, len(downloaded), _ffprobe_duration(str(out_path)),
    )
    return BuiltHighlightReel(
        kind="game_reel",
        output_path=out_path,
        game_pk=game.game_pk,
        date=game.date,
        highlight_ids=[h.highlight_id for h, _ in downloaded],
    )


def build_pitcher_reel(
    date: str,
    highlights_by_game: dict[int, list[Highlight]],
    compilations_dir: Path,
    videos_dir: Path,
    min_clips: int = 5,
) -> Optional[BuiltHighlightReel]:
    """Build the daily league-wide pitching reel.

    Pulls every pitching-tagged highlight across `highlights_by_game` and
    concats them in chronological order. Returns None if the slate yields
    fewer than `min_clips` pitching highlights — a tiny "reel" isn't worth
    publishing.
    """
    pitching: list[Highlight] = []
    for game_pk, items in highlights_by_game.items():
        pitching.extend(h for h in items if h.is_pitching)
    pitching.sort(key=lambda h: h.date_iso)

    if len(pitching) < min_clips:
        log.info(
            "skip pitcher reel for %s: %d pitching clips < min %d",
            date, len(pitching), min_clips,
        )
        return None

    downloaded: list[tuple[Highlight, str]] = []
    for h in pitching:
        clip_cache = videos_dir / "highlights" / date / str(h.game_pk)
        try:
            path = download_highlight(h, str(clip_cache))
            downloaded.append((h, path))
        except Exception:
            log.exception(
                "download failed for pitching highlight %s game_pk=%s; skipping",
                h.highlight_id, h.game_pk,
            )

    if len(downloaded) < min_clips:
        log.warning(
            "skip pitcher reel for %s: only %d/%d pitching clips downloaded ok",
            date, len(downloaded), len(pitching),
        )
        return None

    out_dir = compilations_dir / "highlights" / date
    out_path = out_dir / "pitcher_reel.mp4"
    _ffmpeg_concat_demuxer([p for _, p in downloaded], out_path)
    log.info(
        "built pitcher reel: %s (%d clips, %.0fs)",
        out_path, len(downloaded), _ffprobe_duration(str(out_path)),
    )
    return BuiltHighlightReel(
        kind="pitcher_reel",
        output_path=out_path,
        game_pk=None,
        date=date,
        highlight_ids=[h.highlight_id for h, _ in downloaded],
    )
