"""Run Poisson Monte Carlo simulations for a slate of scheduled games.

For each game, draw N independent Poisson samples for the home and away run
totals using the lambdas from team_strengths.expected_runs(). Aggregate into
win probability, regulation-tie ("extras") probability, score distribution,
and over/under at common totals.

Output: one JSON file per game under sim_site/data/games/YYYY-MM-DD/, plus a
slate summary printed to stdout.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from sim_site.pipeline import ingest, team_strengths
from sim_site.pipeline.park_factors import factor
from sim_site.pipeline.team_strengths import TEAM_LOOKUP

N_SIMS_DEFAULT = 10_000
OVER_UNDER_LINES = (6.5, 7.5, 8.5, 9.5, 10.5)
RNG = np.random.default_rng()
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "games"


def simulate_game(home_lambda: float, away_lambda: float,
                  n_sims: int = N_SIMS_DEFAULT) -> dict:
    home_runs = RNG.poisson(home_lambda, n_sims)
    away_runs = RNG.poisson(away_lambda, n_sims)

    home_win = int((home_runs > away_runs).sum())
    away_win = int((away_runs > home_runs).sum())
    extras = n_sims - home_win - away_win

    score_counts = Counter(zip(home_runs.tolist(), away_runs.tolist()))
    top_scores = [
        {"home": h, "away": a, "probability": c / n_sims}
        for (h, a), c in score_counts.most_common(8)
    ]

    totals = home_runs + away_runs
    over_under = {}
    for line in OVER_UNDER_LINES:
        over = float((totals > line).mean())
        over_under[str(line)] = {"over": over, "under": 1.0 - over}

    return {
        "n_simulations": n_sims,
        "expected": {
            "home_runs": float(home_lambda),
            "away_runs": float(away_lambda),
            "total_runs": float(home_lambda + away_lambda),
        },
        "win_probability": {
            "home": home_win / n_sims,
            "away": away_win / n_sims,
            "extras": extras / n_sims,
        },
        "totals": {
            "mean": float(totals.mean()),
            "median": float(np.median(totals)),
            "p10": float(np.quantile(totals, 0.10)),
            "p90": float(np.quantile(totals, 0.90)),
        },
        "over_under": over_under,
        "most_likely_scores": top_scores,
    }


def simulate_slate(strengths: pd.DataFrame, slate: pd.DataFrame,
                   n_sims: int = N_SIMS_DEFAULT) -> list[dict]:
    results = []
    for game in slate.itertuples(index=False):
        if game.home_id not in strengths.index or game.away_id not in strengths.index:
            continue
        home_lambda, away_lambda = team_strengths.expected_runs(
            strengths, game.home_id, game.away_id
        )
        sim = simulate_game(home_lambda, away_lambda, n_sims)

        home_meta = TEAM_LOOKUP.get(game.home_id, {})
        away_meta = TEAM_LOOKUP.get(game.away_id, {})
        results.append({
            "date": game.date,
            "game_pk": int(game.game_pk),
            "game_time_utc": game.game_time,
            "venue": game.venue,
            "venue_park_factor": factor(game.home_id),
            "home": {
                "id": int(game.home_id),
                "abbr": home_meta.get("Abbreviation"),
                "name": home_meta.get("Brief Name"),
            },
            "away": {
                "id": int(game.away_id),
                "abbr": away_meta.get("Abbreviation"),
                "name": away_meta.get("Brief Name"),
            },
            **sim,
        })
    return results


def save_games(results: list[dict]) -> list[Path]:
    paths = []
    for r in results:
        date_dir = DATA_DIR / r["date"]
        date_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{r['away']['abbr']}-at-{r['home']['abbr']}"
        path = date_dir / f"{slug}.json"
        with open(path, "w") as f:
            json.dump(r, f, indent=2)
        paths.append(path)
    return paths


def print_slate_summary(results: list[dict]) -> None:
    if not results:
        print("No games on slate.")
        return
    rows = []
    for r in results:
        rows.append({
            "matchup": f"{r['away']['abbr']} @ {r['home']['abbr']}",
            "PF": r["venue_park_factor"],
            "E[away]": r["expected"]["away_runs"],
            "E[home]": r["expected"]["home_runs"],
            "E[total]": r["expected"]["total_runs"],
            "away_win%": r["win_probability"]["away"] * 100,
            "home_win%": r["win_probability"]["home"] * 100,
            "extras%": r["win_probability"]["extras"] * 100,
            "P(over 8.5)": r["over_under"]["8.5"]["over"] * 100,
        })
    df = pd.DataFrame(rows)
    with pd.option_context("display.float_format", "{:.2f}".format,
                           "display.max_rows", None,
                           "display.width", 160):
        print(df.to_string(index=False))


if __name__ == "__main__":
    import sys

    target = dt.date.today()
    if len(sys.argv) > 1:
        target = dt.date.fromisoformat(sys.argv[1])

    print(f"Building strengths from {target.year} season-to-date (through {target - dt.timedelta(days=1)})...")
    games = ingest.fetch_games(target.year, through=target - dt.timedelta(days=1))
    print(f"  loaded {len(games)} completed games")
    strengths = team_strengths.compute(games)

    print(f"Fetching slate for {target}...")
    slate = ingest.fetch_slate(target)
    print(f"  {len(slate)} games scheduled")

    if slate.empty:
        sys.exit(0)

    print(f"Simulating {N_SIMS_DEFAULT:,} draws per game...")
    results = simulate_slate(strengths, slate)
    paths = save_games(results)
    print(f"Wrote {len(paths)} game JSONs to {DATA_DIR / target.isoformat()}\n")
    print_slate_summary(results)
