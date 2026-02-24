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

import normalize

# ── Backend detection ─────────────────────────────────────────────────────

_DB_URL: str = ""
_BACKEND: str = "sqlite"   # 'sqlite' | 'postgres'
_POOL = None                # ThreadedConnectionPool (postgres only)


def _init_backend() -> None:
    global _DB_URL, _BACKEND
    _DB_URL = os.getenv("DATABASE_URL", "")
    _BACKEND = "postgres" if _DB_URL.startswith(("postgresql://", "postgres://")) else "sqlite"


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


def _jp() -> str:
    """JSON-typed parameter placeholder — includes ::jsonb cast for Postgres."""
    return "%s::jsonb" if _BACKEND == "postgres" else "?"


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
        "CREATE INDEX IF NOT EXISTS idx_san_imo  ON sanctions_entries(imo_number) "
        "WHERE imo_number IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_san_mmsi ON sanctions_entries(mmsi) "
        "WHERE mmsi IS NOT NULL",
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

    # ── Session 4: Canonical vessel registry ──────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS vessels_canonical (
            canonical_id     VARCHAR(50) PRIMARY KEY,
            entity_name      VARCHAR(500) NOT NULL,
            imo_number       VARCHAR(20),
            mmsi             VARCHAR(20),
            vessel_type      VARCHAR(100),
            flag_normalized  VARCHAR(100),
            aliases          JSONB DEFAULT '[]',
            source_tags      JSONB DEFAULT '[]',
            match_method     VARCHAR(20) DEFAULT 'single_source',
            risk_score       INTEGER DEFAULT 0,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_vc_imo    ON vessels_canonical(imo_number) "
        "WHERE imo_number IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_vc_mmsi   ON vessels_canonical(mmsi)       "
        "WHERE mmsi IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_vc_name   ON vessels_canonical(entity_name)",
        "CREATE INDEX IF NOT EXISTS idx_vc_method ON vessels_canonical(match_method)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sanctions_memberships (
            id               SERIAL PRIMARY KEY,
            canonical_id     VARCHAR(50) NOT NULL
                             REFERENCES vessels_canonical(canonical_id) ON DELETE CASCADE,
            list_name        VARCHAR(100) NOT NULL,
            source_id        VARCHAR(100) NOT NULL,
            entity_type      VARCHAR(50),
            program          VARCHAR(500),
            flag_state       VARCHAR(10),
            call_sign        VARCHAR(50),
            gross_tonnage    INTEGER,
            identifiers      JSONB DEFAULT '{}',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(list_name, source_id)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_sm_canonical ON sanctions_memberships(canonical_id)",
        "CREATE INDEX IF NOT EXISTS idx_sm_list      ON sanctions_memberships(list_name)",
    ]:
        c.execute(idx)

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
        "CREATE INDEX IF NOT EXISTS idx_aispos_imo    ON ais_positions(imo_number) "
        "WHERE imo_number IS NOT NULL",
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
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_aisvsl_imo ON ais_vessels(imo_number) "
        "WHERE imo_number IS NOT NULL"
    )

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

    # ── Session 3: STS events ──────────────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS sts_events (
            id              SERIAL PRIMARY KEY,
            mmsi1           VARCHAR(20) NOT NULL,
            mmsi2           VARCHAR(20) NOT NULL,
            vessel_name1    VARCHAR(255),
            vessel_name2    VARCHAR(255),
            event_ts        TIMESTAMPTZ NOT NULL,
            lat             DOUBLE PRECISION,
            lon             DOUBLE PRECISION,
            distance_m      REAL,
            sog1            REAL,
            sog2            REAL,
            risk_zone       VARCHAR(100),
            risk_level      VARCHAR(20),
            sanctions_hit   BOOLEAN DEFAULT FALSE,
            indicator_code  VARCHAR(10) DEFAULT 'IND7',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(mmsi1, mmsi2, event_ts)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_mmsi1 ON sts_events(mmsi1)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_mmsi2 ON sts_events(mmsi2)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_ts    ON sts_events(event_ts DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_risk  ON sts_events(risk_level)")

    # ── Session 5: Spoofing events ────────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS spoof_events (
            id              SERIAL PRIMARY KEY,
            mmsi            VARCHAR(20) NOT NULL,
            imo_number      VARCHAR(20),
            vessel_name     VARCHAR(255),
            spoof_type      VARCHAR(50) NOT NULL, -- TELEPORT | OVERLAND | ID_MISMATCH
            detected_at     TIMESTAMPTZ NOT NULL,
            lat             DOUBLE PRECISION NOT NULL,
            lon             DOUBLE PRECISION NOT NULL,
            detail          JSONB DEFAULT '{}',
            risk_level      VARCHAR(20) DEFAULT 'LOW',
            sanctions_hit   BOOLEAN DEFAULT FALSE,
            risk_zone       VARCHAR(100),
            indicator_code  VARCHAR(20) DEFAULT 'IND_SPOOF',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(mmsi, spoof_type, detected_at)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_spoof_mmsi ON spoof_events(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_spoof_ts   ON spoof_events(detected_at DESC)")


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

    # ── Session 4: Canonical vessel registry ──────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS vessels_canonical (
            canonical_id    TEXT PRIMARY KEY,
            entity_name     TEXT NOT NULL,
            imo_number      TEXT,
            mmsi            TEXT,
            vessel_type     TEXT,
            flag_normalized TEXT,
            aliases         TEXT DEFAULT '[]',
            source_tags     TEXT DEFAULT '[]',
            match_method    TEXT DEFAULT 'single_source',
            risk_score      INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_vc_imo    ON vessels_canonical(imo_number)",
        "CREATE INDEX IF NOT EXISTS idx_vc_mmsi   ON vessels_canonical(mmsi)",
        "CREATE INDEX IF NOT EXISTS idx_vc_name   ON vessels_canonical(entity_name)",
        "CREATE INDEX IF NOT EXISTS idx_vc_method ON vessels_canonical(match_method)",
    ]:
        c.execute(idx)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sanctions_memberships (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id  TEXT NOT NULL
                          REFERENCES vessels_canonical(canonical_id) ON DELETE CASCADE,
            list_name     TEXT NOT NULL,
            source_id     TEXT NOT NULL,
            entity_type   TEXT,
            program       TEXT,
            flag_state    TEXT,
            call_sign     TEXT,
            gross_tonnage INTEGER,
            identifiers   TEXT DEFAULT '{}',
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(list_name, source_id)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_sm_canonical ON sanctions_memberships(canonical_id)",
        "CREATE INDEX IF NOT EXISTS idx_sm_list      ON sanctions_memberships(list_name)",
    ]:
        c.execute(idx)

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

    # ── Session 3: STS events ──────────────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS sts_events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi1          TEXT NOT NULL,
            mmsi2          TEXT NOT NULL,
            vessel_name1   TEXT,
            vessel_name2   TEXT,
            event_ts       TEXT NOT NULL,
            lat            REAL,
            lon            REAL,
            distance_m     REAL,
            sog1           REAL,
            sog2           REAL,
            risk_zone      TEXT,
            risk_level     TEXT,
            sanctions_hit  INTEGER DEFAULT 0,
            indicator_code TEXT DEFAULT 'IND7',
            created_at     TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi1, mmsi2, event_ts)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_mmsi1 ON sts_events(mmsi1)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_mmsi2 ON sts_events(mmsi2)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_ts    ON sts_events(event_ts DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sts_risk  ON sts_events(risk_level)")

    # ── Session 5: Spoofing events ────────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS spoof_events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi           TEXT NOT NULL,
            imo_number     TEXT,
            vessel_name    TEXT,
            spoof_type     TEXT NOT NULL,
            detected_at    TEXT NOT NULL,
            lat            REAL NOT NULL,
            lon            REAL NOT NULL,
            detail         TEXT DEFAULT '{}',
            risk_level     TEXT DEFAULT 'LOW',
            sanctions_hit  INTEGER DEFAULT 0,
            risk_zone      TEXT,
            indicator_code TEXT DEFAULT 'IND_SPOOF',
            created_at     TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi, spoof_type, detected_at)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_spoof_mmsi ON spoof_events(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_spoof_ts   ON spoof_events(detected_at DESC)")


# ── Canonical vessel registry ─────────────────────────────────────────────

def upsert_sanctions_entries(entries: list[dict], list_name: str) -> tuple[int, int]:
    """
    Bulk upsert sanctions entries into vessels_canonical and sanctions_memberships.
    One canonical row per unique vessel identity; one membership row per source.
    Returns (canonical_inserted, canonical_updated).
    """
    p  = "?" if _BACKEND == "sqlite" else "%s"
    jp = _jp()
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"

    c_inserted = c_updated = 0

    with _conn() as conn:
        c = conn.cursor()

        for ent in entries:
            source_id = (ent.get("source_id") or "").strip()
            if not source_id:
                continue

            imo         = ent.get("imo_number")
            mmsi        = ent.get("mmsi")
            name        = (ent.get("entity_name") or "").strip()
            flag_raw    = ent.get("flag_state")
            identifiers = ent.get("identifiers") or {}
            vessel_type = ent.get("vessel_type")
            entity_type = ent.get("entity_type", "Vessel")

            canonical_id, match_method = normalize.make_canonical_id(imo, mmsi, name, flag_raw)
            flag_norm  = normalize.normalize_flag(flag_raw)
            new_tags   = normalize.parse_source_tags(list_name, identifiers)
            new_aliases = [a for a in (ent.get("aliases") or []) if a and a != name]

            # ── Upsert vessels_canonical (read → merge → write) ───────────
            c.execute(
                f"SELECT aliases, source_tags FROM vessels_canonical WHERE canonical_id = {p}",
                (canonical_id,),
            )
            row = c.fetchone()

            if row:
                ex_aliases = row[0] if not isinstance(row[0], str) else json.loads(row[0] or "[]")
                ex_tags    = row[1] if not isinstance(row[1], str) else json.loads(row[1] or "[]")
                merged_aliases = sorted(set((ex_aliases or []) + new_aliases))
                merged_tags    = sorted(set((ex_tags    or []) + new_tags))

                c.execute(f"""
                    UPDATE vessels_canonical SET
                        entity_name     = {p},
                        imo_number      = COALESCE({p}, imo_number),
                        mmsi            = COALESCE({p}, mmsi),
                        vessel_type     = COALESCE({p}, vessel_type),
                        flag_normalized = COALESCE({p}, flag_normalized),
                        aliases         = {jp},
                        source_tags     = {jp},
                        updated_at      = {now_expr}
                    WHERE canonical_id = {p}
                """, (name, imo, mmsi, vessel_type, flag_norm,
                      json.dumps(merged_aliases), json.dumps(merged_tags),
                      canonical_id))
                c_updated += 1
            else:
                c.execute(f"""
                    INSERT INTO vessels_canonical
                        (canonical_id, entity_name, imo_number, mmsi, vessel_type,
                         flag_normalized, aliases, source_tags, match_method)
                    VALUES ({p},{p},{p},{p},{p},{p},{jp},{jp},{p})
                """, (canonical_id, name, imo, mmsi, vessel_type, flag_norm,
                      json.dumps(new_aliases), json.dumps(new_tags), match_method))
                c_inserted += 1

            # ── Upsert sanctions_memberships ──────────────────────────────
            identifiers_json = json.dumps(identifiers)
            if _BACKEND == "postgres":
                c.execute("""
                    INSERT INTO sanctions_memberships
                        (canonical_id, list_name, source_id, entity_type, program,
                         flag_state, call_sign, gross_tonnage, identifiers)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (list_name, source_id) DO UPDATE SET
                        canonical_id  = EXCLUDED.canonical_id,
                        entity_type   = COALESCE(EXCLUDED.entity_type,
                                                 sanctions_memberships.entity_type),
                        program       = EXCLUDED.program,
                        flag_state    = COALESCE(EXCLUDED.flag_state,
                                                 sanctions_memberships.flag_state),
                        call_sign     = COALESCE(EXCLUDED.call_sign,
                                                 sanctions_memberships.call_sign),
                        gross_tonnage = COALESCE(EXCLUDED.gross_tonnage,
                                                 sanctions_memberships.gross_tonnage),
                        identifiers   = EXCLUDED.identifiers,
                        updated_at    = NOW()
                """, (canonical_id, list_name, source_id, entity_type,
                      ent.get("program"), flag_raw, ent.get("call_sign"),
                      ent.get("gross_tonnage"), identifiers_json))
            else:
                c.execute("""
                    INSERT OR REPLACE INTO sanctions_memberships
                        (canonical_id, list_name, source_id, entity_type, program,
                         flag_state, call_sign, gross_tonnage, identifiers)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (canonical_id, list_name, source_id, entity_type,
                      ent.get("program"), flag_raw, ent.get("call_sign"),
                      ent.get("gross_tonnage"), identifiers_json))

    return c_inserted, c_updated


def get_sanctions_entries(
    list_name: str | None = None,
    program: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """
    Return one row per canonical vessel with aggregated membership info.
    Filters apply to the underlying memberships via EXISTS subqueries.
    """
    p  = "?" if _BACKEND == "sqlite" else "%s"
    op = "ILIKE" if _BACKEND == "postgres" else "LIKE"
    clauses: list[str] = []
    params:  list      = []

    if list_name:
        clauses.append(
            f"EXISTS (SELECT 1 FROM sanctions_memberships sm2 "
            f"WHERE sm2.canonical_id = vc.canonical_id AND sm2.list_name = {p})"
        )
        params.append(list_name)
    if program:
        clauses.append(
            f"EXISTS (SELECT 1 FROM sanctions_memberships sm2 "
            f"WHERE sm2.canonical_id = vc.canonical_id AND sm2.program {op} {p})"
        )
        params.append(f"%{program}%")
    if entity_type:
        clauses.append(
            f"EXISTS (SELECT 1 FROM sanctions_memberships sm2 "
            f"WHERE sm2.canonical_id = vc.canonical_id AND sm2.entity_type = {p})"
        )
        params.append(entity_type)
    if q:
        clauses.append(
            f"(vc.entity_name {op} {p} OR vc.aliases {op} {p} "
            f"OR vc.imo_number = {p} OR vc.mmsi = {p})"
        )
        params.extend([f"%{q}%", f"%{q}%", q, q])

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])

    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT
                vc.canonical_id,
                vc.entity_name,
                vc.imo_number,
                vc.mmsi,
                vc.vessel_type,
                vc.flag_normalized  AS flag_state,
                vc.aliases,
                vc.source_tags,
                vc.match_method,
                vc.created_at,
                vc.updated_at,
                COALESCE(
                    MAX(CASE WHEN sm.list_name = 'OFAC_SDN' THEN sm.program END),
                    MAX(sm.program)
                )                   AS program,
                MAX(sm.gross_tonnage) AS gross_tonnage,
                MAX(sm.entity_type)   AS entity_type,
                COUNT(sm.id)          AS membership_count
            FROM vessels_canonical vc
            LEFT JOIN sanctions_memberships sm ON sm.canonical_id = vc.canonical_id
            {where}
            GROUP BY
                vc.canonical_id, vc.entity_name, vc.imo_number, vc.mmsi,
                vc.vessel_type, vc.flag_normalized, vc.aliases, vc.source_tags,
                vc.match_method, vc.created_at, vc.updated_at
            ORDER BY vc.entity_name ASC
            LIMIT {p} OFFSET {p}
        """, params)
        rows = _rows(c)

    for r in rows:
        for field in ("aliases", "source_tags"):
            if isinstance(r.get(field), str):
                try:
                    r[field] = json.loads(r[field])
                except json.JSONDecodeError:
                    r[field] = []
        # Backward-compat: expose first tag as list_name
        tags = r.get("source_tags") or []
        r["list_name"] = tags[0] if tags else "Unknown"

    return rows


def get_sanctions_counts() -> dict:
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT list_name,
                   COUNT(DISTINCT canonical_id) AS n,
                   COUNT(*) AS entries
            FROM sanctions_memberships
            GROUP BY list_name
            ORDER BY list_name
        """)
        by_list = _rows(c)
        c.execute("SELECT COUNT(*) AS n FROM vessels_canonical")
        total = _row(c)["n"]
        c.execute("SELECT COUNT(*) AS n FROM vessels_canonical WHERE imo_number IS NOT NULL")
        with_imo = _row(c)["n"]
    return {"total": total, "with_imo": with_imo, "by_list": by_list}


# ── Canonical screening queries ───────────────────────────────────────────

def _screen_canonical(where_clause: str, params: list) -> list[dict]:
    """
    Query vessels_canonical with an arbitrary WHERE clause.
    Attaches all sanctions_memberships as a sub-list and synthesises
    backward-compatible fields (list_name, flag_state, program, entity_type).
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT canonical_id, entity_name, imo_number, mmsi, vessel_type,
                   flag_normalized, aliases, source_tags, match_method, created_at
            FROM vessels_canonical
            WHERE {where_clause}
        """, params)
        canonicals = _rows(c)

    result = []
    for can in canonicals:
        for field in ("aliases", "source_tags"):
            if isinstance(can.get(field), str):
                try:
                    can[field] = json.loads(can[field])
                except json.JSONDecodeError:
                    can[field] = []
        memberships = get_vessel_memberships(can["canonical_id"])
        can["memberships"] = memberships

        # Aggregate program (OFAC preferred)
        ofac_prog = next(
            (m["program"] for m in memberships
             if m.get("list_name") == "OFAC_SDN" and m.get("program")), None
        )
        can["program"]     = ofac_prog or next(
            (m["program"] for m in memberships if m.get("program")), None
        )
        # Backward-compat fields
        can["flag_state"]  = can.get("flag_normalized")
        can["entity_type"] = next(
            (m["entity_type"] for m in memberships if m.get("entity_type")), "Vessel"
        )
        tags = can.get("source_tags") or []
        can["list_name"]   = tags[0] if tags else "Unknown"
        result.append(can)
    return result


def search_sanctions_by_imo(imo: str) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    return _screen_canonical(f"imo_number = {p}", [imo])


def search_sanctions_by_mmsi(mmsi: str) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    return _screen_canonical(f"mmsi = {p}", [mmsi])


def search_sanctions_by_name(name: str, limit: int = 50) -> list[dict]:
    p  = "?" if _BACKEND == "sqlite" else "%s"
    op = "ILIKE" if _BACKEND == "postgres" else "LIKE"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT canonical_id
            FROM vessels_canonical
            WHERE entity_name {op} {p} OR aliases {op} {p}
            ORDER BY
                CASE WHEN entity_name {op} {p} THEN 0 ELSE 1 END,
                entity_name ASC
            LIMIT {p}
        """, [f"%{name}%", f"%{name}%", f"{name}%", limit])
        ids = [row["canonical_id"] for row in _rows(c)]

    result = []
    for cid in ids:
        result.extend(_screen_canonical(f"canonical_id = {p}", [cid]))
    return result


