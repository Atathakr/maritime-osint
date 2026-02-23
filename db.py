"""
Database layer — Maritime OSINT Platform.

Dual-backend:
  • SQLite   — local development (no DATABASE_URL, or sqlite:///… URL)
  • PostgreSQL — Railway production  (DATABASE_URL = postgresql://…)

All public functions are backend-agnostic; callers never import psycopg2.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

# ── Backend detection ─────────────────────────────────────────────────────

_DB_URL: str = ""
_BACKEND: str = "sqlite"   # 'sqlite' | 'postgres'
_POOL = None                # ThreadedConnectionPool (postgres only)


def _init_backend() -> None:
    global _DB_URL, _BACKEND
    _DB_URL = os.getenv("DATABASE_URL", "")
    if _DB_URL.startswith(("postgresql://", "postgres://")):
        _BACKEND = "postgres"
    else:
        _BACKEND = "sqlite"


_init_backend()


def _sqlite_path() -> str:
    _here = os.path.dirname(os.path.abspath(__file__))
    if _DB_URL.startswith("sqlite:///"):
        rel = _DB_URL[10:]
        # If it looks relative, anchor it to the project directory
        return rel if os.path.isabs(rel) else os.path.join(_here, rel)
    return os.path.join(_here, "maritime_osint.db")


# ── Connection management ─────────────────────────────────────────────────

def _get_pool():
    global _POOL
    if _POOL is None:
        import psycopg2
        from psycopg2.pool import ThreadedConnectionPool
        url = _DB_URL.replace("postgres://", "postgresql://", 1)
        _POOL = ThreadedConnectionPool(1, 10, dsn=url)
    return _POOL


@contextmanager
def _conn():
    """
    Yield a database connection; commit on clean exit, rollback on exception,
    always release/close.
    """
    if _BACKEND == "postgres":
        pool = _get_pool()
        conn = pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    else:
        conn = sqlite3.connect(_sqlite_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _cursor(conn):
    """Return a cursor with dict-like rows for the current backend."""
    if _BACKEND == "postgres":
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()   # sqlite3.Row already set on conn


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def _row(cursor) -> dict | None:
    r = cursor.fetchone()
    return dict(r) if r else None


# ── SQL helpers ───────────────────────────────────────────────────────────

_P = "%s" if _BACKEND == "postgres" else "?"   # param placeholder


def _ph(n: int = 1) -> str:
    """Return n comma-separated placeholders for the current backend."""
    p = "%s" if _BACKEND == "postgres" else "?"
    return ", ".join([p] * n)


def _ilike(col: str) -> str:
    """Case-insensitive LIKE operator."""
    p = "%s" if _BACKEND == "postgres" else "?"
    return f"{col} {'ILIKE' if _BACKEND == 'postgres' else 'LIKE'} {p}"


# ── Schema ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables and indexes (idempotent)."""
    with _conn() as conn:
        c = conn.cursor()

        if _BACKEND == "postgres":
            _init_postgres(c)
        else:
            _init_sqlite(c)


