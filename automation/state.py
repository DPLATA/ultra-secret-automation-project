"""SQLite-backed dedup store.

Two responsibilities:
 1. `clips`: which play_ids have already been downloaded (so we never re-fetch
    a clip across daily runs).
 2. `compilations`: which compilation videos have already been built / queued
    for upload (so we never publish the same reel twice).

The DB is intentionally schemaless beyond these two tables — no ORM, no
migrations framework. If a column needs adding, do it in `init`.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    play_id           TEXT PRIMARY KEY,
    game_pk           INTEGER NOT NULL,
    game_date         TEXT NOT NULL,
    pitcher_name      TEXT NOT NULL,
    pitch_name        TEXT NOT NULL,
    call_type         TEXT NOT NULL,
    landscape_path    TEXT NOT NULL,
    portrait_path     TEXT NOT NULL,
    downloaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_clips_pitcher_date
    ON clips(pitcher_name, downloaded_at);

CREATE TABLE IF NOT EXISTS compilations (
    id                TEXT PRIMARY KEY,    -- e.g. "Marcus Stroman|2026-05-16|long"
    pitcher_name      TEXT NOT NULL,
    run_date          TEXT NOT NULL,
    kind              TEXT NOT NULL,       -- "long" | "short"
    pitch_name        TEXT,                -- NULL for "long"
    output_path       TEXT NOT NULL,
    title             TEXT,
    description       TEXT,
    tags              TEXT,                -- json list
    upload_status     TEXT NOT NULL DEFAULT 'pending',
    uploaded_at       TEXT,                -- ISO timestamp when uploaded
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comp_upload_status
    ON compilations(upload_status);
CREATE INDEX IF NOT EXISTS idx_comp_uploaded_at
    ON compilations(uploaded_at);
"""


class State:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- clips ----------------------------------------------------------

    def has_play(self, play_id: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM clips WHERE play_id = ?", (play_id,)).fetchone()
            return row is not None

    def record_clip(
        self,
        play_id: str,
        game_pk: int,
        game_date: str,
        pitcher_name: str,
        pitch_name: str,
        call_type: str,
        landscape_path: str,
        portrait_path: str,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO clips
                   (play_id, game_pk, game_date, pitcher_name, pitch_name, call_type,
                    landscape_path, portrait_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    play_id, game_pk, game_date, pitcher_name, pitch_name, call_type,
                    landscape_path, portrait_path,
                ),
            )

    def clips_for_pitcher_since(
        self, pitcher_name: str, since_iso_date: str, call_type: Optional[str] = None
    ) -> list[sqlite3.Row]:
        query = (
            "SELECT * FROM clips WHERE pitcher_name = ? "
            "AND downloaded_at >= ?"
        )
        params: list = [pitcher_name, since_iso_date]
        if call_type is not None:
            query += " AND call_type = ?"
            params.append(call_type)
        query += " ORDER BY downloaded_at ASC"
        with self._conn() as c:
            return c.execute(query, params).fetchall()

    # ---- compilations ---------------------------------------------------

    def has_compilation(self, compilation_id: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM compilations WHERE id = ?", (compilation_id,)
            ).fetchone()
            return row is not None

    def record_compilation(
        self,
        compilation_id: str,
        pitcher_name: str,
        run_date: str,
        kind: str,
        pitch_name: Optional[str],
        output_path: str,
        title: str,
        description: str,
        tags_json: str,
    ) -> None:
        """Insert a new compilation row, or refresh metadata/path on an
        existing one WITHOUT clobbering upload_status. Re-runs that rebuild
        a compilation file must not re-queue an already-published video.
        """
        with self._conn() as c:
            existing = c.execute(
                "SELECT upload_status FROM compilations WHERE id = ?",
                (compilation_id,),
            ).fetchone()
            if existing is None:
                c.execute(
                    """INSERT INTO compilations
                       (id, pitcher_name, run_date, kind, pitch_name,
                        output_path, title, description, tags, upload_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                    (
                        compilation_id, pitcher_name, run_date, kind, pitch_name,
                        output_path, title, description, tags_json,
                    ),
                )
            else:
                c.execute(
                    """UPDATE compilations SET
                           pitcher_name = ?, run_date = ?, kind = ?,
                           pitch_name = ?, output_path = ?, title = ?,
                           description = ?, tags = ?
                       WHERE id = ?""",
                    (
                        pitcher_name, run_date, kind, pitch_name, output_path,
                        title, description, tags_json, compilation_id,
                    ),
                )

    def pending_uploads(self, kind: Optional[str] = None) -> list[sqlite3.Row]:
        """Return pending compilations, newest game-date first.

        Newest first so when quota is tight we upload the freshest content;
        older clips can wait or be dropped without much loss.
        """
        query = "SELECT * FROM compilations WHERE upload_status = 'pending'"
        params: list = []
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY run_date DESC, created_at ASC"
        with self._conn() as c:
            return c.execute(query, params).fetchall()

    def mark_uploaded(self, compilation_id: str, video_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE compilations SET upload_status = ?, uploaded_at = datetime('now') "
                "WHERE id = ?",
                (f"uploaded:{video_id}", compilation_id),
            )

    def uploads_today(self, kind: Optional[str] = None) -> int:
        query = (
            "SELECT COUNT(*) FROM compilations "
            "WHERE upload_status LIKE 'uploaded:%' "
            "AND date(uploaded_at) = date('now')"
        )
        params: list = []
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        with self._conn() as c:
            return c.execute(query, params).fetchone()[0]
