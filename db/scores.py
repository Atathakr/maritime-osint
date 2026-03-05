# db/scores.py
"""
Vessel risk score persistence — Phase 2 implementation.

Public functions (all re-exported from db/__init__.py):
    init_scores_tables()        — DDL: create vessel_scores + vessel_score_history
    upsert_vessel_score()       — INSERT OR REPLACE with is_stale reset
    get_vessel_score()          — single-row lookup; indicator_json returned as dict
    get_all_vessel_scores()     — JOIN query, no per-vessel loop
    mark_risk_scores_stale()    — bulk UPDATE is_stale=1
    append_score_history()      — INSERT into history table
    prune_score_history()       — DELETE rows older than N days
    archive_old_ais_positions() — DELETE ais_positions rows older than N days

Constants:
    SCORE_STALENESS_MINUTES     — 30 (hardcoded per 02-CONTEXT.md)
    SCHEDULER_ADVISORY_LOCK_ID  — 42 (documents the pg_try_advisory_xact_lock ID used in app.py)
"""

import json as _json
from datetime import datetime, timezone

from .connection import _BACKEND, _conn, _cursor, _rows, _ph, _jp

# ── Constants ─────────────────────────────────────────────────────────────────

SCORE_STALENESS_MINUTES = 30        # no env var — hardcoded per 02-CONTEXT.md
SCHEDULER_ADVISORY_LOCK_ID = 42     # documents the advisory lock ID used in app.py scheduler


# ── DDL ───────────────────────────────────────────────────────────────────────

def init_scores_tables() -> None:
    """Create vessel_scores and vessel_score_history tables (idempotent)."""
    if _BACKEND == "postgres":
        _init_scores_postgres()
    else:
        _init_scores_sqlite()


def _init_scores_postgres() -> None:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS vessel_scores (
                imo_number      VARCHAR(20) PRIMARY KEY,
                composite_score INTEGER      NOT NULL DEFAULT 0,
                is_sanctioned   SMALLINT     NOT NULL DEFAULT 0,
                indicator_json  JSONB        NOT NULL DEFAULT '{}',
                computed_at     TIMESTAMPTZ  NOT NULL,
                is_stale        SMALLINT     NOT NULL DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS vessel_score_history (
                id              BIGSERIAL PRIMARY KEY,
                imo_number      VARCHAR(20) NOT NULL,
                composite_score INTEGER     NOT NULL,
                is_sanctioned   SMALLINT    NOT NULL DEFAULT 0,
                computed_at     TIMESTAMPTZ NOT NULL
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_vsh_imo ON vessel_score_history(imo_number)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_vsh_at  ON vessel_score_history(computed_at DESC)"
        )


def _init_scores_sqlite() -> None:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS vessel_scores (
                imo_number      TEXT PRIMARY KEY,
                composite_score INTEGER NOT NULL DEFAULT 0,
                is_sanctioned   INTEGER NOT NULL DEFAULT 0,
                indicator_json  TEXT    NOT NULL DEFAULT '{}',
                computed_at     TEXT    NOT NULL,
                is_stale        INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS vessel_score_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                imo_number      TEXT    NOT NULL,
                composite_score INTEGER NOT NULL,
                is_sanctioned   INTEGER NOT NULL DEFAULT 0,
                computed_at     TEXT    NOT NULL
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_vsh_imo ON vessel_score_history(imo_number)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_vsh_at  ON vessel_score_history(computed_at DESC)"
        )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def upsert_vessel_score(imo: str, score_data: dict) -> None:
    """
    Insert or update a vessel risk score row.

    score_data keys:
        composite_score (int)
        is_sanctioned   (bool | int)
        indicator_json  (dict)       — serialised to JSON string / JSONB
        computed_at     (str)        — ISO 8601 UTC; defaults to now() if omitted

    is_stale is always reset to 0 on upsert.
    """
    composite_score = int(score_data.get("composite_score", 0))
    is_sanctioned = int(bool(score_data.get("is_sanctioned", 0)))
    indicator_json_raw = score_data.get("indicator_json", {})
    indicator_json_str = _json.dumps(indicator_json_raw)
    computed_at = score_data.get("computed_at") or datetime.now(timezone.utc).isoformat()

    if _BACKEND == "postgres":
        sql = f"""
            INSERT INTO vessel_scores
                (imo_number, composite_score, is_sanctioned, indicator_json, computed_at, is_stale)
            VALUES (%s, %s, %s, {_jp()}, %s, 0)
            ON CONFLICT (imo_number) DO UPDATE SET
                composite_score = EXCLUDED.composite_score,
                is_sanctioned   = EXCLUDED.is_sanctioned,
                indicator_json  = EXCLUDED.indicator_json,
                computed_at     = EXCLUDED.computed_at,
                is_stale        = 0
        """
    else:
        sql = f"""
            INSERT INTO vessel_scores
                (imo_number, composite_score, is_sanctioned, indicator_json, computed_at, is_stale)
            VALUES (?, ?, ?, {_jp()}, ?, 0)
            ON CONFLICT (imo_number) DO UPDATE SET
                composite_score = excluded.composite_score,
                is_sanctioned   = excluded.is_sanctioned,
                indicator_json  = excluded.indicator_json,
                computed_at     = excluded.computed_at,
                is_stale        = 0
        """

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, (imo, composite_score, is_sanctioned, indicator_json_str, computed_at))


