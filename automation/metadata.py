"""Generate YouTube title/description/tags for a built compilation.

Template-driven (no LLM call yet) so the daily pipeline is deterministic and
cheap. Swap in a Claude call here later if richer copy is wanted.
"""

import datetime as dt
from collections import Counter
from dataclasses import dataclass

from constants import MLB_TEAMS_INFO
from video_scraper.downloader import ClipRecord

_TEAM_BY_ABBR = {t["Abbreviation"]: t["Brief Name"] for t in MLB_TEAMS_INFO}


@dataclass(frozen=True)
class Metadata:
    title: str
    description: str
    tags: list[str]


_MAX_TITLE_LEN = 100  # YouTube hard cap
_SITE_URL = "https://mlbsims.com"


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _short_date(iso_date: str) -> str:
    """ISO YYYY-MM-DD → 'May 17' (no leading zero on the day)."""
    return dt.date.fromisoformat(iso_date).strftime("%b %-d")


def for_long(pitcher_name: str, run_date: str, clips: list[ClipRecord]) -> Metadata:
    pitch_counts = Counter(c.pitch_name for c in clips)
    teams_faced = sorted({c.team_batting for c in clips})
    pitch_summary = ", ".join(f"{n} {p}" for p, n in pitch_counts.most_common())

    speeds = [c.speed_mph for c in clips if c.speed_mph]
    max_velo = int(max(speeds)) if speeds else None
    last_name = pitcher_name.split()[-1]
    date_short = _short_date(run_date)

    # Title — lead with max velocity when available (proven CTR lever); fall
    # back to the pitcher-name pattern when we don't have speed data.
    if max_velo:
        title = f"{last_name.upper()} HIT {max_velo}! Every Pitch ({date_short})"
    else:
        title = f"{pitcher_name} — Every Pitch ({date_short})"
    title = _truncate(title, _MAX_TITLE_LEN)

    # Description — first line carries matchup + headline stat above the fold.
    if teams_faced:
        opponent = _TEAM_BY_ABBR.get(teams_faced[0], teams_faced[0])
        matchup = f"{pitcher_name} vs the {opponent} on {date_short}"
    else:
        matchup = f"{pitcher_name}'s outing on {date_short}"
    headline_parts = [f"{len(clips)} pitches"]
    if max_velo:
        headline_parts.append(f"top velocity {max_velo} mph")
    headline = ", ".join(headline_parts)

    description_lines = [
        f"{matchup} — {headline}. Every pitch, every result.",
        "",
        f"Pitch mix: {pitch_summary}",
        "",
        f"Daily predictions + accuracy tracking: {_SITE_URL}",
        f"How the model works: {_SITE_URL}/methodology",
        f"Newsletter for tomorrow's picks: {_SITE_URL}",
        "",
        f"#MLB #baseball #pitching #{last_name.replace(' ', '')}",
    ]
    description = "\n".join(description_lines)
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


# Day-of-week rotation for the daily Predicted-vs-Actual recap Short.
# Index 0 = Monday (Python datetime convention). Lets us A/B test hook formats
# without manual intervention; the channel cycles through 4 patterns per week.
def _recap_title(target_date, correct: int, total: int) -> str:
    formats = [
        # Mon — list framing
        lambda: "Every MLB matchup our model called yesterday #Shorts",
        # Tue — stat-led
        lambda: f"Our MLB model went {correct}/{total} yesterday. Watch the misses. #Shorts",
        # Wed — drama hook
        lambda: f"Did our MLB model fix itself? {correct}/{total} yesterday #Shorts",
        # Thu — comeback / streak
        lambda: f"The MLB model bounced back yesterday ({correct}/{total}) #Shorts",
        # Fri — list again
        lambda: "Every MLB matchup our model called yesterday #Shorts",
        # Sat — stat-led again
        lambda: f"Our MLB model went {correct}/{total} yesterday. Watch the misses. #Shorts",
        # Sun — drama again
        lambda: f"Did our MLB model fix itself? {correct}/{total} yesterday #Shorts",
    ]
    return formats[target_date.weekday()]()


def _best_call(rows):
    """Highest-confidence correct call from the day's slate."""
    hits = [r for r in rows if r.get("winner_called")]
    return max(hits, key=lambda r: r["winner_pct"]) if hits else None


def _worst_miss(rows):
    """Highest-confidence wrong call from the day's slate (model was confident and lost)."""
    misses = [r for r in rows if not r.get("winner_called")]
    return max(misses, key=lambda r: r["winner_pct"]) if misses else None


def for_recap(target_date, correct: int, total: int, rows: list[dict] | None = None) -> Metadata:
    """Metadata for the daily Predicted-vs-Actual recap Short.

    Title is adaptive: leans into the day's actual performance. If the model
    crushed (>= 70%) or bombed (< 40%), the title says so directly; otherwise
    falls back to the day-of-week rotation for A/B testing of generic hooks.

    Description includes the best correct call + worst miss when row data is
    available — turns a record into a story worth sharing.
    """
    pct = correct / total if total else 0
    if pct >= 0.70:
        title = f"Our MLB model NAILED yesterday: {correct}/{total} #Shorts"
    elif pct < 0.40:
        title = f"We bombed yesterday: {correct}/{total} picks. Here's why. #Shorts"
    else:
        title = _recap_title(target_date, correct, total)
    title = _truncate(title, _MAX_TITLE_LEN)

    description_lines = [
        f"We went {correct} out of {total} on yesterday's MLB picks.",
        "",
    ]
    if rows:
        best = _best_call(rows)
        worst = _worst_miss(rows)
        if best:
            description_lines.append(
                f"Best call: {best['matchup']} — model favored "
                f"{best['pred_winner_abbr']} {best['winner_pct']}% → "
                f"final {best['actual_score']}"
            )
        if worst:
            description_lines.append(
                f"Worst miss: {worst['matchup']} — we said "
                f"{worst['pred_winner_abbr']} {worst['winner_pct']}% → "
                f"final {worst['actual_score']}"
            )
        if best or worst:
            description_lines.append("")

    description_lines.extend([
        "Park-adjusted Poisson Monte Carlo, 10,000 sims per game. "
        f"Tonight's slate + accuracy tracking: {_SITE_URL}",
        f"Newsletter for tomorrow's picks: {_SITE_URL}",
        "",
        "#shorts #MLB #baseball #MLBpicks #sabermetrics #predictions",
    ])
    description = "\n".join(description_lines)
    tags = ["shorts", "mlb", "baseball", "mlb predictions", "baseball analytics",
            "mlb sims", "sabermetrics", "poisson", "predictions vs actual"]
    return Metadata(title=title, description=description, tags=tags)
