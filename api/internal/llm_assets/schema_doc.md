# pitches table — schema documentation

This document is embedded into the LLM's system prompt. Keep it in sync with
`db/alembic/versions/0001_initial_pitches_schema.py`.

**One table only: `pitches`.** Every row is one MLB pitch from the 2026 season,
sourced from baseballsavant Statcast. Updated daily. ~5,000 rows per day.

There is **no separate `players` or `teams` table.** Every needed value is a
column on `pitches`. If you can't see a column listed below, it does NOT exist.

---

## Composite primary key

| Column | Type | Description |
|---|---|---|
| `game_pk` | BIGINT | MLB game identifier (~6-digit integer) |
| `at_bat_number` | INTEGER | 1..N within a game, sequential |
| `pitch_number` | INTEGER | 1..K within an at-bat, sequential |

## Game / date / teams

| Column | Type | Description |
|---|---|---|
| `game_date` | DATE | The date of the game (in stadium local time) |
| `game_year` | INTEGER | Calendar year, e.g. 2026 |
| `game_type` | TEXT | `R`=regular, `F`=wildcard, `D`=division, `L`=LCS, `W`=WS, `S`=spring |
| `home_team` | TEXT | 3-letter team abbr; see Team Abbreviations below |
| `away_team` | TEXT | 3-letter team abbr |
| `inning` | INTEGER | 1..9+ |
| `inning_topbot` | TEXT | `Top` = away team batting, `Bot` = home team batting |

**No `team` column. No `pitcher_team` column.** To find pitches thrown by a
specific team's pitchers, see "Pitcher's Team" convention below.

## Pitch identity

| Column | Type | Description |
|---|---|---|
| `pitch_type` | TEXT | 2-letter code (FF, SL, CH, etc.) — usually use `pitch_name` instead |
| `pitch_name` | TEXT | Human-readable name. See Pitch Names below |
| `type` | TEXT | `S`=strike, `B`=ball, `X`=in play |
| `description` | TEXT | Pitch outcome — see Description Values below |
| `events` | TEXT | At-bat outcome — NULL except on the terminal pitch. See Event Values |
| `des` | TEXT | Plain-English play description, e.g. "Aaron Judge homers (15) on a fly ball" |
| `zone` | INTEGER | 1-9 = in strike zone (3×3 grid), 11-14 = ball outside zone |

## Pitcher and batter

| Column | Type | Description |
|---|---|---|
| `player_name` | TEXT | **The PITCHER's name**, formatted `Last, First` (e.g. `Skenes, Paul`) |
| `pitcher` | INTEGER | Pitcher MLB ID |
| `batter` | INTEGER | Batter MLB ID |
| `p_throws` | TEXT | Pitcher handedness: `L` or `R` |
| `stand` | TEXT | Batter handedness ("stance"): `L` or `R` |

**There is NO batter name column.** Only the pitcher's name appears as
`player_name`. Batter is just an ID. To filter by "left-handed batters" use
`stand = 'L'`.

## Pitch physics