def _init_postgres(c) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS vessels (
            id              SERIAL PRIMARY KEY,
            imo_number      VARCHAR(20) UNIQUE NOT NULL,
            mmsi            VARCHAR(20),
            vessel_name     VARCHAR(255),
            vessel_type     VARCHAR(100),
            flag_state      VARCHAR(10),
            gross_tonnage   INTEGER,
            year_built      INTEGER,
            call_sign       VARCHAR(50),
            registered_owner VARCHAR(500),
            ship_manager    VARCHAR(500),
            class_society   VARCHAR(100),
            pi_club         VARCHAR(100),
            risk_score      INTEGER DEFAULT 0,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            data_source     VARCHAR(100)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_vessels_name ON vessels(vessel_name)",
        "CREATE INDEX IF NOT EXISTS idx_vessels_flag ON vessels(flag_state)",
        "CREATE INDEX IF NOT EXISTS idx_vessels_mmsi ON vessels(mmsi)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sanctions_entries (
            id              SERIAL PRIMARY KEY,
            list_name       VARCHAR(100) NOT NULL,
            source_id       VARCHAR(100) NOT NULL,
            entity_type     VARCHAR(50),
            entity_name     VARCHAR(500) NOT NULL,
            imo_number      VARCHAR(20),
            mmsi            VARCHAR(20),
            vessel_type     VARCHAR(100),
            flag_state      VARCHAR(10),
            call_sign       VARCHAR(50),
            program         VARCHAR(500),
            gross_tonnage   INTEGER,
            aliases         JSONB    DEFAULT '[]',
            identifiers     JSONB    DEFAULT '{}',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(list_name, source_id)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_san_imo  ON sanctions_entries(imo_number) WHERE imo_number IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_san_mmsi ON sanctions_entries(mmsi)       WHERE mmsi IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_san_name ON sanctions_entries(entity_name)",
        "CREATE INDEX IF NOT EXISTS idx_san_list ON sanctions_entries(list_name)",
        "CREATE INDEX IF NOT EXISTS idx_san_prog ON sanctions_entries(program)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_flag_history (
            id              SERIAL PRIMARY KEY,
            imo_number      VARCHAR(20) NOT NULL,
            flag_state      VARCHAR(10) NOT NULL,
            effective_date  DATE,
            source          VARCHAR(100),
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_flaghist_imo ON vessel_flag_history(imo_number)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS ingest_log (
            id                  SERIAL PRIMARY KEY,
            source_name         VARCHAR(100) NOT NULL,
            status              VARCHAR(50),
            records_processed   INTEGER DEFAULT 0,
            records_inserted    INTEGER DEFAULT 0,
            records_updated     INTEGER DEFAULT 0,
            error_message       TEXT,
            started_at          TIMESTAMPTZ,
            completed_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── Session 2: AIS tables ──────────────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS ais_positions (
            id          BIGSERIAL PRIMARY KEY,
            mmsi        VARCHAR(20) NOT NULL,
            imo_number  VARCHAR(20),
            vessel_name VARCHAR(255),
            vessel_type SMALLINT,
            lat         DOUBLE PRECISION NOT NULL,
            lon         DOUBLE PRECISION NOT NULL,
            sog         REAL,
            cog         REAL,
            heading     SMALLINT,
            nav_status  SMALLINT,
            source      VARCHAR(20) DEFAULT 'aisstream',
            position_ts TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(mmsi, position_ts)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_aispos_mmsi   ON ais_positions(mmsi)",
        "CREATE INDEX IF NOT EXISTS idx_aispos_ts     ON ais_positions(position_ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_aispos_imo    ON ais_positions(imo_number) WHERE imo_number IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_aispos_box    ON ais_positions(lat, lon)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ais_vessels (
            mmsi            VARCHAR(20) PRIMARY KEY,
            imo_number      VARCHAR(20),
            vessel_name     VARCHAR(255),
            vessel_type     SMALLINT,
            call_sign       VARCHAR(50),
            flag_state      VARCHAR(10),
            length          REAL,
            width           REAL,
            draft           REAL,
            destination     VARCHAR(255),
            eta             VARCHAR(50),
            last_lat        DOUBLE PRECISION,
            last_lon        DOUBLE PRECISION,
            last_sog        REAL,
            last_cog        REAL,
            last_nav_status SMALLINT,
            last_seen       TIMESTAMPTZ,
            first_seen      TIMESTAMPTZ DEFAULT NOW(),
            sanctions_hit   BOOLEAN DEFAULT FALSE,
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_aisvsl_imo ON ais_vessels(imo_number) WHERE imo_number IS NOT NULL")

    c.execute("""
        CREATE TABLE IF NOT EXISTS dark_periods (
            id              SERIAL PRIMARY KEY,
            mmsi            VARCHAR(20) NOT NULL,
            imo_number      VARCHAR(20),
            vessel_name     VARCHAR(255),
            gap_start       TIMESTAMPTZ NOT NULL,
            gap_end         TIMESTAMPTZ,
            gap_hours       REAL,
            last_lat        DOUBLE PRECISION,
            last_lon        DOUBLE PRECISION,
            reappear_lat    DOUBLE PRECISION,
            reappear_lon    DOUBLE PRECISION,
            distance_km     REAL,
            risk_zone       VARCHAR(100),
            risk_level      VARCHAR(20),
            sanctions_hit   BOOLEAN DEFAULT FALSE,
            indicator_code  VARCHAR(10) DEFAULT 'IND1',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(mmsi, gap_start)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_dark_mmsi ON dark_periods(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dark_ts   ON dark_periods(gap_start DESC)")


def _init_sqlite(c) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS vessels (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            imo_number       TEXT UNIQUE NOT NULL,
            mmsi             TEXT,
            vessel_name      TEXT,
            vessel_type      TEXT,
            flag_state       TEXT,
            gross_tonnage    INTEGER,
            year_built       INTEGER,
            call_sign        TEXT,
            registered_owner TEXT,
            ship_manager     TEXT,
            class_society    TEXT,
            pi_club          TEXT,
            risk_score       INTEGER DEFAULT 0,
            created_at       TEXT DEFAULT (datetime('now')),
            updated_at       TEXT DEFAULT (datetime('now')),
            data_source      TEXT
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_vessels_name ON vessels(vessel_name)",
        "CREATE INDEX IF NOT EXISTS idx_vessels_flag ON vessels(flag_state)",
        "CREATE INDEX IF NOT EXISTS idx_vessels_mmsi ON vessels(mmsi)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sanctions_entries (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            list_name     TEXT NOT NULL,
            source_id     TEXT NOT NULL,
            entity_type   TEXT,
            entity_name   TEXT NOT NULL,
            imo_number    TEXT,
            mmsi          TEXT,
            vessel_type   TEXT,
            flag_state    TEXT,
            call_sign     TEXT,
            program       TEXT,
            gross_tonnage INTEGER,
            aliases       TEXT DEFAULT '[]',
            identifiers   TEXT DEFAULT '{}',
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(list_name, source_id)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_san_imo  ON sanctions_entries(imo_number)",
        "CREATE INDEX IF NOT EXISTS idx_san_mmsi ON sanctions_entries(mmsi)",
        "CREATE INDEX IF NOT EXISTS idx_san_name ON sanctions_entries(entity_name)",
        "CREATE INDEX IF NOT EXISTS idx_san_list ON sanctions_entries(list_name)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_flag_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            imo_number     TEXT NOT NULL,
            flag_state     TEXT NOT NULL,
            effective_date TEXT,
            source         TEXT,
            created_at     TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_flaghist_imo ON vessel_flag_history(imo_number)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS ingest_log (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name       TEXT NOT NULL,
            status            TEXT,
            records_processed INTEGER DEFAULT 0,
            records_inserted  INTEGER DEFAULT 0,
            records_updated   INTEGER DEFAULT 0,
            error_message     TEXT,
            started_at        TEXT,
            completed_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Session 2: AIS tables ──────────────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS ais_positions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi        TEXT NOT NULL,
            imo_number  TEXT,
            vessel_name TEXT,
            vessel_type INTEGER,
            lat         REAL NOT NULL,
            lon         REAL NOT NULL,
            sog         REAL,
            cog         REAL,
            heading     INTEGER,
            nav_status  INTEGER,
            source      TEXT DEFAULT 'aisstream',
            position_ts TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi, position_ts)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_aispos_mmsi ON ais_positions(mmsi)",
        "CREATE INDEX IF NOT EXISTS idx_aispos_ts   ON ais_positions(position_ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_aispos_imo  ON ais_positions(imo_number)",
        "CREATE INDEX IF NOT EXISTS idx_aispos_box  ON ais_positions(lat, lon)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ais_vessels (
            mmsi            TEXT PRIMARY KEY,
            imo_number      TEXT,
            vessel_name     TEXT,
            vessel_type     INTEGER,
            call_sign       TEXT,
            flag_state      TEXT,
            length          REAL,
            width           REAL,
            draft           REAL,
            destination     TEXT,
            eta             TEXT,
            last_lat        REAL,
            last_lon        REAL,
            last_sog        REAL,
            last_cog        REAL,
            last_nav_status INTEGER,
            last_seen       TEXT,
            first_seen      TEXT DEFAULT (datetime('now')),
            sanctions_hit   INTEGER DEFAULT 0,
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_aisvsl_imo ON ais_vessels(imo_number)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS dark_periods (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi           TEXT NOT NULL,
            imo_number     TEXT,
            vessel_name    TEXT,
            gap_start      TEXT NOT NULL,
            gap_end        TEXT,
            gap_hours      REAL,
            last_lat       REAL,
            last_lon       REAL,
            reappear_lat   REAL,
            reappear_lon   REAL,
            distance_km    REAL,
            risk_zone      TEXT,
            risk_level     TEXT,
            sanctions_hit  INTEGER DEFAULT 0,
            indicator_code TEXT DEFAULT 'IND1',
            created_at     TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi, gap_start)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_dark_mmsi ON dark_periods(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dark_ts   ON dark_periods(gap_start DESC)")


# ── Sanctions ─────────────────────────────────────────────────────────────

def upsert_sanctions_entries(entries: list[dict], list_name: str) -> tuple[int, int]:
    """
    Bulk upsert sanctions entries keyed on (list_name, source_id).
    Also syncs IMO-identified vessels into the vessel registry.
    Returns (inserted, updated).
    """
    inserted = updated = 0
    with _conn() as conn:
        c = conn.cursor()
        for ent in entries:
            source_id = ent.get("source_id") or ""
            if not source_id:
                continue

            aliases_str = json.dumps(ent.get("aliases", []))
            identifiers_str = json.dumps(ent.get("identifiers", {}))

            if _BACKEND == "postgres":
                c.execute("""
                    INSERT INTO sanctions_entries (
                        list_name, source_id, entity_type, entity_name,
                        imo_number, mmsi, vessel_type, flag_state, call_sign,
                        program, gross_tonnage, aliases, identifiers
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                    ON CONFLICT (list_name, source_id) DO UPDATE SET
                        entity_type   = EXCLUDED.entity_type,
                        entity_name   = EXCLUDED.entity_name,
                        imo_number    = COALESCE(EXCLUDED.imo_number,    sanctions_entries.imo_number),
                        mmsi          = COALESCE(EXCLUDED.mmsi,          sanctions_entries.mmsi),
                        vessel_type   = COALESCE(EXCLUDED.vessel_type,   sanctions_entries.vessel_type),
                        flag_state    = COALESCE(EXCLUDED.flag_state,    sanctions_entries.flag_state),
                        call_sign     = COALESCE(EXCLUDED.call_sign,     sanctions_entries.call_sign),
                        program       = EXCLUDED.program,
                        gross_tonnage = COALESCE(EXCLUDED.gross_tonnage, sanctions_entries.gross_tonnage),
                        aliases       = EXCLUDED.aliases,
                        identifiers   = EXCLUDED.identifiers,
                        updated_at    = NOW()
                    RETURNING (xmax = 0) AS is_insert
                """, (
                    list_name, source_id,
                    ent.get("entity_type"), ent.get("entity_name", ""),
                    ent.get("imo_number"), ent.get("mmsi"),
                    ent.get("vessel_type"), ent.get("flag_state"),
                    ent.get("call_sign"), ent.get("program"),
                    ent.get("gross_tonnage"), aliases_str, identifiers_str,
                ))
                row = c.fetchone()
                if row and row[0]:
                    inserted += 1
                else:
                    updated += 1
            else:
                # SQLite: check existence first, then insert-or-replace
                c.execute(
                    "SELECT id FROM sanctions_entries WHERE list_name=? AND source_id=?",
                    (list_name, source_id),
                )
                exists = c.fetchone() is not None
                c.execute("""
                    INSERT OR REPLACE INTO sanctions_entries (
                        list_name, source_id, entity_type, entity_name,
                        imo_number, mmsi, vessel_type, flag_state, call_sign,
                        program, gross_tonnage, aliases, identifiers
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    list_name, source_id,
                    ent.get("entity_type"), ent.get("entity_name", ""),
                    ent.get("imo_number"), ent.get("mmsi"),
                    ent.get("vessel_type"), ent.get("flag_state"),
                    ent.get("call_sign"), ent.get("program"),
                    ent.get("gross_tonnage"), aliases_str, identifiers_str,
                ))
                if exists:
                    updated += 1
                else:
                    inserted += 1

            # Sync to vessel registry if we have an IMO number
            imo = ent.get("imo_number")
            if imo:
                owner = ent.get("identifiers", {}).get("owner_operator")
                if _BACKEND == "postgres":
                    c.execute("""
                        INSERT INTO vessels (
                            imo_number, mmsi, vessel_name, vessel_type,
                            flag_state, call_sign, gross_tonnage,
                            registered_owner, data_source
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (imo_number) DO UPDATE SET
                            mmsi          = COALESCE(EXCLUDED.mmsi,          vessels.mmsi),
                            vessel_name   = COALESCE(EXCLUDED.vessel_name,   vessels.vessel_name),
                            vessel_type   = COALESCE(EXCLUDED.vessel_type,   vessels.vessel_type),
                            flag_state    = COALESCE(EXCLUDED.flag_state,    vessels.flag_state),
                            call_sign     = COALESCE(EXCLUDED.call_sign,     vessels.call_sign),
                            gross_tonnage = COALESCE(EXCLUDED.gross_tonnage, vessels.gross_tonnage),
                            updated_at    = NOW()
                    """, (
                        imo, ent.get("mmsi"), ent.get("entity_name"),
                        ent.get("vessel_type"), ent.get("flag_state"),
                        ent.get("call_sign"), ent.get("gross_tonnage"),
                        owner, list_name,
                    ))
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO vessels (
                            imo_number, mmsi, vessel_name, vessel_type,
                            flag_state, call_sign, gross_tonnage,
                            registered_owner, data_source
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        imo, ent.get("mmsi"), ent.get("entity_name"),
                        ent.get("vessel_type"), ent.get("flag_state"),
                        ent.get("call_sign"), ent.get("gross_tonnage"),
                        owner, list_name,
                    ))

    return inserted, updated


def get_sanctions_entries(
    list_name: str | None = None,
    program: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    p = "?" if _BACKEND == "sqlite" else "%s"

    if list_name:
        clauses.append(f"list_name = {p}")
        params.append(list_name)
    if program:
        clauses.append(f"program {'ILIKE' if _BACKEND == 'postgres' else 'LIKE'} {p}")
        params.append(f"%{program}%")
    if entity_type:
        clauses.append(f"entity_type = {p}")
        params.append(entity_type)
    if q:
        op = 'ILIKE' if _BACKEND == 'postgres' else 'LIKE'
        clauses.append(f"(entity_name {op} {p} OR aliases {op} {p})")
        params.extend([f"%{q}%", f"%{q}%"])

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])

    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                   vessel_type, flag_state, call_sign, program, gross_tonnage,
                   aliases, identifiers, created_at, updated_at
            FROM sanctions_entries
            {where}
            ORDER BY entity_name ASC
            LIMIT {p} OFFSET {p}
        """, params)
        rows = _rows(c)

    # Deserialise JSON aliases for SQLite (Postgres returns them as objects already)
    for r in rows:
        if isinstance(r.get("aliases"), str):
            try:
                r["aliases"] = json.loads(r["aliases"])
            except Exception:
                r["aliases"] = []
    return rows


def get_sanctions_counts() -> dict:
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT list_name,
                   COUNT(*) AS total,
                   COUNT(imo_number) AS with_imo
            FROM sanctions_entries
            GROUP BY list_name
            ORDER BY list_name
        """)
        by_list = _rows(c)
        c.execute("SELECT COUNT(*) AS n FROM sanctions_entries")
        total = _row(c)["n"]
        c.execute("SELECT COUNT(*) AS n FROM sanctions_entries WHERE imo_number IS NOT NULL")
        with_imo = _row(c)["n"]
    return {"total": total, "with_imo": with_imo, "by_list": by_list}


# ── Screening queries ─────────────────────────────────────────────────────

def _screen_query(where_clause: str, params: list) -> list[dict]:
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                   vessel_type, flag_state, call_sign, program, aliases
            FROM sanctions_entries
            WHERE {where_clause}
            ORDER BY list_name
        """, params)
        rows = _rows(c)
    for r in rows:
        if isinstance(r.get("aliases"), str):
            try:
                r["aliases"] = json.loads(r["aliases"])
            except Exception:
                r["aliases"] = []
    return rows


def search_sanctions_by_imo(imo: str) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    return _screen_query(f"imo_number = {p}", [imo])


def search_sanctions_by_mmsi(mmsi: str) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    return _screen_query(f"mmsi = {p}", [mmsi])


def search_sanctions_by_name(name: str, limit: int = 50) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    op = "ILIKE" if _BACKEND == "postgres" else "LIKE"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                   vessel_type, flag_state, call_sign, program, aliases
            FROM sanctions_entries
            WHERE entity_name {op} {p}
               OR aliases {op} {p}
            ORDER BY
                CASE WHEN entity_name {op} {p} THEN 0 ELSE 1 END,
                entity_name ASC
            LIMIT {p}
        """, [f"%{name}%", f"%{name}%", f"{name}%", limit])
        rows = _rows(c)
    for r in rows:
        if isinstance(r.get("aliases"), str):
            try:
                r["aliases"] = json.loads(r["aliases"])
            except Exception:
                r["aliases"] = []
    return rows


