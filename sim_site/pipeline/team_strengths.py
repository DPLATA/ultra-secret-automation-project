"""Compute team home/away offensive & defensive strengths from completed games.

The Soccermatics-style ratio model, with park factor adjustment.

A team's home games happen entirely at one venue, so their raw home scoring
includes that park's effect. We divide each team's home runs (scored & allowed)
by their park factor to get park-neutral per-game numbers, then compute
strengths against the park-neutral league average.

Strengths (all in park-neutral units, > 1 means above league average):
  home_attack  = adj home runs scored/game / league adj home runs/game
  away_attack  = away runs scored/game     / league away runs/game
  home_defense = adj home runs allowed/game / league away runs/game
  away_defense = away runs allowed/game     / league adj home runs/game

When predicting a real game at venue V, the park factor of V is multiplied back
in. We carry the league averages and park factors as DataFrame attrs so the
simulator can use them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from constants import MLB_TEAMS_INFO  # noqa: E402
from sim_site.pipeline.park_factors import PARK_FACTORS, factor  # noqa: E402


TEAM_LOOKUP = {t["Team ID"]: t for t in MLB_TEAMS_INFO}


def compute(games: pd.DataFrame) -> pd.DataFrame:
    home_grp = games.groupby("home_id").agg(
        home_games=("home_runs", "size"),
        home_runs_scored=("home_runs", "sum"),
        home_runs_allowed=("away_runs", "sum"),
    )
    away_grp = games.groupby("away_id").agg(
        away_games=("away_runs", "size"),
        away_runs_scored=("away_runs", "sum"),
        away_runs_allowed=("home_runs", "sum"),
    )
    df = home_grp.join(away_grp, how="outer").fillna(0)

    df["park_factor"] = df.index.map(factor)

    df["home_rs_pg"] = df["home_runs_scored"] / df["home_games"].replace(0, pd.NA)
    df["home_ra_pg"] = df["home_runs_allowed"] / df["home_games"].replace(0, pd.NA)
    df["away_rs_pg"] = df["away_runs_scored"] / df["away_games"].replace(0, pd.NA)
    df["away_ra_pg"] = df["away_runs_allowed"] / df["away_games"].replace(0, pd.NA)

    # Park-neutralize home stats by removing the home venue's run inflation.
    df["home_rs_neutral"] = df["home_rs_pg"] / df["park_factor"]
    df["home_ra_neutral"] = df["home_ra_pg"] / df["park_factor"]

    league_home_neutral = df["home_rs_neutral"].mean()
    league_away = df["away_rs_pg"].mean()

    df["home_attack"] = df["home_rs_neutral"] / league_home_neutral
    df["away_attack"] = df["away_rs_pg"] / league_away
    df["home_defense"] = df["home_ra_neutral"] / league_away
    df["away_defense"] = df["away_ra_pg"] / league_home_neutral

    df["abbr"] = df.index.map(lambda tid: TEAM_LOOKUP.get(tid, {}).get("Abbreviation", str(tid)))
    df["name"] = df.index.map(lambda tid: TEAM_LOOKUP.get(tid, {}).get("Brief Name", str(tid)))
    df.attrs["league_home_neutral"] = league_home_neutral
    df.attrs["league_away"] = league_away
    return df


def expected_runs(strengths: pd.DataFrame, home_id: int, away_id: int) -> tuple[float, float]:
    """Predicted (home_runs, away_runs) for a game at the home team's park."""
    s = strengths
    pf = factor(home_id)
    league_home = s.attrs["league_home_neutral"]
    league_away = s.attrs["league_away"]
    home_exp = s.loc[home_id, "home_attack"] * s.loc[away_id, "away_defense"] * league_home * pf
    away_exp = s.loc[home_id, "home_defense"] * s.loc[away_id, "away_attack"] * league_away * pf
    return float(home_exp), float(away_exp)


def print_table(strengths: pd.DataFrame) -> None:
    cols = ["abbr", "park_factor", "home_games", "away_games",
            "home_rs_pg", "away_rs_pg", "home_ra_pg", "away_ra_pg",
            "home_attack", "away_attack", "home_defense", "away_defense"]
    view = strengths[cols].sort_values("home_attack", ascending=False)
    with pd.option_context("display.float_format", "{:.3f}".format,
                           "display.max_rows", None,
                           "display.width", 180):
        print(view.to_string(index=False))
    print()
    print(f"League park-neutral home runs/game: {strengths.attrs['league_home_neutral']:.3f}")
    print(f"League away runs/game:              {strengths.attrs['league_away']:.3f}")


if __name__ == "__main__":
    import datetime as dt
    from sim_site.pipeline import ingest

    season = dt.date.today().year
    games = ingest.fetch_games(season)
    print(f"Loaded {len(games)} completed games for {season}")
    strengths = compute(games)
    print_table(strengths)

    print()
    print("Sample expected-runs predictions (home, away):")
    samples = [(147, 111), (115, 119), (137, 135)]  # NYY@BOS, LAD@COL, SD@SF
    for home, away in samples:
        h_exp, a_exp = expected_runs(strengths, home, away)
        h = TEAM_LOOKUP[home]["Abbreviation"]
        a = TEAM_LOOKUP[away]["Abbreviation"]
        print(f"  {a} @ {h}: expected {a}={a_exp:.2f}, {h}={h_exp:.2f}  (PF={factor(home):.2f})")
