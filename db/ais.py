# db/ais.py
"""AIS position and vessel static data CRUD."""

import json  # noqa: F401

from .connection import _BACKEND, _conn, _cursor, _rows, _row, _ph, _ilike, _jp  # noqa: F401


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


def get_consecutive_ais_pairs(
    mmsi: str | None = None,
    hours_back: int = 168,
    limit: int = 5000,
) -> list[dict]:
    """
    Return consecutive AIS position pairs with time delta in minutes.
    Used by spoofing.py for IND10 speed-anomaly detection.
    """
    p = "?" if _BACKEND == "sqlite" else "%s"

    if _BACKEND == "sqlite":
        cutoff  = f"datetime('now', '-{hours_back} hours')"
        td_expr = "(julianday(next_ts) - julianday(position_ts)) * 1440"
    else:
        cutoff  = f"NOW() - INTERVAL '{hours_back} hours'"
        td_expr = "EXTRACT(EPOCH FROM (next_ts - position_ts)) / 60"

    mmsi_filter = f"AND mmsi = {p}" if mmsi else ""
    mmsi_params = [mmsi] if mmsi else []

    query = f"""
        WITH ordered AS (
            SELECT mmsi, imo_number, vessel_name,
                   lat, lon, position_ts,
                   LEAD(position_ts) OVER (PARTITION BY mmsi ORDER BY position_ts) AS next_ts,
                   LEAD(lat)         OVER (PARTITION BY mmsi ORDER BY position_ts) AS next_lat,
                   LEAD(lon)         OVER (PARTITION BY mmsi ORDER BY position_ts) AS next_lon
            FROM ais_positions
            WHERE position_ts >= {cutoff}
            {mmsi_filter}
        )
        SELECT mmsi, imo_number, vessel_name,
               position_ts, next_ts,
               lat, lon, next_lat, next_lon,
               {td_expr} AS time_delta_min
        FROM ordered
        WHERE next_ts IS NOT NULL
        ORDER BY mmsi, position_ts
        LIMIT {p}
    """
    params = mmsi_params + [limit]
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(query, params)
        return _rows(c)


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
