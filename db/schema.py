# db/schema.py
"""Schema initialization — CREATE TABLE / CREATE INDEX DDL for all tables."""

from .connection import _BACKEND, _conn, _ph  # noqa: F401


# ── Schema ────────────────────────────────────────────────────────────────

def _migrate_vessels_canonical() -> None:
    """
    Add columns introduced after initial schema creation (idempotent).
    Postgres supports ADD COLUMN IF NOT EXISTS; SQLite needs try/except per column.
    """
    if _BACKEND == "postgres":
        with _conn() as conn:
            c = conn.cursor()
            for stmt in [
                "ALTER TABLE vessels_canonical ADD COLUMN IF NOT EXISTS build_year    INTEGER",
                "ALTER TABLE vessels_canonical ADD COLUMN IF NOT EXISTS call_sign     VARCHAR(50)",
                "ALTER TABLE vessels_canonical ADD COLUMN IF NOT EXISTS gross_tonnage INTEGER",
            ]:
                c.execute(stmt)
    else:
        for col, col_type in [
            ("build_year",    "INTEGER"),
            ("call_sign",     "TEXT"),
            ("gross_tonnage", "INTEGER"),
        ]:
            try:
                with _conn() as conn:
                    conn.cursor().execute(
                        f"ALTER TABLE vessels_canonical ADD COLUMN {col} {col_type}"
                    )
            except Exception:
                pass  # Column already exists — safe to ignore