# ── Vessel registry (backed by vessels_canonical) ─────────────────────────

def get_vessels(q: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    params: list = []
    where = ""
    if q:
        op = "ILIKE" if _BACKEND == "postgres" else "LIKE"
        where = (
            f"WHERE entity_name {op} {p} OR imo_number = {p} OR mmsi = {p}"
        )
        params = [f"%{q}%", q, q]
    params.extend([limit, offset])
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT canonical_id, entity_name AS vessel_name, imo_number, mmsi,
                   vessel_type, flag_normalized AS flag_state,
                   source_tags, match_method, risk_score, created_at, updated_at
            FROM vessels_canonical
            {where}
            ORDER BY entity_name ASC
            LIMIT {p} OFFSET {p}
        """, params)
        rows = _rows(c)
    for r in rows:
        if isinstance(r.get("source_tags"), str):
            try:
                r["source_tags"] = json.loads(r["source_tags"])
            except json.JSONDecodeError:
                r["source_tags"] = []
    return rows


def get_vessel(imo: str) -> dict | None:
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(
            f"SELECT * FROM vessels_canonical WHERE imo_number = {p}", (imo,)
        )
        r = _row(c)
    if r:
        for field in ("aliases", "source_tags"):
            if isinstance(r.get(field), str):
                try:
                    r[field] = json.loads(r[field])
                except json.JSONDecodeError:
                    r[field] = []
    return r


def get_vessel_count() -> int:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM vessels_canonical")
        return c.fetchone()[0]


# ── Vessel membership detail (for profiles + reconciliation) ──────────────

def get_vessel_memberships(canonical_id: str) -> list[dict]:
    """
    Return all sanctions-list memberships for one canonical vessel.
    Used by screening (detail), vessel profiles, and reconciliation.
    """
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, canonical_id, list_name, source_id, entity_type,
                   program, flag_state, call_sign, gross_tonnage,
                   identifiers, created_at, updated_at
            FROM sanctions_memberships
            WHERE canonical_id = {p}
            ORDER BY list_name ASC
        """, (canonical_id,))
        rows = _rows(c)
    for r in rows:
        if isinstance(r.get("identifiers"), str):
            try:
                r["identifiers"] = json.loads(r["identifiers"])
            except json.JSONDecodeError:
                r["identifiers"] = {}
    return rows


