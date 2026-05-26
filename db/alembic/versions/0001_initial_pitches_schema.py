"""Initial pitches table — full Statcast schema (118 columns)

Revision ID: 0001
Revises:
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Composite primary key: every Statcast pitch is uniquely identified by
# (game_pk, at_bat_number, pitch_number). All three are NOT NULL from the
# source data; the others are nullable since deprecated columns and some
# situational fields (on_1b, hit_location, etc.) are routinely missing.
CREATE_TABLE_SQL = """
CREATE TABLE pitches (
    -- Composite primary key
    game_pk           BIGINT  NOT NULL,
    at_bat_number     INTEGER NOT NULL,
    pitch_number      INTEGER NOT NULL,

    -- Game / date / teams
    game_date         DATE    NOT NULL,
    game_year         INTEGER,
    game_type         TEXT,
    home_team         TEXT,
    away_team         TEXT,
    inning            INTEGER,
    inning_topbot     TEXT,

    -- Pitch identity
    pitch_type        TEXT,
    pitch_name        TEXT,
    type              TEXT,
    description       TEXT,
    events            TEXT,
    des               TEXT,
    zone              INTEGER,

    -- Pitcher / batter
    player_name       TEXT,
    pitcher           INTEGER,
    batter            INTEGER,
    p_throws          TEXT,
    stand             TEXT,

    -- Pitch physics
    release_speed     DOUBLE PRECISION,
    release_pos_x     DOUBLE PRECISION,
    release_pos_y     DOUBLE PRECISION,
    release_pos_z     DOUBLE PRECISION,
    release_extension DOUBLE PRECISION,
    release_spin_rate INTEGER,
    effective_speed   DOUBLE PRECISION,
    spin_axis         INTEGER,
    pfx_x             DOUBLE PRECISION,
    pfx_z             DOUBLE PRECISION,
    plate_x           DOUBLE PRECISION,
    plate_z           DOUBLE PRECISION,
    vx0               DOUBLE PRECISION,
    vy0               DOUBLE PRECISION,
    vz0               DOUBLE PRECISION,
    ax                DOUBLE PRECISION,
    ay                DOUBLE PRECISION,
    az                DOUBLE PRECISION,
    sz_top            DOUBLE PRECISION,
    sz_bot            DOUBLE PRECISION,
    api_break_z_with_gravity DOUBLE PRECISION,
    api_break_x_arm          DOUBLE PRECISION,
    api_break_x_batter_in    DOUBLE PRECISION,
    arm_angle         DOUBLE PRECISION,

    -- Count / situational state
    balls             INTEGER,
    strikes           INTEGER,
    outs_when_up      INTEGER,
    on_1b             INTEGER,
    on_2b             INTEGER,
    on_3b             INTEGER,
    if_fielding_alignment TEXT,
    of_fielding_alignment TEXT,

    -- Contact / hit data
    bb_type           TEXT,
    hit_location      INTEGER,
    hit_distance_sc   INTEGER,
    launch_speed      DOUBLE PRECISION,
    launch_angle      INTEGER,
    launch_speed_angle INTEGER,
    hc_x              DOUBLE PRECISION,
    hc_y              DOUBLE PRECISION,
    hyper_speed       DOUBLE PRECISION,

    -- Swing data
    bat_speed         DOUBLE PRECISION,
    swing_length      DOUBLE PRECISION,
    attack_angle      DOUBLE PRECISION,
    attack_direction  DOUBLE PRECISION,
    swing_path_tilt   DOUBLE PRECISION,
    intercept_ball_minus_batter_pos_x_inches DOUBLE PRECISION,
    intercept_ball_minus_batter_pos_y_inches DOUBLE PRECISION,

    -- Defense / fielders
    fielder_2         INTEGER,
    fielder_3         INTEGER,
    fielder_4         INTEGER,
    fielder_5         INTEGER,
    fielder_6         INTEGER,
    fielder_7         INTEGER,
    fielder_8         INTEGER,
    fielder_9         INTEGER,

    -- Expected stats
    estimated_ba_using_speedangle      DOUBLE PRECISION,
    estimated_woba_using_speedangle    DOUBLE PRECISION,
    estimated_slg_using_speedangle     DOUBLE PRECISION,
    woba_value        DOUBLE PRECISION,
    woba_denom        INTEGER,
    babip_value       INTEGER,
    iso_value         INTEGER,

    -- Score / win expectancy
    home_score        INTEGER,
    away_score        INTEGER,
    bat_score         INTEGER,
    fld_score         INTEGER,
    post_home_score   INTEGER,
    post_away_score   INTEGER,
    post_bat_score    INTEGER,
    post_fld_score    INTEGER,
    home_score_diff   INTEGER,
    bat_score_diff    INTEGER,
    home_win_exp      DOUBLE PRECISION,
    bat_win_exp       DOUBLE PRECISION,
    delta_home_win_exp DOUBLE PRECISION,
    delta_run_exp     DOUBLE PRECISION,
    delta_pitcher_run_exp DOUBLE PRECISION,

    -- Player meta
    age_pit           INTEGER,
    age_bat           INTEGER,
    age_pit_legacy    INTEGER,
    age_bat_legacy    INTEGER,
    n_thruorder_pitcher INTEGER,
    n_priorpa_thisgame_player_at_bat INTEGER,
    pitcher_days_since_prev_game  INTEGER,
    batter_days_since_prev_game   INTEGER,
    pitcher_days_until_next_game  INTEGER,
    batter_days_until_next_game   INTEGER,

    -- Deprecated / often-null (kept for completeness, no indexes)
    spin_dir                INTEGER,
    spin_rate_deprecated    INTEGER,
    break_angle_deprecated  INTEGER,
    break_length_deprecated INTEGER,
    tfs_deprecated          INTEGER,
    tfs_zulu_deprecated     INTEGER,
    umpire                  INTEGER,
    sv_id                   INTEGER,

    -- Audit
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (game_pk, at_bat_number, pitch_number)
);
"""

INDEXES_SQL = """
CREATE INDEX idx_pitches_game_date ON pitches (game_date);
CREATE INDEX idx_pitches_pitcher   ON pitches (pitcher);
CREATE INDEX idx_pitches_batter    ON pitches (batter);
CREATE INDEX idx_pitches_pitch_type ON pitches (pitch_type);
CREATE INDEX idx_pitches_events    ON pitches (events) WHERE events IS NOT NULL;
CREATE INDEX idx_pitches_game_pk   ON pitches (game_pk);
"""

# Reader gets SELECT only (future LLM query layer); writer gets full DML.
# Default privileges ensure these grants apply to any future tables too.
GRANTS_SQL = """
GRANT USAGE ON SCHEMA public TO mlbsims_reader, mlbsims_writer;
GRANT SELECT ON pitches TO mlbsims_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON pitches TO mlbsims_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mlbsims_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mlbsims_writer;
"""


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    op.execute(INDEXES_SQL)
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pitches;")