def init_db() -> None:
    """Create all tables and indexes (idempotent)."""
    with _conn() as conn:
        c = conn.cursor()

        if _BACKEND == "postgres":
            _init_postgres(c)
        else:
            _init_sqlite(c)

    _migrate_vessels_canonical()


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

    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_ownership (
            id           SERIAL PRIMARY KEY,
            canonical_id VARCHAR(50) NOT NULL
                         REFERENCES vessels_canonical(canonical_id) ON DELETE CASCADE,
            role         VARCHAR(50)  NOT NULL,
            entity_name  VARCHAR(500) NOT NULL,
            source       VARCHAR(100) NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(canonical_id, role, entity_name, source)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_vo_canonical ON vessel_ownership(canonical_id)")

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

    # ── Session 8: AIS speed anomalies ────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS ais_anomalies (
            id               SERIAL PRIMARY KEY,
            mmsi             VARCHAR(20) NOT NULL,
            imo_number       VARCHAR(20),
            vessel_name      VARCHAR(255),
            anomaly_type     VARCHAR(50)  DEFAULT 'speed_jump',
            event_ts         TIMESTAMPTZ  NOT NULL,
            lat              DOUBLE PRECISION,
            lon              DOUBLE PRECISION,
            prev_lat         DOUBLE PRECISION,
            prev_lon         DOUBLE PRECISION,
            implied_speed_kt REAL,
            distance_km      REAL,
            time_delta_min   REAL,
            risk_level       VARCHAR(20)  DEFAULT 'HIGH',
            indicator_code   VARCHAR(10)  DEFAULT 'IND10',
            created_at       TIMESTAMPTZ  DEFAULT NOW(),
            UNIQUE(mmsi, event_ts)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_anom_mmsi ON ais_anomalies(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_anom_ts   ON ais_anomalies(event_ts DESC)")

    # ── Session 9: Loitering events (IND9) ────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS loitering_events (
            id             SERIAL PRIMARY KEY,
            mmsi           VARCHAR(20) NOT NULL,
            imo_number     VARCHAR(20),
            vessel_name    VARCHAR(255),
            loiter_start   TIMESTAMPTZ NOT NULL,
            loiter_end     TIMESTAMPTZ NOT NULL,
            loiter_hours   REAL NOT NULL,
            center_lat     DOUBLE PRECISION NOT NULL,
            center_lon     DOUBLE PRECISION NOT NULL,
            risk_zone      VARCHAR(100),
            risk_level     VARCHAR(20),
            sanctions_hit  BOOLEAN DEFAULT FALSE,
            indicator_code VARCHAR(10) DEFAULT 'IND9',
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(mmsi, loiter_start)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_loiter_mmsi ON loitering_events(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_loiter_ts   ON loitering_events(loiter_start DESC)")

    # ── Session 9: Sanctioned port calls (IND29) ──────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS port_calls (
            id               SERIAL PRIMARY KEY,
            mmsi             VARCHAR(20) NOT NULL,
            imo_number       VARCHAR(20),
            vessel_name      VARCHAR(255),
            port_name        VARCHAR(200) NOT NULL,
            port_country     VARCHAR(100) NOT NULL,
            sanctions_level  VARCHAR(20)  NOT NULL,
            arrival_ts       TIMESTAMPTZ  NOT NULL,
            departure_ts     TIMESTAMPTZ,
            center_lat       DOUBLE PRECISION NOT NULL,
            center_lon       DOUBLE PRECISION NOT NULL,
            distance_km      REAL,
            indicator_code   VARCHAR(10) DEFAULT 'IND29',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(mmsi, port_name, arrival_ts)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_portcall_mmsi ON port_calls(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_portcall_ts   ON port_calls(arrival_ts DESC)")

    # ── Session 10: PSC detention records (IND31) ─────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS psc_detentions (
            id               SERIAL PRIMARY KEY,
            imo_number       VARCHAR(20) NOT NULL,
            vessel_name      VARCHAR(255),
            flag_state       VARCHAR(100),
            detention_date   DATE,
            release_date     DATE,
            port_name        VARCHAR(200),
            port_country     VARCHAR(100),
            authority        VARCHAR(50),
            deficiency_count INTEGER,
            list_source      VARCHAR(20),
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(imo_number, detention_date, authority)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_psc_imo ON psc_detentions(imo_number)")


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

    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_ownership (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id TEXT NOT NULL
                         REFERENCES vessels_canonical(canonical_id) ON DELETE CASCADE,
            role         TEXT NOT NULL,
            entity_name  TEXT NOT NULL,
            source       TEXT NOT NULL,
            created_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(canonical_id, role, entity_name, source)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_vo_canonical ON vessel_ownership(canonical_id)")

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

    # ── Session 8: AIS speed anomalies ────────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS ais_anomalies (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi             TEXT NOT NULL,
            imo_number       TEXT,
            vessel_name      TEXT,
            anomaly_type     TEXT DEFAULT 'speed_jump',
            event_ts         TEXT NOT NULL,
            lat              REAL,
            lon              REAL,
            prev_lat         REAL,
            prev_lon         REAL,
            implied_speed_kt REAL,
            distance_km      REAL,
            time_delta_min   REAL,
            risk_level       TEXT DEFAULT 'HIGH',
            indicator_code   TEXT DEFAULT 'IND10',
            created_at       TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi, event_ts)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_anom_mmsi ON ais_anomalies(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_anom_ts   ON ais_anomalies(event_ts DESC)")

    # ── Session 9: Loitering events (IND9) ────────────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS loitering_events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi           TEXT NOT NULL,
            imo_number     TEXT,
            vessel_name    TEXT,
            loiter_start   TEXT NOT NULL,
            loiter_end     TEXT NOT NULL,
            loiter_hours   REAL NOT NULL,
            center_lat     REAL NOT NULL,
            center_lon     REAL NOT NULL,
            risk_zone      TEXT,
            risk_level     TEXT,
            sanctions_hit  INTEGER DEFAULT 0,
            indicator_code TEXT DEFAULT 'IND9',
            created_at     TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi, loiter_start)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_loiter_mmsi ON loitering_events(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_loiter_ts   ON loitering_events(loiter_start DESC)")

    # ── Session 9: Sanctioned port calls (IND29) ──────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS port_calls (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi            TEXT NOT NULL,
            imo_number      TEXT,
            vessel_name     TEXT,
            port_name       TEXT NOT NULL,
            port_country    TEXT NOT NULL,
            sanctions_level TEXT NOT NULL,
            arrival_ts      TEXT NOT NULL,
            departure_ts    TEXT,
            center_lat      REAL NOT NULL,
            center_lon      REAL NOT NULL,
            distance_km     REAL,
            indicator_code  TEXT DEFAULT 'IND29',
            created_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(mmsi, port_name, arrival_ts)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_portcall_mmsi ON port_calls(mmsi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_portcall_ts   ON port_calls(arrival_ts DESC)")

    # ── Session 10: PSC detention records (IND31) ─────────────────────────

    c.execute("""
        CREATE TABLE IF NOT EXISTS psc_detentions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            imo_number      TEXT NOT NULL,
            vessel_name     TEXT,
            flag_state      TEXT,
            detention_date  TEXT,
            release_date    TEXT,
            port_name       TEXT,
            port_country    TEXT,
            authority       TEXT,
            deficiency_count INTEGER,
            list_source     TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(imo_number, detention_date, authority)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_psc_imo ON psc_detentions(imo_number)")