# ── Vessel registry ───────────────────────────────────────────────────────

def get_vessels(q: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    params: list = []
    where = ""
    if q:
        op = "ILIKE" if _BACKEND == "postgres" else "LIKE"
        where = f"WHERE vessel_name {op} {p} OR imo_number = {p} OR mmsi = {p}"
        params = [f"%{q}%", q, q]
    params.extend([limit, offset])
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, imo_number, mmsi, vessel_name, vessel_type, flag_state,
                   gross_tonnage, year_built, call_sign, registered_owner,
                   risk_score, data_source, created_at, updated_at
            FROM vessels
            {where}
            ORDER BY vessel_name ASC
            LIMIT {p} OFFSET {p}
        """, params)
        return _rows(c)


def get_vessel(imo: str) -> dict | None:
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"SELECT * FROM vessels WHERE imo_number = {p}", (imo,))
        return _row(c)


def get_vessel_count() -> int:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM vessels")
        return c.fetchone()[0]


# ── Ingest log ────────────────────────────────────────────────────────────

def log_ingest_start(source_name: str) -> int:
    p = "?" if _BACKEND == "sqlite" else "%s"
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"
    with _conn() as conn:
        c = conn.cursor()
        c.execute(f"""
            INSERT INTO ingest_log (source_name, status, started_at)
            VALUES ({p}, 'running', {now_expr})
        """, (source_name,))
        if _BACKEND == "sqlite":
            return c.lastrowid
        c.execute("SELECT lastval()")
        return c.fetchone()[0]


def log_ingest_complete(
    log_id: int, status: str,
    processed: int = 0, inserted: int = 0, updated: int = 0,
    error: str | None = None,
) -> None:
    p = "?" if _BACKEND == "sqlite" else "%s"
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"
    with _conn() as conn:
        c = conn.cursor()
        c.execute(f"""
            UPDATE ingest_log SET
                status            = {p},
                records_processed = {p},
                records_inserted  = {p},
                records_updated   = {p},
                error_message     = {p},
                completed_at      = {now_expr}
            WHERE id = {p}
        """, (status, processed, inserted, updated, error, log_id))


def get_ingest_log(limit: int = 20) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, source_name, status, records_processed,
                   records_inserted, records_updated, error_message,
                   started_at, completed_at
            FROM ingest_log
            ORDER BY id DESC
            LIMIT {p}
        """, (limit,))
        return _rows(c)


