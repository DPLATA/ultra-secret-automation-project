"""Pull season-to-date completed games from the MLB Stats API.

Output: pandas DataFrame with one row per completed regular-season game,
columns: date, home_id, away_id, home_runs, away_runs.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import requests

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def season_start(year: int) -> dt.date:
    return dt.date(year, 3, 1)


def fetch_games(season: int, through: dt.date | None = None) -> pd.DataFrame:
    through = through or dt.date.today()
    params = {
        "sportId": 1,
        "gameType": "R",
        "startDate": season_start(season).isoformat(),
        "endDate": through.isoformat(),
    }
    r = requests.get(SCHEDULE_URL, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()

    rows = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            status = game.get("status", {}).get("abstractGameState")
            if status != "Final":
                continue
            home = game["teams"]["home"]
            away = game["teams"]["away"]
            if "score" not in home or "score" not in away:
                continue
            rows.append({
                "date": day["date"],
                "game_pk": game["gamePk"],
                "home_id": home["team"]["id"],
                "away_id": away["team"]["id"],
                "home_runs": home["score"],
                "away_runs": away["score"],
            })
    return pd.DataFrame(rows)


def fetch_slate(date: dt.date) -> pd.DataFrame:
    """Pull scheduled (not-yet-final) regular-season games for a single date."""
    params = {
        "sportId": 1,
        "gameType": "R",
        "startDate": date.isoformat(),
        "endDate": date.isoformat(),
    }
    r = requests.get(SCHEDULE_URL, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()

    rows = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            status = game.get("status", {}).get("abstractGameState")
            if status == "Final":
                continue
            home = game["teams"]["home"]
            away = game["teams"]["away"]
            rows.append({
                "date": day["date"],
                "game_pk": game["gamePk"],
                "game_time": game.get("gameDate"),
                "home_id": home["team"]["id"],
                "away_id": away["team"]["id"],
                "venue": game.get("venue", {}).get("name"),
            })
    return pd.DataFrame(rows)


def save(df: pd.DataFrame, season: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"games_{season}.csv"
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    season = dt.date.today().year
    df = fetch_games(season)
    path = save(df, season)
    print(f"Pulled {len(df)} completed games for {season} -> {path}")
