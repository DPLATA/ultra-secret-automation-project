# pitches table — schema documentation for the LLM

> This document is embedded into the Anthropic system prompt at build time.
> Keep it up to date when migrations change the schema.

The `pitches` table contains every Statcast pitch from the 2026 MLB season.
Updated daily.

## Composite primary key
- `game_pk` (BIGINT) — MLB game identifier
- `at_bat_number` (INTEGER) — sequential within a game (1..N)
- `pitch_number` (INTEGER) — sequential within an at-bat (1..K)

## Most queried columns
(TODO: fill in. Should include short, accurate descriptions of every column
that's likely to appear in user questions. See:
    db/alembic/versions/0001_initial_pitches_schema.py
for the full column list with types.)

## Domain conventions the LLM must respect
- `player_name` is the PITCHER name in `Last, First` format (e.g. `Skenes, Paul`).
- `pitcher` and `batter` are integer player IDs from MLB Stats API.
- `events` is NULL except on the terminal pitch of an at-bat. To find at-bat
  outcomes, filter `WHERE events IS NOT NULL`.
- `description` is the pitch-level outcome (e.g. `swinging_strike`,
  `called_strike`, `foul`, `hit_into_play`, `ball`).
- `release_spin_rate` is in RPM; NULL when not measured.
- `release_speed` is in MPH.
- `game_date` is a real DATE — use date arithmetic / range filters.
- Pitch type families:
  - Fastballs: `4-Seam Fastball`, `Sinker`, `Cutter`
  - Breaking balls: `Slider`, `Curveball`, `Sweeper`, `Knuckle Curve`, `Slurve`
  - Offspeed: `Changeup`, `Split-Finger`, `Screwball`, `Forkball`
- Data freshness: refreshed daily at 7am and 12pm EDT. "Today's games" may not
  be in the table yet — when in doubt, filter `<= CURRENT_DATE - 1` for safety.

## Output contract
Respond with **raw SQL only**. No markdown fences. No explanation.
The query must:
- Start with SELECT or WITH
- Be a single statement (no semicolons except optionally at the end)
- Not use INSERT/UPDATE/DELETE/DROP/etc.
