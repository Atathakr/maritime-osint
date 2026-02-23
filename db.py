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
    return {
        "total_sanctions": total_sanctions,
        "total_vessels":   total_vessels,
        "by_list":         by_list,
        "recent_ingests":  recent_ingests,
    }