| Column | Type | Description |
|---|---|---|
| `release_speed` | DOUBLE | MPH at release (e.g. `97.4`). Often called "velocity" or "velo" |
| `release_spin_rate` | INTEGER | RPM at release. Often NULL |
| `release_pos_x`, `release_pos_y`, `release_pos_z` | DOUBLE | Release point in feet (catcher's POV) |
| `release_extension` | DOUBLE | Feet of extension toward home plate |
| `effective_speed` | DOUBLE | Perceived MPH (release_speed × extension factor) |
| `spin_axis` | INTEGER | Spin axis in degrees (0-360) |
| `pfx_x`, `pfx_z` | DOUBLE | Horizontal / vertical movement in feet at the plate |
| `plate_x`, `plate_z` | DOUBLE | Horizontal / vertical pitch location at the plate (feet from center) |
| `vx0`, `vy0`, `vz0` | DOUBLE | Velocity components at release point |
| `ax`, `ay`, `az` | DOUBLE | Acceleration components |
| `sz_top`, `sz_bot` | DOUBLE | Strike zone top / bottom for this batter (feet) |
| `api_break_z_with_gravity` | DOUBLE | Vertical break including gravity |
| `api_break_x_arm` | DOUBLE | Horizontal break, arm-side |
| `api_break_x_batter_in` | DOUBLE | Horizontal break, into the batter |
| `arm_angle` | DOUBLE | Pitcher arm angle in degrees |

## Count + situation

| Column | Type | Description |
|---|---|---|
| `balls`, `strikes` | INTEGER | Count BEFORE this pitch |
| `outs_when_up` | INTEGER | Outs in the inning before this at-bat |
| `on_1b`, `on_2b`, `on_3b` | INTEGER | Runner MLB ID if base occupied, else NULL |
| `if_fielding_alignment` | TEXT | `Standard`, `Strategic`, `Infield shift` |
| `of_fielding_alignment` | TEXT | Outfield alignment |

## Contact / hit data

(Only populated when the pitch is hit into play — `description = 'hit_into_play'`)

| Column | Type | Description |
|---|---|---|
| `bb_type` | TEXT | Batted ball type: `fly_ball`, `ground_ball`, `line_drive`, `popup` |
| `hit_location` | INTEGER | Fielder who fielded the ball (1=P, 2=C, 3=1B, ..., 9=RF) |
| `launch_speed` | DOUBLE | Exit velocity MPH |
| `launch_angle` | INTEGER | Launch angle in degrees |
| `launch_speed_angle` | INTEGER | 1-6 sweet-spot bucket (6 = barrel) |
| `hit_distance_sc` | INTEGER | Distance in feet |
| `hc_x`, `hc_y` | DOUBLE | Where the ball landed in the spray chart |

## Swing data (when batter swings)

| Column | Type | Description |
|---|---|---|
| `bat_speed` | DOUBLE | Bat speed at contact in MPH |
| `swing_length` | DOUBLE | Distance bat traveled in feet |
| `attack_angle` | DOUBLE | Bat angle at contact, degrees |
| `swing_path_tilt` | DOUBLE | Bat path tilt, degrees |

## Score and win expectancy

| Column | Type | Description |
|---|---|---|
| `home_score`, `away_score` | INTEGER | Score before this pitch |
| `post_home_score`, `post_away_score` | INTEGER | Score after this pitch |
| `bat_score`, `fld_score` | INTEGER | Score for batting / fielding team |
| `home_win_exp` | DOUBLE | Probability home team wins (0..1) before this pitch |
| `delta_home_win_exp` | DOUBLE | Change in home win prob caused by this pitch |
| `delta_run_exp` | DOUBLE | Change in run expectancy this pitch (run units) |
| `delta_pitcher_run_exp` | DOUBLE | Same, from the pitcher's perspective |

## Expected stats (Statcast model outputs)

| Column | Type | Description |
|---|---|---|
| `estimated_ba_using_speedangle` | DOUBLE | xBA — expected batting avg of this batted ball |
| `estimated_woba_using_speedangle` | DOUBLE | xwOBA |
| `estimated_slg_using_speedangle` | DOUBLE | xSLG |
| `woba_value`, `woba_denom` | DOUBLE/INT | Actual wOBA numerator and denominator |

## Fielders (rarely useful)

`fielder_2` through `fielder_9` — MLB IDs of the fielders at each position
during this pitch.

## Audit

| Column | Type | Description |
|---|---|---|
| `loaded_at` | TIMESTAMPTZ | When our pipeline pulled this row |

---

## Team Abbreviations

`home_team` and `away_team` use these 3-letter codes. Common questions about
"the Yankees" need to filter on `'NYY'`.

| Code | Team | Code | Team |
|---|---|---|---|
| ARI / **AZ** | Diamondbacks (AZ in 2026) | MIA | Marlins |
| ATL | Braves | MIL | Brewers |
| **ATH** | Athletics (ATH since 2026 Sacramento move) | MIN | Twins |
| BAL | Orioles | NYM | Mets |
| BOS | Red Sox | NYY | Yankees |
| CHC | Cubs | PHI | Phillies |
| CIN | Reds | PIT | Pirates |
| CLE | Guardians | SD | Padres |
| COL | Rockies | SEA | Mariners |
| CWS | White Sox | SF | Giants |
| DET | Tigers | STL | Cardinals |
| HOU | Astros | TB | Rays |
| KC | Royals | TEX | Rangers |
| LAA | Angels | TOR | Blue Jays |
| LAD | Dodgers | WSH | Nationals |

**Use `AZ` not `ARI`** and **`ATH` not `OAK`** in 2026 data.

---

## Pitch Names

`pitch_name` uses these exact strings. Group them as needed:

- **Fastballs:** `4-Seam Fastball`, `Sinker`, `Cutter`
- **Breaking balls:** `Slider`, `Curveball`, `Sweeper`, `Knuckle Curve`, `Slurve`
- **Offspeed:** `Changeup`, `Split-Finger`, `Forkball`, `Screwball`

---

## Description Values (`description` column)

Pitch-level outcomes:

- `ball`, `called_strike`, `swinging_strike`, `swinging_strike_blocked`
- `foul`, `foul_tip`, `foul_bunt`
- `hit_into_play`
- `blocked_ball`, `pitchout`, `hit_by_pitch`
- `missed_bunt`

A whiff = `description IN ('swinging_strike', 'swinging_strike_blocked')`.

---

## Event Values (`events` column)

At-bat outcomes (NULL on non-terminal pitches). Common values:

`single`, `double`, `triple`, `home_run`, `walk`, `strikeout`,
`field_out`, `force_out`, `grounded_into_double_play`, `sac_fly`,
`hit_by_pitch`, `field_error`, `intent_walk`, `caught_stealing_2b`,
`pickoff_1b`, `wild_pitch`, `passed_ball`

**To find at-bat results, ALWAYS filter `WHERE events IS NOT NULL`.**

---

## Critical domain conventions the LLM must respect

### Convention 1 — Pitcher's team

There is **no `pitcher_team` column.** To find pitches thrown by a team's
pitchers, infer from inning + which side is at bat:

```sql
-- Pitches thrown BY Blue Jays pitchers (defense = TOR)
WHERE (home_team = 'TOR' AND inning_topbot = 'Top')
   OR (away_team = 'TOR' AND inning_topbot = 'Bot')
```

Same logic for any team. The pitcher's team is whichever team is on defense.
Convention: when `inning_topbot = 'Top'`, home team's pitcher is on the mound.

### Convention 2 — Batter's team

Symmetric to above:

```sql
-- Pitches thrown TO Yankees batters (offense = NYY)
WHERE (home_team = 'NYY' AND inning_topbot = 'Bot')
   OR (away_team = 'NYY' AND inning_topbot = 'Top')
```

### Convention 3 — League (AL vs NL)

There is **no league column.** To filter to American League, list the
abbreviations: `home_team IN ('NYY','BOS','TB','TOR','BAL','CLE','MIN','CWS','DET','KC','HOU','TEX','SEA','LAA','ATH')`.
National League is the other 15 teams.

### Convention 4 — "This season"

The table only contains 2026 data. **Do NOT add date filters like
`game_date >= '2026-03-01'` for "this season" — it's redundant noise.**
Only add `game_date` filters when the question specifically scopes to a
date range or "last N days".

### Convention 5 — "Yesterday" and recency

`CURRENT_DATE` works in Postgres. "Yesterday" = `game_date = CURRENT_DATE - 1`.
"This week" = `game_date >= CURRENT_DATE - 7`. Data updates daily so today's
games-in-progress may not be present.

### Convention 6 — Strikeouts and other at-bat outcomes

Strikeouts are at-bat-level events, so filter `events = 'strikeout'`. The
pitch with `events = 'strikeout'` is the terminal pitch (the called/swinging
strike that ended the at-bat). One row per K.

### Convention 7 — Player names

`player_name` is the PITCHER, in `Last, First` format (e.g. `Skenes, Paul`,
`Cease, Dylan`). When the user names a pitcher, use this format. Use
`ILIKE 'Last%'` for case-insensitive prefix match if unsure of full spelling.

### Convention 8 — Whiff rate

`100.0 * sum(CASE WHEN description = 'swinging_strike' THEN 1 ELSE 0 END) / count(*)`

per pitch type or per pitcher.

---

## Output contract

Respond with **raw SQL only**. No markdown fences. No commentary.
The query must:
- Start with `SELECT` or `WITH`
- Be a single statement (no semicolons in the middle)
- Never use INSERT/UPDATE/DELETE/DROP/etc.
- Reference only columns listed above — **do not invent column names**
- Include a reasonable LIMIT (10-25) unless the question asks for a count or aggregate