# ── Reconciliation helpers ────────────────────────────────────────────────

def find_mmsi_imo_collisions() -> list[tuple[str, str]]:
    """
    Tier 2: find MMSI-keyed canonicals whose MMSI value also appears in
    an IMO-keyed canonical.  Returns list of (mmsi_canonical_id, imo_canonical_id).
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT a.canonical_id AS mmsi_cid,
                   b.canonical_id AS imo_cid
            FROM vessels_canonical a
            JOIN vessels_canonical b
                ON a.mmsi IS NOT NULL
               AND a.mmsi = b.mmsi
               AND a.canonical_id != b.canonical_id
            WHERE a.match_method = 'mmsi_exact'
              AND b.match_method = 'imo_exact'
        """)
        return [(r["mmsi_cid"], r["imo_cid"]) for r in _rows(c)]


def find_imo_collisions() -> list[tuple[str, list[str]]]:
    """
    Tier 1 safety sweep: find multiple canonicals with the same imo_number.
    Returns list of (imo_number, [canonical_id, ...]).
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT imo_number, COUNT(*) AS n
            FROM vessels_canonical
            WHERE imo_number IS NOT NULL
            GROUP BY imo_number
            HAVING COUNT(*) > 1
        """)
        dupes = _rows(c)

    p = "?" if _BACKEND == "sqlite" else "%s"
    result = []
    for d in dupes:
        imo = d["imo_number"]
        with _conn() as conn:
            c = _cursor(conn)
            c.execute(
                f"SELECT canonical_id FROM vessels_canonical WHERE imo_number = {p}",
                (imo,),
            )
            cids = [r["canonical_id"] for r in _rows(c)]
        result.append((imo, cids))
    return result


