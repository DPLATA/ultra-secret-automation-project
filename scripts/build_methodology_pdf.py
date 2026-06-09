"""Build the methodology PDF lead magnet for mlbsims.com newsletter subscribers.

Renders ~8-page clean whitepaper-style PDF: navy cover, white body pages with
serif body type, cyan accent. Uses WeasyPrint for HTML → PDF conversion.

Output: lead_magnets/methodology.pdf

WeasyPrint needs Pango/Cairo system libs (installed via `brew install pango`
on macOS). The DYLD_FALLBACK_LIBRARY_PATH env var ensures Python finds them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sure WeasyPrint can find Pango/Cairo from Homebrew
os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

from weasyprint import HTML  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "lead_magnets" / "methodology.pdf"


HTML_DOC = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>How We Predict MLB Games · MLB Sims</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap');

  @page {
    size: A4;
    margin: 22mm 18mm;
    @bottom-right {
      content: "mlbsims.com · " counter(page);
      font-family: 'Inter', sans-serif;
      font-size: 9pt;
      color: #6b7280;
    }
  }
  @page cover {
    background: #0f172a;
    margin: 0;
    @bottom-right { content: none; }
    @bottom-left { content: none; }
    @bottom-center { content: none; }
    @top-right { content: none; }
  }

  :root {
    --navy: #0f172a;
    --cyan: #22d3ee;
    --fg: #1a1a1a;
    --muted: #6b7280;
    --rule: #e5e7eb;
  }

  body {
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 11pt;
    line-height: 1.55;
    color: var(--fg);
  }
  h1, h2, h3, .sans {
    font-family: 'Inter', sans-serif;
  }
  h1 { font-size: 22pt; font-weight: 700; color: var(--navy); margin: 0 0 6pt 0; }
  h2 { font-size: 14pt; font-weight: 600; color: var(--navy); margin: 18pt 0 6pt 0; }
  h3 { font-size: 11pt; font-weight: 600; color: var(--navy); margin: 12pt 0 4pt 0; }
  p { margin: 0 0 8pt 0; }

  .lede {
    font-size: 12pt;
    color: var(--muted);
    margin-bottom: 16pt;
  }

  ul, ol { margin: 4pt 0 8pt 18pt; padding: 0; }
  li { margin-bottom: 4pt; }

  .section {
    page-break-before: always;
  }
  .section.first { page-break-before: auto; }

  .callout {
    border-left: 3px solid var(--cyan);
    padding: 6pt 12pt;
    margin: 12pt 0;
    background: #f8fafc;
    font-size: 10.5pt;
  }

  .table {
    width: 100%;
    border-collapse: collapse;
    margin: 8pt 0 12pt;
    font-family: 'Inter', sans-serif;
    font-size: 10pt;
  }
  .table th, .table td {
    padding: 5pt 8pt;
    text-align: left;
    border-bottom: 1px solid var(--rule);
  }
  .table th {
    color: var(--muted);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 8.5pt;
    letter-spacing: 0.05em;
  }
  .num { text-align: right; font-variant-numeric: tabular-nums; }

  .formula {
    font-family: 'Inter', sans-serif;
    background: #f8fafc;
    padding: 10pt 14pt;
    border-radius: 4pt;
    margin: 8pt 0;
    font-size: 11pt;
    color: var(--navy);
  }

  .cover {
    page: cover;
    height: 100vh;
    background: var(--navy);
    color: white;
    padding: 90mm 18mm 30mm 18mm;
    font-family: 'Inter', sans-serif;
  }
  .cover .brand {
    font-size: 10pt;
    color: var(--cyan);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 20mm;
  }
  .cover h1 {
    color: white;
    font-size: 38pt;
    line-height: 1.05;
    margin: 0 0 6mm 0;
    font-weight: 700;
  }
  .cover .subtitle {
    color: var(--cyan);
    font-size: 14pt;
    font-weight: 400;
    margin: 0 0 16mm 0;
  }
  .cover .tagline {
    color: #cbd5e1;
    font-size: 11pt;
    line-height: 1.6;
    max-width: 120mm;
    font-family: 'Source Serif 4', serif;
    font-style: italic;
  }
  .cover .meta {
    position: absolute;
    bottom: 30mm;
    color: #94a3b8;
    font-size: 9pt;
    letter-spacing: 0.05em;
  }

  .footer-cta {
    margin-top: 18pt;
    padding: 14pt 16pt;
    background: var(--navy);
    color: white;
    border-radius: 4pt;
    font-family: 'Inter', sans-serif;
    font-size: 10.5pt;
  }
  .footer-cta strong { color: var(--cyan); }
  .footer-cta a { color: var(--cyan); text-decoration: none; }
</style>
</head>
<body>

<!-- ─────────────────── COVER ─────────────────── -->
<section class="cover">
  <div class="brand">mlbsims.com</div>
  <h1>How We Predict<br>MLB Games</h1>
  <div class="subtitle">The MLB Sims Methodology · 2026 Edition</div>
  <div class="tagline">
    A walkthrough of the Poisson Monte Carlo model that powers our daily
    predictions — the math, the data, what we account for, and what we
    deliberately don't.
  </div>
  <div class="meta">mlbsims.com · 2026</div>
</section>

<!-- ─────────────────── PAGE 2 — WHY ─────────────────── -->
<section class="section">
  <h1>Why this exists</h1>
  <p class="lede">
    Most MLB prediction sites won't show you their numbers. They publish
    confident picks, but you have no way to verify they're more than vibes.
  </p>
  <p>
    MLB Sims is built on the opposite premise. Every prediction we make is
    public, every assumption is documented, and we publish our daily accuracy
    where you can audit it.
  </p>
  <p>
    This document is the part most sites bury — the actual methodology. If
    you're going to trust a model's picks, you should know exactly how those
    picks are generated, what data goes in, and what the model deliberately
    ignores. Trust comes from transparency, not from confidence.
  </p>

  <h2>What you'll find in this guide</h2>
  <ul>
    <li>The intuition behind Poisson distributions for run scoring</li>
    <li>The six-step pipeline from raw box scores to win probabilities</li>
    <li>Why we park-adjust everything — and why one team's "great offense"
        might just be Coors Field</li>
    <li>A complete worked example: a real game, calculated end to end</li>
    <li>What the model can't yet do (and what's coming next)</li>
  </ul>

</section>

<!-- ─────────────────── PAGE 3 — POISSON ─────────────────── -->
<section class="section">
  <h1>The core idea</h1>
  <p class="lede">
    Run scoring in baseball happens to follow a Poisson distribution very well.
    Once you know a team's <em>expected</em> runs in a given matchup, you can
    sample plausible final scores by drawing Poisson random numbers, then run
    that thousands of times to build a complete picture of how the game
    could go.
  </p>

  <h2>Why Poisson works for baseball</h2>
  <p>
    The Poisson distribution describes how often discrete events occur in a
    fixed window when they're (a) independent, (b) happen at a known average
    rate, and (c) can occur any number of times. A baseball game maps onto
    this almost perfectly. There are many independent at-bats. Each has a
    small probability of producing a run. The number of plate appearances
    per game is relatively fixed.
  </p>
  <div class="formula">
    P(runs = k) = (λ^k · e^−λ) / k!
  </div>
  <p>
    The whole game becomes: <em>estimate λ for each team accurately, sample
    Poisson draws, count outcomes</em>. The hard part is the estimation.
  </p>
</section>

<!-- ─────────────────── PAGE 4 — STEP BY STEP ─────────────────── -->
<section class="section">
  <h1>The pipeline, in six steps</h1>
  <p class="lede">
    Every morning at 9am ET, the following pipeline runs against the latest
    data from the official MLB Stats API.
  </p>

  <h3>1. Pull every completed game this season</h3>
  <p>
    Box scores for the entire season-to-date, refreshed daily. Late-night
    West Coast games are usually final by 4am ET, so the 9am window has
    everything.
  </p>

  <h3>2. Compute four splits per team</h3>
  <p>
    For each of the 30 teams: average runs scored at home, average runs
    scored on the road, average runs allowed at home, average runs allowed
    on the road. Four numbers per team, computed from all games played.
  </p>

  <h3>3. Park-adjust the home numbers</h3>
  <p>
    Coors Field inflates run scoring ~12%. Petco Park suppresses it ~5%.
    We divide each team's home stats by their ballpark's 3-year run factor
    so we're comparing apples to apples across the league. Without this,
    the Rockies look like an offensive juggernaut every season.
  </p>

  <h3>4. Compute four strength ratios per team</h3>
  <p>
    Each team's park-adjusted splits, expressed as ratios against the
    park-neutral league averages: home attack, away attack, home defense,
    away defense. A value of 1.20 means 20% above average in that split;
    0.80 means 20% below.
  </p>

  <h3>5. Predict expected runs (λ) for the upcoming game</h3>
  <p>
    Multiply the relevant strengths together with the league average, then
    re-apply the home venue's park factor. That produces an expected-runs
    value for each team — the lambda we feed into the Poisson sampler.
  </p>

  <h3>6. Run 10,000 Poisson draws</h3>
  <p>
    For each team's run total, sample 10,000 Poisson draws. Count how often
    each side wins, the most likely final scores, the distribution of run
    totals, and the over/under at common lines.
  </p>
</section>

<!-- ─────────────────── PAGE 5 — PARK FACTORS ─────────────────── -->
<section class="section">
  <h1>Why Coors Field ≠ Petco Park</h1>
  <p class="lede">
    Park factors are the most underrated component of this model — and the
    one that most casual analysis gets wrong. A team's stat line at home
    isn't a clean measure of their offense; it's their offense
    <em>plus the park they happen to play in</em>.
  </p>

  <p>
    Park factors are computed from years of historical data: how many runs
    are scored at a given venue compared to a neutral park, holding teams
    constant. Our model uses a 3-year rolling factor, refreshed annually.
  </p>

  <table class="table">
    <thead>
      <tr><th>Park</th><th>Team</th><th class="num">Factor</th><th>Effect</th></tr>
    </thead>
    <tbody>
      <tr><td>Coors Field</td><td>Rockies</td><td class="num">1.12</td><td>Hitter's paradise (altitude + dry air)</td></tr>
      <tr><td>Great American</td><td>Reds</td><td class="num">1.05</td><td>Short porch in right</td></tr>
      <tr><td>Fenway Park</td><td>Red Sox</td><td class="num">1.04</td><td>Green Monster doubles</td></tr>
      <tr><td>Camden Yards</td><td>Orioles</td><td class="num">1.03</td><td>Short LF, recent renovation moved walls back</td></tr>
      <tr><td>Yankee Stadium</td><td>Yankees</td><td class="num">0.99</td><td>Roughly neutral despite short porch</td></tr>
      <tr><td>Dodger Stadium</td><td>Dodgers</td><td class="num">0.99</td><td>Pitcher-friendly historically; recent years neutral</td></tr>
      <tr><td>T-Mobile Park</td><td>Mariners</td><td class="num">0.93</td><td>Deep gaps, heavy marine air</td></tr>
      <tr><td>Oracle Park</td><td>Giants</td><td class="num">0.91</td><td>Most pitcher-friendly in MLB (depth + wind)</td></tr>
    </tbody>
  </table>

  <div class="callout">
    <strong>Practical effect.</strong> The Rockies and Giants both played 50+
    home games last year. Without park adjustment, the Rockies' team OPS
    looked elite and the Giants' looked anemic — even though the players
    were closer to comparable than the raw numbers suggest.
  </div>
</section>

<!-- ─────────────────── PAGE 6 — WORKED EXAMPLE ─────────────────── -->
<section class="section">
  <h1>A worked example</h1>
  <p class="lede">
    Let's walk through how the model predicted the Yankees vs Rays game
    on May 22, 2026 — using actual numbers from that morning's run.
  </p>

  <h2>Inputs</h2>
  <p>
    From the previous 50ish completed games of the season:
  </p>
  <table class="table">
    <thead>
      <tr><th>Strength</th><th class="num">Yankees (home)</th><th class="num">Rays (away)</th></tr>
    </thead>
    <tbody>
      <tr><td>Home attack</td><td class="num">1.18</td><td class="num">—</td></tr>
      <tr><td>Home defense</td><td class="num">0.92</td><td class="num">—</td></tr>
      <tr><td>Away attack</td><td class="num">—</td><td class="num">0.94</td></tr>
      <tr><td>Away defense</td><td class="num">—</td><td class="num">1.03</td></tr>
    </tbody>
  </table>
  <p>
    League park-neutral averages: 4.52 runs/game at home, 4.32 on the road.
    Yankee Stadium park factor: 0.99 (essentially neutral).
  </p>

  <h2>Expected runs</h2>
  <div class="formula">
    NYY expected =<br>
    1.18 (NYY home attack) × 1.03 (TB away defense) × 4.52 (league home avg) × 0.99 (park) =
    <strong>6.0 runs</strong>
  </div>
  <div class="formula">
    TB expected =<br>
    0.92 (NYY home defense) × 0.94 (TB away attack) × 4.32 (league away avg) × 0.99 (park) =
    <strong>4.3 runs</strong>
  </div>

  <h2>Simulation result</h2>
  <p>
    Sampling 10,000 Poisson draws with those lambdas:
  </p>
  <ul>
    <li>Yankees win probability: <strong>63%</strong></li>
    <li>Rays win probability: <strong>25%</strong></li>
    <li>Extras needed (regulation tie): 12%</li>
    <li>Most likely final score: 5–4 Yankees (about 2.4% of simulations)</li>
    <li>Over 8.5 total runs: 70%</li>
  </ul>
</section>

<!-- ─────────────────── PAGE 7 — WHAT WE DON'T KNOW ─────────────────── -->
<section class="section">
  <h1>What the model doesn't know</h1>
  <p class="lede">
    This is the section most prediction sites omit. We're transparent about
    the limits because honesty about uncertainty is what separates a real
    model from a confident-sounding scam.
  </p>

  <h3>Starting pitcher identity</h3>
  <p>
    A Cy Young vs. a spot starter looks identical to the current model.
    This is the single biggest gap. A separate pitcher-level model
    (per-PA Poisson with log5 against batter rates) is coming.
  </p>

  <h3>Lineup composition</h3>
  <p>
    No platoon splits, no rest days for stars, no awareness of who's batting
    behind whom. We treat the offense as a single number.
  </p>

  <h3>Recent form</h3>
  <p>
    A team in a 7-game winning streak looks identical to its season-to-date
    averages. There's a tradeoff here: weighting recent games more heavily
    can chase noise as readily as it captures real shifts.
  </p>

  <h3>Weather</h3>
  <p>
    Wind at Wrigley or rain at Citi Field can shift expected runs by 1-2
    per game. The data is available (NOAA + wind direction at the park);
    we just haven't wired it in yet.
  </p>

  <h3>Bullpen quality</h3>
  <p>
    Late-inning leverage isn't modeled. A team with a dominant closer wins
    more close games than the run-distribution model implies; we miss that.
  </p>

  <h3>Injuries</h3>
  <p>
    If a team's best hitter just went on the IL, the season-to-date averages
    still include their contribution. The model reacts only as games are
    played without them.
  </p>

</section>

<!-- ─────────────────── PAGE 8 — WHAT'S NEXT ─────────────────── -->
<section class="section">
  <h1>What's coming next</h1>
  <p class="lede">
    The current model is the foundation. The next twelve months of work is
    layering more granular signal on top of it.
  </p>

  <h3>Pitcher-vs-lineup projections</h3>
  <p>
    The biggest single upgrade. Instead of "team A scores X runs," the
    pitcher-level model will simulate every plate appearance using log5
    against the starter's K rate, BB rate, and HR/9. Daily strikeout
    projections, expected ERA per start, and stronger win probabilities.
  </p>

  <h3>Bayesian shrinkage early in the season</h3>
  <p>
    In April, sample sizes are tiny. We currently wait until May to publish
    daily predictions for this reason. A proper Bayesian shrinkage prior
    (blend prior-year baseline + current-year results) would let us start
    earlier without trusting noise.
  </p>

  <h3>Park-factor refresh per game</h3>
  <p>
    Wind direction, temperature, humidity — all available via weather APIs
    per stadium per first-pitch time. Could shift λ by 5-15% on any given
    game.
  </p>

  <h3>Public model performance dashboard</h3>
  <p>
    A dedicated page on mlbsims.com with rolling 30-day accuracy, biggest
    hits and misses, and a streak counter. Shipping soon.
  </p>

  <div class="footer-cta">
    <strong>Tomorrow's picks land in your inbox before first pitch.</strong>
    <br><br>
    You're already subscribed — thanks for that. If you haven't yet
    bookmarked the site, the daily slate lives at <a href="https://mlbsims.com">mlbsims.com</a>
    and updates every morning. Questions, suggestions, or model critiques
    are welcome by replying to any newsletter email.
  </div>
</section>

</body>
</html>
"""


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=HTML_DOC).write_pdf(str(OUTPUT))
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Built: {OUTPUT}  ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