# ── Stats ─────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("SELECT COUNT(*) AS n FROM sanctions_entries")
        total_sanctions = _row(c)["n"]
        c.execute("SELECT COUNT(*) AS n FROM vessels")
        total_vessels = _row(c)["n"]
        c.execute("""
            SELECT list_name, COUNT(*) AS n
            FROM sanctions_entries
            GROUP BY list_name
            ORDER BY list_name
        """)
        by_list = {r["list_name"]: r["n"] for r in _rows(c)}
        c.execute("""
            SELECT source_name, status, records_inserted, completed_at
            FROM ingest_log
            ORDER BY id DESC
            LIMIT 10
        """)
        recent_ingests = _rows(c)
        # AIS stats (tables may not exist yet in older dbs — handle gracefully)
        try:
            c.execute("SELECT COUNT(*) AS n FROM ais_positions")
            total_ais_positions = _row(c)["n"]
            c.execute("SELECT COUNT(*) AS n FROM ais_vessels")
            total_ais_vessels = _row(c)["n"]
            c.execute("SELECT COUNT(*) AS n FROM dark_periods")
            total_dark_periods = _row(c)["n"]
        except Exception:
            total_ais_positions = total_ais_vessels = total_dark_periods = 0
    return {
        "total_sanctions":    total_sanctions,
        "total_vessels":      total_vessels,
        "by_list":            by_list,
        "recent_ingests":     recent_ingests,
        "total_ais_positions": total_ais_positions,
        "total_ais_vessels":  total_ais_vessels,
        "total_dark_periods": total_dark_periods,
    }