def get_vessel_score(imo: str) -> dict | None:
    """
    Return the vessel_scores row for the given IMO, or None if not found.

    indicator_json is always returned as a dict (never a raw JSON string).
    """
    if _BACKEND == "postgres":
        sql = "SELECT * FROM vessel_scores WHERE imo_number = %s"
    else:
        sql = "SELECT * FROM vessel_scores WHERE imo_number = ?"

    with _conn() as conn:
        c = _cursor(conn)
        c.execute(sql, (imo,))
        row = c.fetchone()
        if row is None:
            return None
        row = dict(row)

    # Normalise: SQLite stores indicator_json as TEXT
    if isinstance(row.get("indicator_json"), str):
        row["indicator_json"] = _json.loads(row["indicator_json"])

    return row


def get_all_vessel_scores() -> list[dict]:
    """
    Return all vessel scores joined with canonical vessel info and latest AIS data.

    Uses a single JOIN — no per-vessel query loop.
    Results ordered by composite_score DESC.
    indicator_json is normalised to dict for each row.
    """
    sql = """
        SELECT
            vs.imo_number,
            vs.composite_score,
            vs.is_sanctioned,
            vs.indicator_json,
            vs.computed_at,
            vs.is_stale,
            vc.entity_name,
            vc.flag_normalized,
            vc.vessel_type,
            av.mmsi,
            av.last_lat,
            av.last_lon,
            av.last_seen
        FROM vessel_scores vs
        JOIN vessels_canonical vc USING (imo_number)
        LEFT JOIN ais_vessels av ON vc.mmsi = av.mmsi
        ORDER BY vs.composite_score DESC
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(sql)
        rows = _rows(c)

    # Normalise indicator_json for every row
    for row in rows:
        if isinstance(row.get("indicator_json"), str):
            row["indicator_json"] = _json.loads(row["indicator_json"])

    return rows


def mark_risk_scores_stale(imo_numbers: list[str]) -> int:
    """
    Set is_stale=1 for every IMO in imo_numbers.

    Returns the count of rows updated. Returns 0 immediately for an empty list.
    """
    if not imo_numbers:
        return 0

    placeholders = _ph(len(imo_numbers))
    if _BACKEND == "postgres":
        sql = f"UPDATE vessel_scores SET is_stale = 1 WHERE imo_number IN ({placeholders})"
    else:
        sql = f"UPDATE vessel_scores SET is_stale = 1 WHERE imo_number IN ({placeholders})"

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, list(imo_numbers))
        return c.rowcount


def append_score_history(imo: str, score_data: dict) -> None:
    """
    Insert a history snapshot row into vessel_score_history.

    Only stores composite_score, is_sanctioned, and computed_at — no indicator_json
    (keeps history table small per 02-CONTEXT.md design decision).
    """
    composite_score = int(score_data.get("composite_score", 0))
    is_sanctioned = int(bool(score_data.get("is_sanctioned", 0)))
    computed_at = score_data.get("computed_at") or datetime.now(timezone.utc).isoformat()

    if _BACKEND == "postgres":
        sql = """
            INSERT INTO vessel_score_history (imo_number, composite_score, is_sanctioned, computed_at)
            VALUES (%s, %s, %s, %s)
        """
    else:
        sql = """
            INSERT INTO vessel_score_history (imo_number, composite_score, is_sanctioned, computed_at)
            VALUES (?, ?, ?, ?)
        """

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, (imo, composite_score, is_sanctioned, computed_at))


def prune_score_history(days: int = 90) -> int:
    """
    Delete vessel_score_history rows older than `days` days.

    Returns the count of rows deleted.
    """
    if _BACKEND == "postgres":
        sql = f"DELETE FROM vessel_score_history WHERE computed_at < NOW() - INTERVAL '{days} days'"
        params: tuple = ()
    else:
        sql = f"DELETE FROM vessel_score_history WHERE computed_at < datetime('now', '-{days} days')"
        params = ()

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        return c.rowcount


def archive_old_ais_positions(days: int = 90) -> int:
    """
    Delete ais_positions rows with position_ts older than `days` days.

    Returns the count of rows deleted.
    """
    if _BACKEND == "postgres":
        sql = f"DELETE FROM ais_positions WHERE position_ts < NOW() - INTERVAL '{days} days'"
        params: tuple = ()
    else:
        sql = f"DELETE FROM ais_positions WHERE position_ts < datetime('now', '-{days} days')"
        params = ()

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        return c.rowcount
