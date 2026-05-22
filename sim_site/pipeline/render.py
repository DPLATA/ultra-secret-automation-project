"""Render the static site from data/.

Reads simulated game JSONs (data/games/YYYY-MM-DD/*.json) and historical box
scores (data/games_<season>.csv), applies Jinja templates, writes a tree of
static HTML files under sim_site/site/ that can be deployed directly to
Cloudflare Pages (or any static host).

Layout produced:
  site/
    index.html                            # latest slate (or "calibrating")
    methodology.html
    style.css                             # already in repo
    games/YYYY-MM-DD/index.html           # slate for that date
    games/YYYY-MM-DD/AWAY-at-HOME.html    # per-game detail
    results/index.html                    # latest completed date
    results/YYYY-MM-DD/index.html         # results for that date
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from constants import MLB_TEAMS_INFO  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
SITE_DIR = ROOT / "site"
DATA_DIR = ROOT / "data"
GAMES_DIR = DATA_DIR / "games"

TEAM_LOOKUP = {t["Team ID"]: t for t in MLB_TEAMS_INFO}
CALIBRATING_THROUGH_MONTH = 5  # show "calibrating" splash through April
YOUTUBE_SHORTS_URL = "https://www.youtube.com/@mlbsims/shorts"


def load_game_sims() -> dict[str, list[dict]]:
    """Map of date string -> list of game dicts, sorted by game_time_utc."""
    out: dict[str, list[dict]] = {}
    if not GAMES_DIR.exists():
        return out
    for date_dir in sorted(GAMES_DIR.iterdir()):
        if not date_dir.is_dir():
            continue
        games = []
        for f in sorted(date_dir.glob("*.json")):
            with open(f) as fh:
                games.append(json.load(fh))
        games.sort(key=lambda g: g.get("game_time_utc") or "")
        out[date_dir.name] = games
    return out


def load_completed_games(season: int) -> pd.DataFrame:
    path = DATA_DIR / f"games_{season}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date", "home_id", "away_id", "home_runs", "away_runs"])
    df = pd.read_csv(path)
    df["home_abbr"] = df["home_id"].map(lambda i: TEAM_LOOKUP.get(i, {}).get("Abbreviation", str(i)))
    df["away_abbr"] = df["away_id"].map(lambda i: TEAM_LOOKUP.get(i, {}).get("Abbreviation", str(i)))
    return df


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def long_date(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%A, %B %-d, %Y")


def is_calibrating(today: dt.date) -> bool:
    return today.month < CALIBRATING_THROUGH_MONTH


def yesterday_record(today: dt.date, sims: dict, completed: pd.DataFrame) -> dict | None:
    """Walk back from today to find the most recent date with both predictions
    and actuals; return {date, correct, total} for that day. Powers the hero's
    live social-proof line ('the model went X/N yesterday'). Returns None if
    no eligible day exists within the last 14 days.
    """
    if completed.empty:
        return None
    for back in range(1, 15):
        d = today - dt.timedelta(days=back)
        date_str = d.isoformat()
        if date_str not in sims:
            continue
        actuals = completed[completed["date"] == date_str]
        if actuals.empty:
            continue
        actuals_by_pk = {int(r.game_pk): r for _, r in actuals.iterrows()}
        correct = total = 0
        for pred in sims[date_str]:
            actual = actuals_by_pk.get(int(pred["game_pk"]))
            if actual is None:
                continue
            pred_winner = "home" if pred["win_probability"]["home"] > pred["win_probability"]["away"] else "away"
            actual_winner = "home" if actual.home_runs > actual.away_runs else "away"
            total += 1
            if pred_winner == actual_winner:
                correct += 1
        if total >= 5:
            return {"date": date_str, "correct": correct, "total": total}
    return None


# MailerLite list endpoint for direct form POST (same list as the footer embed).
MAILERLITE_SUBSCRIBE_URL = (
    "https://assets.mailerlite.com/jsonp/2358834/forms/187827545546163994/subscribe"
)


def copy_static() -> None:
    """Copy everything under sim_site/static/ into the site output dir."""
    if not STATIC_DIR.exists():
        return
    for src in STATIC_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(STATIC_DIR)
        dst = SITE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())


def render(today: dt.date | None = None) -> None:
    today = today or dt.date.today()
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape())
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    common = {
        "generated_at": generated_at,
        "youtube_shorts_url": YOUTUBE_SHORTS_URL,
        "mailerlite_subscribe_url": MAILERLITE_SUBSCRIBE_URL,
    }

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    copy_static()

    # Methodology — static
    methodology_tpl = env.get_template("methodology.html")
    write(SITE_DIR / "methodology.html",
          methodology_tpl.render(nav="methodology", **common))

    # Calibrating splash — used as index.html before May
    if is_calibrating(today):
        calib_tpl = env.get_template("calibrating.html")
        write(SITE_DIR / "index.html", calib_tpl.render(nav="today", **common))
        print(f"[calibrating mode] today={today} — wrote calibrating splash as index.html")
        return

    # Slate pages from simulated game JSONs
    sims = load_game_sims()
    completed_now = load_completed_games(today.year)
    common["yesterday_record"] = yesterday_record(today, sims, completed_now)
    slate_tpl = env.get_template("slate.html")
    game_tpl = env.get_template("game.html")

    for date_str, games in sims.items():
        slate_html = slate_tpl.render(
            nav="today",
            slate_date=date_str,
            slate_date_long=long_date(date_str),
            games=games,
            show_footer_signup=False,  # hero already has the signup
            **common,
        )
        write(SITE_DIR / "games" / date_str / "index.html", slate_html)

        for g in games:
            game_html = game_tpl.render(nav="today", g=g, **common)
            slug = f"{g['away']['abbr']}-at-{g['home']['abbr']}"
            write(SITE_DIR / "games" / date_str / f"{slug}.html", game_html)

    # Root index = the slate with the latest (max) date >= today, falling back
    # to the most recent any-date slate.
    if sims:
        latest_date = max(sims.keys())
        write(SITE_DIR / "index.html",
              slate_tpl.render(
                  nav="today",
                  slate_date=latest_date,
                  slate_date_long=long_date(latest_date),
                  games=sims[latest_date],
                  show_footer_signup=False,  # hero already has the signup
                  **common,
              ))

    # Results pages from historical box scores
    completed = completed_now
    results_tpl = env.get_template("results.html")
    if not completed.empty:
        recent_dates = sorted(completed["date"].unique(), reverse=True)[:14]
        for date_str in recent_dates:
            games_for_date = completed[completed["date"] == date_str].to_dict(orient="records")
            html = results_tpl.render(
                nav="results",
                result_date=date_str,
                result_date_long=long_date(date_str),
                games=games_for_date,
                recent_dates=[d for d in recent_dates if d != date_str][:7],
                **common,
            )
            write(SITE_DIR / "results" / date_str / "index.html", html)

        # /results/ -> most recent completed date
        latest_result_date = recent_dates[0]
        games_for_date = completed[completed["date"] == latest_result_date].to_dict(orient="records")
        write(SITE_DIR / "results" / "index.html",
              results_tpl.render(
                  nav="results",
                  result_date=latest_result_date,
                  result_date_long=long_date(latest_result_date),
                  games=games_for_date,
                  recent_dates=recent_dates[1:7],
                  **common,
              ))

    write_sitemap(SITE_DIR, sims, completed, today)

    print(f"Rendered site to {SITE_DIR}")
    print(f"  slate dates: {sorted(sims.keys())}")
    print(f"  results dates: {len(completed['date'].unique()) if not completed.empty else 0}")


SITE_BASE = "https://mlbsims.com"


def write_sitemap(site_dir: Path, sims: dict, completed: pd.DataFrame, today: dt.date) -> None:
    """Generate sitemap.xml listing every public URL on the site, with lastmod.

    Search engines (especially for new sites) rely on the sitemap to discover
    pages — without it, Google may take weeks to find non-homepage URLs since
    nothing links to them yet.
    """
    today_iso = today.isoformat()
    urls: list[tuple[str, str]] = [
        (f"{SITE_BASE}/", today_iso),
        (f"{SITE_BASE}/methodology", today_iso),
        (f"{SITE_BASE}/results/", today_iso),
    ]

    # Slate pages + per-game detail pages
    for date_str, games in sorted(sims.items()):
        urls.append((f"{SITE_BASE}/games/{date_str}/", date_str))
        for g in games:
            slug = f"{g['away']['abbr']}-at-{g['home']['abbr']}"
            urls.append((f"{SITE_BASE}/games/{date_str}/{slug}", date_str))

    # Per-date results pages
    if not completed.empty:
        for date_str in sorted(set(completed["date"].tolist()), reverse=True)[:30]:
            urls.append((f"{SITE_BASE}/results/{date_str}/", date_str))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in urls:
        lines.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
    lines.append("</urlset>")
    (site_dir / "sitemap.xml").write_text("\n".join(lines))


if __name__ == "__main__":
    today = dt.date.today()
    if len(sys.argv) > 1:
        today = dt.date.fromisoformat(sys.argv[1])
    render(today)