def merge_canonical(source_id: str, target_id: str) -> None:
    """
    Merge the source canonical into the target canonical:
      1. Reassign all memberships from source → target.
      2. Merge aliases + source_tags onto target.
      3. Promote imo_number / mmsi if source has them and target doesn't.
      4. Delete source canonical.
    """
    p        = "?" if _BACKEND == "sqlite" else "%s"
    jp       = _jp()
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"

    with _conn() as conn:
        c = _cursor(conn)

        c.execute(
            f"SELECT aliases, source_tags, imo_number, mmsi "
            f"FROM vessels_canonical WHERE canonical_id = {p}",
            (source_id,),
        )
        src = _row(c)
        c.execute(
            f"SELECT aliases, source_tags, imo_number, mmsi "
            f"FROM vessels_canonical WHERE canonical_id = {p}",
            (target_id,),
        )
        tgt = _row(c)
        if not src or not tgt:
            return

        def _parse(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return []
            return val or []

        merged_aliases = sorted(set(_parse(tgt["aliases"]) + _parse(src["aliases"])))
        merged_tags    = sorted(set(_parse(tgt["source_tags"]) + _parse(src["source_tags"])))

        # Reassign memberships
        c.execute(
            f"UPDATE sanctions_memberships SET canonical_id = {p} WHERE canonical_id = {p}",
            (target_id, source_id),
        )
        # Merge metadata onto target
        c.execute(f"""
            UPDATE vessels_canonical SET
                imo_number  = COALESCE(imo_number,  {p}),
                mmsi        = COALESCE(mmsi,        {p}),
                aliases     = {jp},
                source_tags = {jp},
                updated_at  = {now_expr}
            WHERE canonical_id = {p}
        """, (src["imo_number"], src["mmsi"],
              json.dumps(merged_aliases), json.dumps(merged_tags),
              target_id))
        # Delete source
        c.execute(
            f"DELETE FROM vessels_canonical WHERE canonical_id = {p}",
            (source_id,),
        )


def rebuild_all_source_tags() -> None:
    """
    Recompute source_tags on every vessels_canonical row from its memberships.
    Run after a reconciliation pass to ensure consistency.
    """
    p        = "?" if _BACKEND == "sqlite" else "%s"
    jp       = _jp()
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"

    with _conn() as conn:
        c = _cursor(conn)
        c.execute("SELECT canonical_id FROM vessels_canonical")
        cids = [r["canonical_id"] for r in _rows(c)]

    for cid in cids:
        memberships = get_vessel_memberships(cid)
        tags: list[str] = []
        for m in memberships:
            identifiers = m.get("identifiers") or {}
            new_tags = normalize.parse_source_tags(
                m["list_name"], identifiers
            )
            for t in new_tags:
                if t not in tags:
                    tags.append(t)
        tags.sort()

        with _conn() as conn:
            c = conn.cursor()
            c.execute(f"""
                UPDATE vessels_canonical SET source_tags = {jp}, updated_at = {now_expr}
                WHERE canonical_id = {p}
            """, (json.dumps(tags), cid))


def get_vessel_track(mmsi: str, hours: int = 72) -> list[dict]:
    """
    Return historical positions for a specific vessel, ordered chronologically.
    Used for drawing breadcrumb tracks on the map.
    """
    p = "?" if _BACKEND == "sqlite" else "%s"
    cutoff_expr = (
        f"datetime('now', '-{hours} hours')"
        if _BACKEND == "sqlite"
        else f"NOW() - INTERVAL '{hours} hours'"
    )
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT lat, lon, position_ts, sog, cog
            FROM ais_positions
            WHERE mmsi = {p}
              AND position_ts >= {cutoff_expr}
            ORDER BY position_ts ASC
        """, (mmsi,))
        return _rows(c)


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

        # Unique canonical vessels (the headline number)
        try:
            c.execute("SELECT COUNT(*) AS n FROM vessels_canonical")
            total_sanctions = _row(c)["n"]
        except Exception:
            total_sanctions = 0

        # Per-list counts from memberships (distinct canonical vessels per list)
        try:
            c.execute("""
                SELECT list_name, COUNT(DISTINCT canonical_id) AS n
                FROM sanctions_memberships
                GROUP BY list_name
                ORDER BY list_name
            """)
            by_list = {r["list_name"]: r["n"] for r in _rows(c)}
        except Exception:
            by_list = {}

        c.execute("""
            SELECT source_name, status, records_inserted, completed_at
            FROM ingest_log
            ORDER BY id DESC
            LIMIT 10
        """)
        recent_ingests = _rows(c)

        # AIS + detection stats (tables may not exist in older dbs)
        try:
            c.execute("SELECT COUNT(*) AS n FROM ais_positions")
            total_ais_positions = _row(c)["n"]
            c.execute("SELECT COUNT(*) AS n FROM ais_vessels")
            total_ais_vessels = _row(c)["n"]
            c.execute("SELECT COUNT(*) AS n FROM dark_periods")
            total_dark_periods = _row(c)["n"]
            c.execute("SELECT COUNT(*) AS n FROM sts_events")
            total_sts_events = _row(c)["n"]
            c.execute("SELECT COUNT(*) AS n FROM spoof_events")
            total_spoof_events = _row(c)["n"]
        except Exception:
            total_ais_positions = total_ais_vessels = total_dark_periods = total_sts_events = total_spoof_events = 0

    return {
        "total_sanctions":     total_sanctions,
        "total_vessels":       total_sanctions,   # backward compat alias
        "by_list":             by_list,
        "recent_ingests":      recent_ingests,
        "total_ais_positions": total_ais_positions,
        "total_ais_vessels":   total_ais_vessels,
        "total_dark_periods":  total_dark_periods,
        "total_sts_events":    total_sts_events,
        "total_spoof_events":   total_spoof_events,
    }


# ── AIS positions ──────────────────────────────────────────────────────────

def insert_ais_positions(positions: list[dict]) -> int:
    """Batch-insert AIS positions. Silently skips duplicates. Returns insert count."""
    if not positions:
        return 0
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
                    c.execute("""
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
                c.execute("""
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
    params = [*mmsi_params, min_hours, limit]
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(query, params)
        return _rows(c)


def upsert_dark_periods(periods: list[dict]) -> int:
    """Persist detected dark periods. Returns count inserted."""
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


# ── STS event detection ───────────────────────────────────────────────────

def find_sts_candidates(
    hours_back: int = 48,
    max_sog: float = 3.0,
    limit: int = 2000,
) -> list[dict]:
    """
    Bounding-box SQL self-join to find candidate STS pairs.
    Returns rows with lat1/lon1/lat2/lon2 for Haversine post-filter in Python.
    Keeps the query light with a 0.05° spatial pre-filter and 30-min temporal window.
    """
    p = "?" if _BACKEND == "sqlite" else "%s"

    if _BACKEND == "sqlite":
        cutoff = f"datetime('now', '-{hours_back} hours')"
        time_diff = "ABS(julianday(a.position_ts) - julianday(b.position_ts)) * 1440"
    else:
        cutoff = f"NOW() - INTERVAL '{hours_back} hours'"
        time_diff = "ABS(EXTRACT(EPOCH FROM (a.position_ts - b.position_ts))) / 60"

    query = f"""
        SELECT
            a.mmsi           AS mmsi1,
            b.mmsi           AS mmsi2,
            a.vessel_name    AS vessel_name1,
            b.vessel_name    AS vessel_name2,
            a.lat  AS lat1,  a.lon  AS lon1,
            b.lat  AS lat2,  b.lon  AS lon2,
            a.sog  AS sog1,  b.sog  AS sog2,
            a.position_ts    AS ts
        FROM ais_positions a
        JOIN ais_positions b ON (
            a.mmsi < b.mmsi
            AND {time_diff} <= 30
            AND ABS(a.lat - b.lat) < 0.05
            AND ABS(a.lon - b.lon) < 0.05
        )
        WHERE a.position_ts >= {cutoff}
          AND (a.sog IS NULL OR a.sog <= {p}
               OR b.sog IS NULL OR b.sog <= {p})
        ORDER BY a.position_ts DESC
        LIMIT {p}
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(query, [max_sog, max_sog, limit])
        return _rows(c)


def upsert_sts_events(events: list[dict]) -> int:
    """Persist STS events. Returns count inserted/updated."""
    if not events:
        return 0
    inserted = 0
    with _conn() as conn:
        c = conn.cursor()
        for ev in events:
            # Normalise mmsi order so (A,B) and (B,A) collapse to the same row
            m1, m2 = sorted([str(ev.get("mmsi1", "")), str(ev.get("mmsi2", ""))])
            try:
                if _BACKEND == "postgres":
                    c.execute(f"""
                        INSERT INTO sts_events (
                            mmsi1, mmsi2, vessel_name1, vessel_name2,
                            event_ts, lat, lon, distance_m,
                            sog1, sog2, risk_zone, risk_level,
                            sanctions_hit, indicator_code
                        ) VALUES ({_ph(14)})
                        ON CONFLICT (mmsi1, mmsi2, event_ts) DO UPDATE SET
                            vessel_name1 = COALESCE(EXCLUDED.vessel_name1, sts_events.vessel_name1),
                            vessel_name2 = COALESCE(EXCLUDED.vessel_name2, sts_events.vessel_name2),
                            distance_m   = EXCLUDED.distance_m,
                            risk_zone    = EXCLUDED.risk_zone,
                            risk_level   = EXCLUDED.risk_level,
                            sanctions_hit= EXCLUDED.sanctions_hit
                    """, (
                        m1, m2,
                        ev.get("vessel_name1"), ev.get("vessel_name2"),
                        ev.get("event_ts"),
                        ev.get("lat"), ev.get("lon"),
                        ev.get("distance_m"),
                        ev.get("sog1"), ev.get("sog2"),
                        ev.get("risk_zone"), ev.get("risk_level"),
                        ev.get("sanctions_hit", False),
                        ev.get("indicator_code", "IND7"),
                    ))
                else:
                    c.execute("""
                        INSERT OR REPLACE INTO sts_events (
                            mmsi1, mmsi2, vessel_name1, vessel_name2,
                            event_ts, lat, lon, distance_m,
                            sog1, sog2, risk_zone, risk_level,
                            sanctions_hit, indicator_code
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        m1, m2,
                        ev.get("vessel_name1"), ev.get("vessel_name2"),
                        ev.get("event_ts"),
                        ev.get("lat"), ev.get("lon"),
                        ev.get("distance_m"),
                        ev.get("sog1"), ev.get("sog2"),
                        ev.get("risk_zone"), ev.get("risk_level"),
                        1 if ev.get("sanctions_hit") else 0,
                        ev.get("indicator_code", "IND7"),
                    ))
                inserted += 1
            except Exception:
                pass
    return inserted


def get_sts_events(
    limit: int = 200,
    offset: int = 0,
    mmsi: str | None = None,
    risk_level: str | None = None,
    sanctions_only: bool = False,
) -> list[dict]:
    p = "?" if _BACKEND == "sqlite" else "%s"
    clauses: list[str] = []
    params: list = []

    if mmsi:
        clauses.append(f"(mmsi1 = {p} OR mmsi2 = {p})")
        params.extend([mmsi, mmsi])
    if risk_level:
        clauses.append(f"risk_level = {p}")
        params.append(risk_level)
    if sanctions_only:
        clauses.append(f"sanctions_hit = {p}")
        params.append(True if _BACKEND == "postgres" else 1)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])

    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT id, mmsi1, mmsi2, vessel_name1, vessel_name2,
                   event_ts, lat, lon, distance_m,
                   sog1, sog2, risk_zone, risk_level,
                   sanctions_hit, indicator_code, created_at
            FROM sts_events
            {where}
            ORDER BY event_ts DESC
            LIMIT {p} OFFSET {p}
        """, params)
        rows = _rows(c)

    for r in rows:
        r["sanctions_hit"] = bool(r.get("sanctions_hit"))
    return rows


# ── Spoofing event detection ──────────────────────────────────────────────

def upsert_spoof_events(events: list[dict]) -> int:
    """Persist detected spoofing events. Returns count inserted/updated."""
    if not events:
        return 0
    inserted = 0
    with _conn() as conn:
        c = conn.cursor()
        for ev in events:
            try:
                detail_json = json.dumps(ev.get("detail", {}))
                if _BACKEND == "postgres":
                    c.execute(f"""
                        INSERT INTO spoof_events (
                            mmsi, imo_number, vessel_name, spoof_type,
                            detected_at, lat, lon, detail,
                            risk_level, sanctions_hit, risk_zone, indicator_code
                        ) VALUES ({_ph(12)})
                        ON CONFLICT (mmsi, spoof_type, detected_at) DO UPDATE SET
                            lat           = EXCLUDED.lat,
                            lon           = EXCLUDED.lon,
                            detail        = EXCLUDED.detail,
                            risk_level    = EXCLUDED.risk_level,
                            sanctions_hit = EXCLUDED.sanctions_hit,
                            risk_zone     = EXCLUDED.risk_zone
                    """, (
                        ev.get("mmsi"), ev.get("imo_number"), ev.get("vessel_name"),
                        ev.get("spoof_type"), ev.get("detected_at"),
                        ev.get("lat"), ev.get("lon"), detail_json,
                        ev.get("risk_level", "LOW"),
                        ev.get("sanctions_hit", False),
                        ev.get("risk_zone"),
                        ev.get("indicator_code", "IND_SPOOF"),
                    ))
                else:
                    c.execute("""
                        INSERT OR REPLACE INTO spoof_events (
                            mmsi, imo_number, vessel_name, spoof_type,
                            detected_at, lat, lon, detail,
                            risk_level, sanctions_hit, risk_zone, indicator_code
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        ev.get("mmsi"), ev.get("imo_number"), ev.get("vessel_name"),
                        ev.get("spoof_type"), ev.get("detected_at"),
                        ev.get("lat"), ev.get("lon"), detail_json,
                        ev.get("risk_level", "LOW"),
                        1 if ev.get("sanctions_hit") else 0,
                        ev.get("risk_zone"),
                        ev.get("indicator_code", "IND_SPOOF"),
                    ))
                inserted += 1
            except Exception:
                pass
    return inserted


def get_spoof_events(limit: int = 200, offset: int = 0,
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
            SELECT id, mmsi, imo_number, vessel_name, spoof_type,
                   detected_at, lat, lon, detail, risk_level,
                   sanctions_hit, risk_zone, indicator_code, created_at
            FROM spoof_events
            {where}
            ORDER BY detected_at DESC
            LIMIT {p} OFFSET {p}
        """, params)
        rows = _rows(c)
    for r in rows:
        r["sanctions_hit"] = bool(r.get("sanctions_hit"))
        if isinstance(r.get("detail"), str):
            try:
                r["detail"] = json.loads(r["detail"])
            except json.JSONDecodeError:
                r["detail"] = {}
    return rows


# ── Map data ───────────────────────────────────────────────────────────────

def get_map_vessels_raw(
    hours: int = 48,
    dp_days: int = 7,
    sts_days: int = 7,
    limit: int = 1000,
) -> list[dict]:
    """
    Return AIS vessel positions for the live risk map.

    Uses CTEs to pre-aggregate dark_periods and sts_events once, then
    LEFT JOINs — avoids the O(n) correlated-subquery scan that was
    issuing ~20 000 sub-executions for a 5 k vessel table.

    Sanctions is kept as a correlated subquery because vessels_canonical
    is small (~2 500 rows) and an OR-join against it would fan out rows.

    Returns up to `limit` rows ordered highest-risk first so the most
    important vessels always appear when the result is capped.
    """
    if _BACKEND == "sqlite":
        av_cutoff  = f"datetime('now', '-{hours} hours')"
        dp_cutoff  = f"datetime('now', '-{dp_days} days')"
        sts_cutoff = f"datetime('now', '-{sts_days} days')"
    else:
        av_cutoff  = f"NOW() - INTERVAL '{hours} hours'"
        dp_cutoff  = f"NOW() - INTERVAL '{dp_days} days'"
        sts_cutoff = f"NOW() - INTERVAL '{sts_days} days'"

    risk_case = """CASE risk_level
                       WHEN 'CRITICAL' THEN 4
                       WHEN 'HIGH'     THEN 3
                       WHEN 'MEDIUM'   THEN 2
                       WHEN 'LOW'      THEN 1
                       ELSE 0 END"""

    query = f"""
        WITH
        -- Pre-aggregate dark period risk per MMSI (one GROUP BY scan)
        dp_agg AS (
            SELECT mmsi,
                   MAX({risk_case}) AS risk_num
            FROM   dark_periods
            WHERE  gap_start >= {dp_cutoff}
            GROUP  BY mmsi
        ),
        -- Pre-aggregate STS risk per MMSI (UNION covers both sides)
        sts_side AS (
            SELECT mmsi1 AS mmsi, {risk_case} AS rn
            FROM   sts_events WHERE event_ts >= {sts_cutoff}
            UNION ALL
            SELECT mmsi2 AS mmsi, {risk_case} AS rn
            FROM   sts_events WHERE event_ts >= {sts_cutoff}
        ),
        sts_agg AS (
            SELECT mmsi, MAX(rn) AS risk_num
            FROM   sts_side
            GROUP  BY mmsi
        )
        SELECT
            av.mmsi,
            av.imo_number,
            av.vessel_name,
            av.vessel_type,
            av.flag_state,
            av.last_lat,
            av.last_lon,
            av.last_cog,
            av.last_sog,
            av.last_nav_status,
            av.last_seen,
            av.destination,
            av.call_sign,
            av.length,
            av.draft,
            -- Sanctions: correlated subquery is fine — vessels_canonical is ~2 500 rows
            CASE WHEN EXISTS (
                SELECT 1 FROM vessels_canonical vc
                WHERE vc.mmsi = av.mmsi
                   OR (av.imo_number IS NOT NULL
                       AND av.imo_number != ''
                       AND vc.imo_number = av.imo_number)
            ) THEN 1 ELSE 0 END AS sanctioned,
            (SELECT vc2.source_tags
             FROM   vessels_canonical vc2
             WHERE  vc2.mmsi = av.mmsi
                OR  (av.imo_number IS NOT NULL
                     AND av.imo_number != ''
                     AND vc2.imo_number = av.imo_number)
             LIMIT 1) AS source_tags,
            COALESCE(dp.risk_num,  0) AS dp_risk_num,
            COALESCE(sts.risk_num, 0) AS sts_risk_num
        FROM  ais_vessels av
        LEFT  JOIN dp_agg  dp  ON dp.mmsi  = av.mmsi
        LEFT  JOIN sts_agg sts ON sts.mmsi = av.mmsi
        WHERE av.last_lat  IS NOT NULL
          AND av.last_lon  IS NOT NULL
          AND av.last_seen >= {av_cutoff}
        ORDER BY
            -- Sanctioned vessels first, then highest behavioural risk
            CASE WHEN EXISTS (
                SELECT 1 FROM vessels_canonical vc2
                WHERE vc2.mmsi = av.mmsi
                   OR (av.imo_number IS NOT NULL
                       AND av.imo_number != ''
                       AND vc2.imo_number = av.imo_number)
            ) THEN 1 ELSE 0 END DESC,
            COALESCE(dp.risk_num, 0) + COALESCE(sts.risk_num, 0) DESC
        LIMIT {limit}
    """

    with _conn() as conn:
        c = _cursor(conn)
        c.execute(query)
        return _rows(c)
