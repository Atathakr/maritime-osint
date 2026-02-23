"""PostgreSQL database layer for Maritime OSINT platform."""

import json
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL environment variable not set")
        # psycopg2 accepts Railway's postgres:// URLs; upgrade scheme if needed
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        _pool = ThreadedConnectionPool(1, 10, dsn=url)
    return _pool


def get_connection():
    return _get_pool().getconn()


def release_connection(conn):
    _get_pool().putconn(conn)


def init_db() -> None:
    """Create all tables and indexes on first run (idempotent)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # ── Canonical vessel registry ─────────────────────────────────
            # IMO number is the permanent anchor identifier for a vessel.
            # Flag, name, owner etc. change; IMO does not.
            cur.execute("""
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vessels_name  ON vessels(vessel_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vessels_flag  ON vessels(flag_state)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vessels_mmsi  ON vessels(mmsi)")

            # ── Sanctions entries (multi-list) ───────────────────────────
            # source_id is the canonical ID from the originating list
            # (OFAC UID, OpenSanctions entity ID, etc.) — used for upserts.
            cur.execute("""
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_san_imo    ON sanctions_entries(imo_number) WHERE imo_number IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_san_mmsi   ON sanctions_entries(mmsi)       WHERE mmsi IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_san_name   ON sanctions_entries(entity_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_san_list   ON sanctions_entries(list_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_san_prog   ON sanctions_entries(program)")

            # ── Vessel flag history (Indicator 15: flag hopping) ─────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vessel_flag_history (
                    id              SERIAL PRIMARY KEY,
                    imo_number      VARCHAR(20) NOT NULL,
                    flag_state      VARCHAR(10) NOT NULL,
                    effective_date  DATE,
                    source          VARCHAR(100),
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_flaghist_imo ON vessel_flag_history(imo_number)")

            # ── Ingest log ────────────────────────────────────────────────
            cur.execute("""
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
        conn.commit()
    finally:
        release_connection(conn)


# ── Sanctions ──────────────────────────────────────────────────────────────

def upsert_sanctions_entries(entries: list[dict], list_name: str) -> tuple[int, int]:
    """
    Bulk upsert sanctions entries keyed on (list_name, source_id).
    Returns (inserted, updated) counts.
    Also syncs matching IMO-keyed vessels into the vessel registry.
    """
    conn = get_connection()
    inserted = updated = 0
    try:
        with conn.cursor() as cur:
            for ent in entries:
                source_id = ent.get("source_id") or ""
                if not source_id:
                    continue

                aliases_json = json.dumps(ent.get("aliases", []))
                identifiers_json = json.dumps(ent.get("identifiers", {}))

                cur.execute("""
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
                    list_name,
                    source_id,
                    ent.get("entity_type"),
                    ent.get("entity_name", ""),
                    ent.get("imo_number"),
                    ent.get("mmsi"),
                    ent.get("vessel_type"),
                    ent.get("flag_state"),
                    ent.get("call_sign"),
                    ent.get("program"),
                    ent.get("gross_tonnage"),
                    aliases_json,
                    identifiers_json,
                ))
                row = cur.fetchone()
                if row and row[0]:
                    inserted += 1
                else:
                    updated += 1

                # Sync to vessel registry if we have an IMO
                imo = ent.get("imo_number")
                if imo:
                    cur.execute("""
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
                        imo,
                        ent.get("mmsi"),
                        ent.get("entity_name"),
                        ent.get("vessel_type"),
                        ent.get("flag_state"),
                        ent.get("call_sign"),
                        ent.get("gross_tonnage"),
                        ent.get("identifiers", {}).get("owner_operator"),
                        list_name,
                    ))

        conn.commit()
    finally:
        release_connection(conn)
    return inserted, updated


def get_sanctions_entries(
    list_name: str | None = None,
    program: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    conn = get_connection()
    try:
        clauses = []
        params: list = []
        if list_name:
            clauses.append("list_name = %s")
            params.append(list_name)
        if program:
            clauses.append("program ILIKE %s")
            params.append(f"%{program}%")
        if entity_type:
            clauses.append("entity_type = %s")
            params.append(entity_type)
        if q:
            clauses.append("(entity_name ILIKE %s OR aliases::text ILIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                       vessel_type, flag_state, call_sign, program, gross_tonnage,
                       aliases, identifiers, created_at, updated_at
                FROM sanctions_entries
                {where}
                ORDER BY entity_name ASC
                LIMIT %s OFFSET %s
            """, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def get_sanctions_counts() -> dict:
    """Return entry counts by list, plus a vessel-only count."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT list_name,
                       COUNT(*) AS total,
                       COUNT(imo_number) AS with_imo
                FROM sanctions_entries
                GROUP BY list_name
                ORDER BY list_name
            """)
            by_list = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT COUNT(*) AS n FROM sanctions_entries")
            total = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM sanctions_entries WHERE imo_number IS NOT NULL")
            with_imo = cur.fetchone()["n"]
        return {"total": total, "with_imo": with_imo, "by_list": by_list}
    finally:
        release_connection(conn)


# ── Screening queries ──────────────────────────────────────────────────────

def search_sanctions_by_imo(imo: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                       vessel_type, flag_state, call_sign, program, aliases
                FROM sanctions_entries
                WHERE imo_number = %s
                ORDER BY list_name
            """, (imo,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def search_sanctions_by_mmsi(mmsi: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                       vessel_type, flag_state, call_sign, program, aliases
                FROM sanctions_entries
                WHERE mmsi = %s
                ORDER BY list_name
            """, (mmsi,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def search_sanctions_by_name(name: str, limit: int = 50) -> list[dict]:
    """Search by vessel name — checks entity_name and aliases JSONB array."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, list_name, entity_name, entity_type, imo_number, mmsi,
                       vessel_type, flag_state, call_sign, program, aliases
                FROM sanctions_entries
                WHERE entity_name ILIKE %s
                   OR aliases::text ILIKE %s
                ORDER BY
                    CASE WHEN entity_name ILIKE %s THEN 0 ELSE 1 END,
                    entity_name ASC
                LIMIT %s
            """, (f"%{name}%", f"%{name}%", f"{name}%", limit))
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


# ── Vessel registry ───────────────────────────────────────────────────────

def get_vessels(q: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_connection()
    try:
        params: list = []
        where = ""
        if q:
            where = "WHERE vessel_name ILIKE %s OR imo_number = %s OR mmsi = %s"
            params = [f"%{q}%", q, q]
        params.extend([limit, offset])
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, imo_number, mmsi, vessel_name, vessel_type, flag_state,
                       gross_tonnage, year_built, call_sign, registered_owner,
                       risk_score, data_source, created_at, updated_at
                FROM vessels
                {where}
                ORDER BY vessel_name ASC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def get_vessel(imo: str) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM vessels WHERE imo_number = %s", (imo,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        release_connection(conn)


def get_vessel_count() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vessels")
            return cur.fetchone()[0]
    finally:
        release_connection(conn)


# ── Ingest log ────────────────────────────────────────────────────────────

def log_ingest_start(source_name: str) -> int:
    """Insert a new ingest_log row with status='running'. Returns row ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingest_log (source_name, status, started_at)
                VALUES (%s, 'running', NOW())
                RETURNING id
            """, (source_name,))
            log_id = cur.fetchone()[0]
        conn.commit()
        return log_id
    finally:
        release_connection(conn)


def log_ingest_complete(
    log_id: int,
    status: str,
    processed: int = 0,
    inserted: int = 0,
    updated: int = 0,
    error: str | None = None,
) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ingest_log SET
                    status             = %s,
                    records_processed  = %s,
                    records_inserted   = %s,
                    records_updated    = %s,
                    error_message      = %s,
                    completed_at       = NOW()
                WHERE id = %s
            """, (status, processed, inserted, updated, error, log_id))
        conn.commit()
    finally:
        release_connection(conn)


def get_ingest_log(limit: int = 20) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, source_name, status, records_processed,
                       records_inserted, records_updated, error_message,
                       started_at, completed_at
                FROM ingest_log
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


# ── Stats ─────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM sanctions_entries")
            total_sanctions = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM vessels")
            total_vessels = cur.fetchone()["n"]

            cur.execute("""
                SELECT list_name, COUNT(*) AS n
                FROM sanctions_entries
                GROUP BY list_name
                ORDER BY list_name
            """)
            by_list = {r["list_name"]: r["n"] for r in cur.fetchall()}

            cur.execute("""
                SELECT source_name, status, records_inserted, completed_at
                FROM ingest_log
                ORDER BY id DESC
                LIMIT 10
            """)
            recent_ingests = [dict(r) for r in cur.fetchall()]

        return {
            "total_sanctions": total_sanctions,
            "total_vessels": total_vessels,
            "by_list": by_list,
            "recent_ingests": recent_ingests,
        }
    finally:
        release_connection(conn)
