# db/alerts.py
"""Alert storage — CREATE TABLE DDL and CRUD for the alerts table.

Dual-backend: PostgreSQL (BIGSERIAL, TIMESTAMPTZ, JSONB) and SQLite (INTEGER AUTOINCREMENT, TEXT, TEXT).
All functions follow the _BACKEND / _conn() / _cursor() / _rows() pattern from db/connection.py.
"""
import json as _json
from .connection import _BACKEND, _conn, _cursor, _rows, _row, _jp


# ── DDL ───────────────────────────────────────────────────────────────────────

def init_alerts_table() -> None:
    """Create alerts table and indexes (idempotent)."""
    if _BACKEND == "postgres":
        _init_alerts_postgres()
    else:
        _init_alerts_sqlite()


def _init_alerts_postgres() -> None:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id                  BIGSERIAL    PRIMARY KEY,
                imo_number          VARCHAR(20)  NOT NULL,
                vessel_name         TEXT,
                alert_type          TEXT         NOT NULL,
                before_score        INTEGER,
                after_score         INTEGER,
                before_risk_level   TEXT,
                after_risk_level    TEXT,
                score_at_trigger    INTEGER,
                new_indicators_json JSONB        DEFAULT '[]',
                is_read             SMALLINT     NOT NULL DEFAULT 0,
                triggered_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_imo ON alerts(imo_number)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at DESC)"
        )


def _init_alerts_sqlite() -> None:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                imo_number          TEXT    NOT NULL,
                vessel_name         TEXT,
                alert_type          TEXT    NOT NULL,
                before_score        INTEGER,
                after_score         INTEGER,
                before_risk_level   TEXT,
                after_risk_level    TEXT,
                score_at_trigger    INTEGER,
                new_indicators_json TEXT    DEFAULT '[]',
                is_read             INTEGER NOT NULL DEFAULT 0,
                triggered_at        TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_imo ON alerts(imo_number)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at DESC)"
        )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def insert_alert(
    imo: str,
    vessel_name: str | None,
    alert_type: str,
    before_score: int | None,
    after_score: int | None,
    before_risk_level: str | None,
    after_risk_level: str | None,
    score_at_trigger: int,
    new_indicators: list,
) -> None:
    """Insert one alert row. triggered_at defaults to NOW()/datetime('now') in the DB."""
    new_indicators_str = _json.dumps(new_indicators)

    if _BACKEND == "postgres":
        sql = f"""
            INSERT INTO alerts
                (imo_number, vessel_name, alert_type,
                 before_score, after_score, before_risk_level, after_risk_level,
                 score_at_trigger, new_indicators_json, is_read)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {_jp()}, 0)
        """
    else:
        sql = f"""
            INSERT INTO alerts
                (imo_number, vessel_name, alert_type,
                 before_score, after_score, before_risk_level, after_risk_level,
                 score_at_trigger, new_indicators_json, is_read)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, {_jp()}, 0)
        """

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, (
            imo, vessel_name, alert_type,
            before_score, after_score, before_risk_level, after_risk_level,
            score_at_trigger, new_indicators_str,
        ))


def get_alerts(is_read: int | None = None, limit: int = 200) -> list[dict]:
    """
    Return alert rows ordered by triggered_at DESC.

    is_read=None  — all rows
    is_read=0     — unread only
    is_read=1     — read only
    new_indicators_json is normalised from JSON string to Python list on every row.
    """
    if _BACKEND == "postgres":
        if is_read is None:
            sql = "SELECT * FROM alerts ORDER BY triggered_at DESC LIMIT %s"
            params = (limit,)
        else:
            sql = "SELECT * FROM alerts WHERE is_read = %s ORDER BY triggered_at DESC LIMIT %s"
            params = (is_read, limit)
    else:
        if is_read is None:
            sql = "SELECT * FROM alerts ORDER BY triggered_at DESC LIMIT ?"
            params = (limit,)
        else:
            sql = "SELECT * FROM alerts WHERE is_read = ? ORDER BY triggered_at DESC LIMIT ?"
            params = (is_read, limit)

    with _conn() as conn:
        c = _cursor(conn)
        c.execute(sql, params)
        rows = _rows(c)

    # Normalise new_indicators_json to Python list
    for row in rows:
        val = row.get("new_indicators_json")
        if isinstance(val, str):
            try:
                row["new_indicators_json"] = _json.loads(val)
            except (_json.JSONDecodeError, TypeError):
                row["new_indicators_json"] = []
        elif val is None:
            row["new_indicators_json"] = []
        # If already a list (postgres JSONB), leave as-is

    return rows


def get_unread_count() -> int:
    """Return the count of unread alerts (is_read=0)."""
    with _conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM alerts WHERE is_read = 0")
        return int(c.fetchone()[0])


def mark_alert_read(alert_id: int) -> bool:
    """
    Set is_read=1 for the given alert_id.

    Returns True if the row existed and was updated, False if not found.
    """
    if _BACKEND == "postgres":
        sql = "UPDATE alerts SET is_read = 1 WHERE id = %s"
    else:
        sql = "UPDATE alerts SET is_read = 1 WHERE id = ?"

    with _conn() as conn:
        c = conn.cursor()
        c.execute(sql, (alert_id,))
        return c.rowcount > 0
