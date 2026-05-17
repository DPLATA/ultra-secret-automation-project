"""Generate YouTube title/description/tags for a built compilation.

Template-driven (no LLM call yet) so the daily pipeline is deterministic and
cheap. Swap in a Claude call here later if richer copy is wanted.
"""

from collections import Counter
from dataclasses import dataclass

from video_scraper.downloader import ClipRecord


@dataclass(frozen=True)
class Metadata:
    title: str
    description: str
    tags: list[str]


_MAX_TITLE_LEN = 100  # YouTube hard cap
_SITE_URL = "https://mlbsims.com"


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def for_long(pitcher_name: str, run_date: str, clips: list[ClipRecord]) -> Metadata:
    pitch_counts = Counter(c.pitch_name for c in clips)
    teams_faced = sorted({c.team_batting for c in clips})
    pitch_summary = ", ".join(f"{n} {p}" for p, n in pitch_counts.most_common())

    title = _truncate(
        f"{pitcher_name} — Every Pitch ({run_date})", _MAX_TITLE_LEN
    )
    description_lines = [
        f"Every pitch from {pitcher_name} compiled from games on / before {run_date}.",
        "",
        f"Pitches: {pitch_summary}",
        f"Opponents: {', '.join(teams_faced)}" if teams_faced else "",
        "",
        f"visit: {_SITE_URL}",
    ]
    description = "\n".join(line for line in description_lines if line is not None)
    tags = list({pitcher_name, "MLB", "baseball", "pitching", *pitch_counts.keys(), *teams_faced})
    return Metadata(title=title, description=description, tags=tags)


def for_short(
    pitcher_name: str, run_date: str, pitch_name: str, clips: list[ClipRecord]
) -> Metadata:
    speeds = [c.speed_mph for c in clips if c.speed_mph]
    speed_range = f"{min(speeds)}–{max(speeds)} mph" if speeds else ""
    title = _truncate(
        f"{pitcher_name} {pitch_name}s {speed_range} #shorts".strip(),
        _MAX_TITLE_LEN,
    )
    description_lines = [
        f"{pitcher_name} {pitch_name.lower()}s from {run_date}.",
        f"Clips: {len(clips)}",
        speed_range,
        "",
        f"visit: {_SITE_URL}",
        "",
        "#shorts #mlb #baseball",
    ]
    description = "\n".join(line for line in description_lines if line)
    tags = list(
        {pitcher_name, pitch_name, "MLB", "baseball", "pitching", "shorts"}
    )
    return Metadata(title=title, description=description, tags=tags)