# ── AIS positions ──────────────────────────────────────────────────────────

def insert_ais_positions(positions: list[dict]) -> int:
    """Batch-insert AIS positions. Silently skips duplicates. Returns insert count."""
    if not positions:
        return 0
    p = "?" if _BACKEND == "sqlite" else "%s"
    inserted = 0
    with _conn() as conn:
        c = conn.cursor()
        for pos in positions:
            try:
                if _BACKEND == "postgres":
                    c.execute(f"""
                        INSERT INTO ais_positions
                            (mmsi, imo_number, vessel_name, vessel_type,
                             lat, lon, sog, cog, heading, nav_status, source, position_ts)
                        VALUES ({_ph(12)})
                        ON CONFLICT (mmsi, position_ts) DO NOTHING
                    """, (
                        pos.get("mmsi"), pos.get("imo_number"), pos.get("vessel_name"),
                        pos.get("vessel_type"),
                        pos.get("lat"), pos.get("lon"),
                        pos.get("sog"), pos.get("cog"), pos.get("heading"),
                        pos.get("nav_status"), pos.get("source", "aisstream"),
                        pos.get("position_ts"),
                    ))
                    inserted += c.rowcount
                else:
                    c.execute(f"""
                        INSERT OR IGNORE INTO ais_positions
                            (mmsi, imo_number, vessel_name, vessel_type,
                             lat, lon, sog, cog, heading, nav_status, source, position_ts)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        pos.get("mmsi"), pos.get("imo_number"), pos.get("vessel_name"),
                        pos.get("vessel_type"),
                        pos.get("lat"), pos.get("lon"),
                        pos.get("sog"), pos.get("cog"), pos.get("heading"),
                        pos.get("nav_status"), pos.get("source", "aisstream"),
                        pos.get("position_ts"),
                    ))
                    inserted += c.rowcount
            except Exception:
                pass
    return inserted


def upsert_ais_vessel(mmsi: str, data: dict) -> None:
    """Insert or update current vessel state from a ShipStaticData message."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"
    with _conn() as conn:
        c = conn.cursor()
        if _BACKEND == "postgres":
            c.execute(f"""
                INSERT INTO ais_vessels (mmsi, imo_number, vessel_name, vessel_type,
                    call_sign, length, width, draft, destination, eta, updated_at)
                VALUES ({_ph(11)})
                ON CONFLICT (mmsi) DO UPDATE SET
                    imo_number  = COALESCE(EXCLUDED.imo_number,  ais_vessels.imo_number),
                    vessel_name = COALESCE(EXCLUDED.vessel_name, ais_vessels.vessel_name),
                    vessel_type = COALESCE(EXCLUDED.vessel_type, ais_vessels.vessel_type),
                    call_sign   = COALESCE(EXCLUDED.call_sign,   ais_vessels.call_sign),
                    length      = COALESCE(EXCLUDED.length,      ais_vessels.length),
                    width       = COALESCE(EXCLUDED.width,       ais_vessels.width),
                    draft       = COALESCE(EXCLUDED.draft,       ais_vessels.draft),
                    destination = COALESCE(EXCLUDED.destination, ais_vessels.destination),
                    eta         = COALESCE(EXCLUDED.eta,         ais_vessels.eta),
                    updated_at  = NOW()
            """, (
                mmsi, data.get("imo_number"), data.get("vessel_name"),
                data.get("vessel_type"), data.get("call_sign"),
                data.get("length"), data.get("width"), data.get("draft"),
                data.get("destination"), data.get("eta"), "NOW()",
            ))
        else:
            # SQLite: check-then-update or insert
            c.execute("SELECT mmsi FROM ais_vessels WHERE mmsi=?", (mmsi,))
            if c.fetchone():
                c.execute(f"""
                    UPDATE ais_vessels SET
                        imo_number  = COALESCE(?, imo_number),
                        vessel_name = COALESCE(?, vessel_name),
                        vessel_type = COALESCE(?, vessel_type),
                        call_sign   = COALESCE(?, call_sign),
                        length      = COALESCE(?, length),
                        width       = COALESCE(?, width),
                        draft       = COALESCE(?, draft),
                        destination = COALESCE(?, destination),
                        eta         = COALESCE(?, eta),
                        updated_at  = datetime('now')
                    WHERE mmsi = ?
                """, (
                    data.get("imo_number"), data.get("vessel_name"),
                    data.get("vessel_type"), data.get("call_sign"),
                    data.get("length"), data.get("width"), data.get("draft"),
                    data.get("destination"), data.get("eta"), mmsi,
                ))
            else:
                c.execute("""
                    INSERT OR IGNORE INTO ais_vessels
                        (mmsi, imo_number, vessel_name, vessel_type, call_sign,
                         length, width, draft, destination, eta)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    mmsi, data.get("imo_number"), data.get("vessel_name"),
                    data.get("vessel_type"), data.get("call_sign"),
                    data.get("length"), data.get("width"), data.get("draft"),
                    data.get("destination"), data.get("eta"),
                ))


def update_ais_vessel_position(mmsi: str, lat: float, lon: float,
                                sog: float, cog: float,
                                nav_status: int, ts: str) -> None:
    """Update last-seen position on the ais_vessels current-state row."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"
    with _conn() as conn:
        c = conn.cursor()
        if _BACKEND == "postgres":
            c.execute(f"""
                INSERT INTO ais_vessels (mmsi, last_lat, last_lon, last_sog,
                    last_cog, last_nav_status, last_seen, updated_at)
                VALUES ({_ph(8)})
                ON CONFLICT (mmsi) DO UPDATE SET
                    last_lat        = EXCLUDED.last_lat,
                    last_lon        = EXCLUDED.last_lon,
                    last_sog        = EXCLUDED.last_sog,
                    last_cog        = EXCLUDED.last_cog,
                    last_nav_status = EXCLUDED.last_nav_status,
                    last_seen       = EXCLUDED.last_seen,
                    updated_at      = NOW()
            """, (mmsi, lat, lon, sog, cog, nav_status, ts, "NOW()"))
        else:
            c.execute("""
                INSERT INTO ais_vessels (mmsi, last_lat, last_lon, last_sog,
                    last_cog, last_nav_status, last_seen)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(mmsi) DO UPDATE SET
                    last_lat        = excluded.last_lat,
                    last_lon        = excluded.last_lon,
                    last_sog        = excluded.last_sog,
                    last_cog        = excluded.last_cog,
                    last_nav_status = excluded.last_nav_status,
                    last_seen       = excluded.last_seen,
                    updated_at      = datetime('now')
            """, (mmsi, lat, lon, sog, cog, nav_status, ts))


def get_ais_vessels(q: str | None = None, limit: int = 100, offset: int = 0,
                    sanctioned_only: bool = False) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    clauses: list[str] = []
    params: list = []
    op = "ILIKE" if _BACKEND == "postgres" else "LIKE"
    if q:
        clauses.append(f"(vessel_name {op} {p} OR mmsi = {p} OR imo_number = {p})")
        params.extend([f"%{q}%", q, q])
    if sanctioned_only:
        clauses.append(f"sanctions_hit = {p}")
        params.append(True if _BACKEND == "postgres" else 1)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    null_last = "NULLS LAST" if _BACKEND == "postgres" else ""
    params.extend([limit, offset])
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT mmsi, imo_number, vessel_name, vessel_type, call_sign,
                   last_lat, last_lon, last_sog, last_nav_status,
                   last_seen, sanctions_hit, destination, draft
            FROM ais_vessels
            {where}
            ORDER BY last_seen DESC {null_last}
            LIMIT {p} OFFSET {p}
        """, params)
        return _rows(c)


def get_recent_positions(limit: int = 200, mmsi: str | None = None,
                         hours: int = 24) -> list[dict]:
    """Return recent AIS positions, optionally filtered to a specific MMSI."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    cutoff_expr = (
        f"datetime('now', '-{hours} hours')"
        if _BACKEND == "sqlite"
        else f"NOW() - INTERVAL '{hours} hours'"
    )
    clauses = [f"position_ts >= {cutoff_expr}"]
    params: list = []
    if mmsi:
        clauses.append(f"mmsi = {p}")
        params.append(mmsi)
    params.append(limit)
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT mmsi, imo_number, vessel_name, vessel_type,
                   lat, lon, sog, cog, nav_status, source, position_ts
            FROM ais_positions
            WHERE {' AND '.join(clauses)}
            ORDER BY position_ts DESC
            LIMIT {p}
        """, params)
        return _rows(c)


# ── Dark period detection ─────────────────────────────────────────────────

def find_ais_gaps(mmsi: str | None = None, min_hours: float = 2.0,
                  limit: int = 200) -> list[dict]:
    """
    Use window functions to find consecutive AIS position gaps > min_hours.
    Returns list of gap dicts with start/end timestamps and coordinates.
    """
    p = "?" if _BACKEND == "sqlite" else "%s"

    if _BACKEND == "sqlite":
        gap_expr  = "(julianday(next_ts) - julianday(position_ts)) * 24"
    else:
        gap_expr  = "EXTRACT(EPOCH FROM (next_ts - position_ts)) / 3600"

    mmsi_filter = f"WHERE mmsi = {p}" if mmsi else ""
    mmsi_params = [mmsi] if mmsi else []

    query = f"""
        WITH ordered AS (
            SELECT mmsi, imo_number, vessel_name,
                   lat, lon, position_ts,
                   LEAD(position_ts) OVER (PARTITION BY mmsi ORDER BY position_ts) AS next_ts,
                   LEAD(lat)         OVER (PARTITION BY mmsi ORDER BY position_ts) AS next_lat,
                   LEAD(lon)         OVER (PARTITION BY mmsi ORDER BY position_ts) AS next_lon
            FROM ais_positions
            {mmsi_filter}
        )
        SELECT
            mmsi, imo_number, vessel_name,
            position_ts  AS gap_start,
            next_ts      AS gap_end,
            {gap_expr}   AS gap_hours,
            lat          AS last_lat,
            lon          AS last_lon,
            next_lat     AS reappear_lat,
            next_lon     AS reappear_lon
        FROM ordered
        WHERE next_ts IS NOT NULL
          AND {gap_expr} >= {p}
        ORDER BY gap_start DESC
        LIMIT {p}
    """
    params = mmsi_params + [min_hours, limit]
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(query, params)
        return _rows(c)


def upsert_dark_periods(periods: list[dict]) -> int:
    """Persist detected dark periods. Returns count inserted."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    inserted = 0
    with _conn() as conn:
        c = conn.cursor()
        for dp in periods:
            try:
                if _BACKEND == "postgres":
                    c.execute(f"""
                        INSERT INTO dark_periods (
                            mmsi, imo_number, vessel_name,
                            gap_start, gap_end, gap_hours,
                            last_lat, last_lon, reappear_lat, reappear_lon,
                            distance_km, risk_zone, risk_level,
                            sanctions_hit, indicator_code
                        ) VALUES ({_ph(15)})
                        ON CONFLICT (mmsi, gap_start) DO UPDATE SET
                            gap_end      = EXCLUDED.gap_end,
                            gap_hours    = EXCLUDED.gap_hours,
                            reappear_lat = EXCLUDED.reappear_lat,
                            reappear_lon = EXCLUDED.reappear_lon,
                            risk_zone    = EXCLUDED.risk_zone,
                            risk_level   = EXCLUDED.risk_level,
                            sanctions_hit= EXCLUDED.sanctions_hit
                    """, (
                        dp.get("mmsi"), dp.get("imo_number"), dp.get("vessel_name"),
                        dp.get("gap_start"), dp.get("gap_end"), dp.get("gap_hours"),
                        dp.get("last_lat"), dp.get("last_lon"),
                        dp.get("reappear_lat"), dp.get("reappear_lon"),
                        dp.get("distance_km"), dp.get("risk_zone"), dp.get("risk_level"),
                        dp.get("sanctions_hit", False), dp.get("indicator_code", "IND1"),
                    ))
                else:
                    c.execute("""
                        INSERT OR REPLACE INTO dark_periods (
                            mmsi, imo_number, vessel_name,
                            gap_start, gap_end, gap_hours,
                            last_lat, last_lon, reappear_lat, reappear_lon,
                            distance_km, risk_zone, risk_level,
                            sanctions_hit, indicator_code
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        dp.get("mmsi"), dp.get("imo_number"), dp.get("vessel_name"),
                        dp.get("gap_start"), dp.get("gap_end"), dp.get("gap_hours"),
                        dp.get("last_lat"), dp.get("last_lon"),
                        dp.get("reappear_lat"), dp.get("reappear_lon"),
                        dp.get("distance_km"), dp.get("risk_zone"), dp.get("risk_level"),
                        1 if dp.get("sanctions_hit") else 0,
                        dp.get("indicator_code", "IND1"),
                    ))
                inserted += 1
            except Exception:
                pass
    return inserted


def get_dark_periods(limit: int = 100, offset: int = 0,
                     mmsi: str | None = None,
                     risk_level: str | None = None) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    clauses: list[str] = []
    params: list = []
    if mmsi:
        clauses.append(f"mmsi = {p}")
        params.append(mmsi)
    if risk_level:
        clauses.append(f"risk_level = {p}")
        params.append(risk_level)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, mmsi, imo_number, vessel_name,
                   gap_start, gap_end, gap_hours,
                   last_lat, last_lon, reappear_lat, reappear_lon,
                   distance_km, risk_zone, risk_level,
                   sanctions_hit, indicator_code, created_at
            FROM dark_periods
            {where}
            ORDER BY gap_start DESC
            LIMIT {p} OFFSET {p}
        """, params)
        rows = _rows(c)
    # Normalise sanctions_hit to bool for SQLite (stored as 0/1)
    for r in rows:
        r["sanctions_hit"] = bool(r.get("sanctions_hit"))
    return rows


def get_ais_positions(mmsi: str | None = None, limit: int = 200,
                      offset: int = 0) -> list[dict]:
    """Return AIS positions with optional MMSI filter, newest first."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    clauses: list[str] = []
    params: list = []
    if mmsi:
        clauses.append(f"mmsi = {p}")
        params.append(mmsi)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT mmsi, imo_number, vessel_name, vessel_type,
                   lat, lon, sog, cog, nav_status, source, position_ts
            FROM ais_positions
            {where}
            ORDER BY position_ts DESC
            LIMIT {p} OFFSET {p}
        """, params)
        return _rows(c)


def get_active_mmsis(days: int = 30) -> list[str]:
    """Return distinct MMSIs seen within the last N days."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    cutoff_expr = (
        f"datetime('now', '-{days} days')"
        if _BACKEND == "sqlite"
        else f"NOW() - INTERVAL '{days} days'"
    )
    with _conn() as conn:
        c = conn.cursor()
        c.execute(f"""
            SELECT DISTINCT mmsi
            FROM ais_positions
            WHERE position_ts >= {cutoff_expr}
            ORDER BY mmsi
        """)
        return [row[0] for row in c.fetchall()]
