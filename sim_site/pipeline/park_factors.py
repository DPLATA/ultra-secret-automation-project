"""Multiplicative park run factors, keyed by MLB team ID.

A factor of 1.10 means runs at that park are inflated 10% above a neutral park;
0.92 means runs are suppressed 8%. These are 3-year basic run park factors,
approximated from publicly published values (FanGraphs / Statcast). They are
intentionally simple: one number per park, applied symmetrically to home & road
scoring at that venue.

Update annually. Park factors are very stable year-over-year so frequent
re-tuning is unnecessary.
"""
from __future__ import annotations

# Keyed by MLB team ID (matches constants.MLB_TEAMS_INFO "Team ID").
PARK_FACTORS: dict[int, float] = {
    108: 0.99,  # LAA - Angel Stadium
    109: 1.02,  # ARI - Chase Field
    110: 1.03,  # BAL - Camden Yards
    111: 1.04,  # BOS - Fenway Park
    112: 0.99,  # CHC - Wrigley Field
    113: 1.05,  # CIN - Great American Ball Park
    114: 0.98,  # CLE - Progressive Field
    115: 1.12,  # COL - Coors Field
    116: 0.96,  # DET - Comerica Park
    117: 1.02,  # HOU - Minute Maid Park
    118: 1.02,  # KC  - Kauffman Stadium
    119: 0.99,  # LAD - Dodger Stadium
    120: 0.99,  # WSH - Nationals Park
    121: 0.97,  # NYM - Citi Field
    133: 0.96,  # OAK - Sutter Health Park / Coliseum era
    134: 0.95,  # PIT - PNC Park
    135: 0.95,  # SD  - Petco Park
    136: 0.93,  # SEA - T-Mobile Park
    137: 0.91,  # SF  - Oracle Park
    138: 0.96,  # STL - Busch Stadium
    139: 0.97,  # TB  - Tropicana / Steinbrenner
    140: 1.01,  # TEX - Globe Life Field
    141: 1.01,  # TOR - Rogers Centre
    142: 0.98,  # MIN - Target Field
    143: 1.00,  # PHI - Citizens Bank Park
    144: 1.00,  # ATL - Truist Park
    145: 0.99,  # CWS - Rate Field
    146: 0.94,  # MIA - loanDepot park
    147: 0.99,  # NYY - Yankee Stadium
    158: 0.99,  # MIL - American Family Field
}


def factor(team_id: int) -> float:
    return PARK_FACTORS.get(team_id, 1.0)
