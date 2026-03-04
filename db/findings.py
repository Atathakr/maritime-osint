# db/findings.py
"""
Detection results CRUD.

Covers all five detection domains:
  - dark_periods (AIS gap events)
  - sts_transfers (ship-to-ship transfer events)
  - loitering_reports
  - spoofing_events (speed anomalies via ais_anomalies table)
  - port_calls
"""

import json  # noqa: F401

from .connection import _BACKEND, _conn, _cursor, _rows, _row, _ph, _ilike, _jp  # noqa: F401


# ── Dark periods ──────────────────────────────────────────────────────────

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


# ── STS events ────────────────────────────────────────────────────────────

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


def get_sts_zone_count(mmsi: str) -> int:
    """Count STS events in a named high-risk zone for a given MMSI (IND8)."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT COUNT(*) AS n FROM sts_events
            WHERE (mmsi1 = {p} OR mmsi2 = {p}) AND risk_zone IS NOT NULL
        """, (mmsi, mmsi))
        row = _row(c)
        return (row["n"] if row else 0) or 0


# ── Speed anomalies ───────────────────────────────────────────────────────

def upsert_speed_anomalies(anomalies: list[dict]) -> int:
    """
    Bulk-insert speed anomaly records.  Silently skips duplicates.
    Returns the number of rows actually inserted.
    """
    if not anomalies:
        return 0

    inserted = 0
    with _conn() as conn:
        c = _cursor(conn)
        for a in anomalies:
            try:
                if _BACKEND == "postgres":
                    c.execute("""
                        INSERT INTO ais_anomalies
                            (mmsi, imo_number, vessel_name, anomaly_type,
                             event_ts, lat, lon, prev_lat, prev_lon,
                             implied_speed_kt, distance_km, time_delta_min,
                             risk_level, indicator_code)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (mmsi, event_ts) DO NOTHING
                    """, (
                        a.get("mmsi"), a.get("imo_number"), a.get("vessel_name"),
                        a.get("anomaly_type", "speed_jump"),
                        a.get("event_ts"),
                        a.get("lat"), a.get("lon"),
                        a.get("prev_lat"), a.get("prev_lon"),
                        a.get("implied_speed_kt"), a.get("distance_km"),
                        a.get("time_delta_min"),
                        a.get("risk_level", "HIGH"), a.get("indicator_code", "IND10"),
                    ))
                    inserted += c.rowcount
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO ais_anomalies
                            (mmsi, imo_number, vessel_name, anomaly_type,
                             event_ts, lat, lon, prev_lat, prev_lon,
                             implied_speed_kt, distance_km, time_delta_min,
                             risk_level, indicator_code)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        a.get("mmsi"), a.get("imo_number"), a.get("vessel_name"),
                        a.get("anomaly_type", "speed_jump"),
                        a.get("event_ts"),
                        a.get("lat"), a.get("lon"),
                        a.get("prev_lat"), a.get("prev_lon"),
                        a.get("implied_speed_kt"), a.get("distance_km"),
                        a.get("time_delta_min"),
                        a.get("risk_level", "HIGH"), a.get("indicator_code", "IND10"),
                    ))
                    inserted += conn.total_changes
            except Exception:
                pass  # Duplicate or constraint violation — skip
    return inserted


def get_speed_anomaly_summary(mmsi: str) -> dict:
    """
    Return speed-anomaly count and latest anomaly details for a given MMSI.

    Returns a dict with keys:
      spoof_count, spoof_last_ts, spoof_last_lat, spoof_last_lon, spoof_last_speed_kt
    """
    p = "?" if _BACKEND == "sqlite" else "%s"
    result: dict = {
        "spoof_count": 0,
        "spoof_last_ts": None,
        "spoof_last_lat": None,
        "spoof_last_lon": None,
        "spoof_last_speed_kt": None,
    }
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"SELECT COUNT(*) AS n FROM ais_anomalies WHERE mmsi = {p}", (mmsi,))
        row = _row(c)
        result["spoof_count"] = (row["n"] if row else 0) or 0

        if result["spoof_count"] > 0:
            c.execute(f"""
                SELECT event_ts, lat, lon, implied_speed_kt
                FROM ais_anomalies
                WHERE mmsi = {p}
                ORDER BY event_ts DESC
                LIMIT 1
            """, (mmsi,))
            row = _row(c)
            if row:
                result["spoof_last_ts"]       = row.get("event_ts")
                result["spoof_last_lat"]      = row.get("lat")
                result["spoof_last_lon"]      = row.get("lon")
                result["spoof_last_speed_kt"] = row.get("implied_speed_kt")
    return result


# ── Loitering events ──────────────────────────────────────────────────────

def upsert_loitering_events(episodes: list[dict]) -> int:
    """
    Bulk-insert loitering event records.  Silently skips duplicates.
    Returns the number of rows actually inserted.
    """
    if not episodes:
        return 0

    inserted = 0
    with _conn() as conn:
        c = _cursor(conn)
        for e in episodes:
            try:
                if _BACKEND == "postgres":
                    c.execute("""
                        INSERT INTO loitering_events
                            (mmsi, imo_number, vessel_name,
                             loiter_start, loiter_end, loiter_hours,
                             center_lat, center_lon,
                             risk_zone, risk_level, sanctions_hit, indicator_code)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (mmsi, loiter_start) DO NOTHING
                    """, (
                        e.get("mmsi"), e.get("imo_number"), e.get("vessel_name"),
                        e.get("loiter_start"), e.get("loiter_end"), e.get("loiter_hours"),
                        e.get("center_lat"), e.get("center_lon"),
                        e.get("risk_zone"), e.get("risk_level"),
                        e.get("sanctions_hit", False), e.get("indicator_code", "IND9"),
                    ))
                    inserted += c.rowcount
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO loitering_events
                            (mmsi, imo_number, vessel_name,
                             loiter_start, loiter_end, loiter_hours,
                             center_lat, center_lon,
                             risk_zone, risk_level, sanctions_hit, indicator_code)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        e.get("mmsi"), e.get("imo_number"), e.get("vessel_name"),
                        e.get("loiter_start"), e.get("loiter_end"), e.get("loiter_hours"),
                        e.get("center_lat"), e.get("center_lon"),
                        e.get("risk_zone"), e.get("risk_level"),
                        1 if e.get("sanctions_hit") else 0, e.get("indicator_code", "IND9"),
                    ))
                    inserted += conn.total_changes
            except Exception:
                pass
    return inserted


def get_loitering_summary(mmsi: str) -> dict:
    """
    Return loitering count and latest event details for a given MMSI.

    Returns a dict with keys:
      loiter_count, loiter_last_ts, loiter_last_lat, loiter_last_lon,
      loiter_last_hours, loiter_last_zone
    """
    p = "?" if _BACKEND == "sqlite" else "%s"
    result: dict = {
        "loiter_count": 0,
        "loiter_last_ts": None,
        "loiter_last_lat": None,
        "loiter_last_lon": None,
        "loiter_last_hours": None,
        "loiter_last_zone": None,
    }
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"SELECT COUNT(*) AS n FROM loitering_events WHERE mmsi = {p}", (mmsi,))
        row = _row(c)
        result["loiter_count"] = (row["n"] if row else 0) or 0

        if result["loiter_count"] > 0:
            c.execute(f"""
                SELECT loiter_start, center_lat, center_lon, loiter_hours, risk_zone
                FROM loitering_events
                WHERE mmsi = {p}
                ORDER BY loiter_start DESC
                LIMIT 1
            """, (mmsi,))
            row = _row(c)
            if row:
                result["loiter_last_ts"]    = row.get("loiter_start")
                result["loiter_last_lat"]   = row.get("center_lat")
                result["loiter_last_lon"]   = row.get("center_lon")
                result["loiter_last_hours"] = row.get("loiter_hours")
                result["loiter_last_zone"]  = row.get("risk_zone")
    return result


# ── Port calls ────────────────────────────────────────────────────────────

def upsert_port_calls(calls: list[dict]) -> int:
    """
    Bulk-insert port call records.  Silently skips duplicates.
    Returns the number of rows actually inserted.
    """
    if not calls:
        return 0

    inserted = 0
    with _conn() as conn:
        c = _cursor(conn)
        for pc in calls:
            try:
                if _BACKEND == "postgres":
                    c.execute("""
                        INSERT INTO port_calls
                            (mmsi, imo_number, vessel_name,
                             port_name, port_country, sanctions_level,
                             arrival_ts, departure_ts,
                             center_lat, center_lon, distance_km, indicator_code)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (mmsi, port_name, arrival_ts) DO NOTHING
                    """, (
                        pc.get("mmsi"), pc.get("imo_number"), pc.get("vessel_name"),
                        pc.get("port_name"), pc.get("port_country"), pc.get("sanctions_level"),
                        pc.get("arrival_ts"), pc.get("departure_ts"),
                        pc.get("center_lat"), pc.get("center_lon"),
                        pc.get("distance_km"), pc.get("indicator_code", "IND29"),
                    ))
                    inserted += c.rowcount
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO port_calls
                            (mmsi, imo_number, vessel_name,
                             port_name, port_country, sanctions_level,
                             arrival_ts, departure_ts,
                             center_lat, center_lon, distance_km, indicator_code)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        pc.get("mmsi"), pc.get("imo_number"), pc.get("vessel_name"),
                        pc.get("port_name"), pc.get("port_country"), pc.get("sanctions_level"),
                        pc.get("arrival_ts"), pc.get("departure_ts"),
                        pc.get("center_lat"), pc.get("center_lon"),
                        pc.get("distance_km"), pc.get("indicator_code", "IND29"),
                    ))
                    inserted += conn.total_changes
            except Exception:
                pass
    return inserted


def get_port_call_summary(mmsi: str) -> dict:
    """
    Return sanctioned port call count and latest event details for a given MMSI.

    Returns a dict with keys:
      port_count, port_last_name, port_last_country, port_last_ts, port_last_level
    """
    p = "?" if _BACKEND == "sqlite" else "%s"
    result: dict = {
        "port_count": 0,
        "port_last_name": None,
        "port_last_country": None,
        "port_last_ts": None,
        "port_last_level": None,
    }
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"SELECT COUNT(*) AS n FROM port_calls WHERE mmsi = {p}", (mmsi,))
        row = _row(c)
        result["port_count"] = (row["n"] if row else 0) or 0

        if result["port_count"] > 0:
            c.execute(f"""
                SELECT arrival_ts, port_name, port_country, sanctions_level
                FROM port_calls
                WHERE mmsi = {p}
                ORDER BY arrival_ts DESC
                LIMIT 1
            """, (mmsi,))
            row = _row(c)
            if row:
                result["port_last_ts"]      = row.get("arrival_ts")
                result["port_last_name"]    = row.get("port_name")
                result["port_last_country"] = row.get("port_country")
                result["port_last_level"]   = row.get("sanctions_level")
    return result


# ── PSC detentions ────────────────────────────────────────────────────────

def get_psc_detentions(imo: str, months_back: int = 24) -> list[dict]:
    """
    Return PSC detention records for a vessel within the last N months (IND31).

    Returns a list of dicts with keys:
      imo_number, vessel_name, detention_date, release_date,
      port_name, port_country, authority, deficiency_count
    """
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        if _BACKEND == "postgres":
            c.execute(f"""
                SELECT imo_number, vessel_name, detention_date, release_date,
                       port_name, port_country, authority, deficiency_count
                FROM psc_detentions
                WHERE imo_number = {p}
                  AND detention_date >= (CURRENT_DATE - INTERVAL '{months_back} months')
                ORDER BY detention_date DESC
            """, (imo,))
        else:
            # SQLite: date arithmetic via date()
            c.execute(f"""
                SELECT imo_number, vessel_name, detention_date, release_date,
                       port_name, port_country, authority, deficiency_count
                FROM psc_detentions
                WHERE imo_number = {p}
                  AND detention_date >= date('now', '-{months_back} months')
                ORDER BY detention_date DESC
            """, (imo,))
        rows = c.fetchall()
    return [dict(r) for r in rows] if rows else []


def upsert_psc_detentions(records: list[dict]) -> int:
    """
    Bulk-insert PSC detention records.  Silently skips exact duplicates
    (same IMO + detention_date + authority).
    Returns the number of rows actually inserted.
    """
    if not records:
        return 0

    inserted = 0
    with _conn() as conn:
        c = _cursor(conn)
        for r in records:
            try:
                if _BACKEND == "postgres":
                    c.execute("""
                        INSERT INTO psc_detentions
                            (imo_number, vessel_name, flag_state,
                             detention_date, release_date,
                             port_name, port_country, authority,
                             deficiency_count, list_source)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (imo_number, detention_date, authority) DO NOTHING
                    """, (
                        r.get("imo_number"), r.get("vessel_name"), r.get("flag_state"),
                        r.get("detention_date"), r.get("release_date"),
                        r.get("port_name"), r.get("port_country"), r.get("authority"),
                        r.get("deficiency_count"), r.get("list_source"),
                    ))
                    inserted += c.rowcount
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO psc_detentions
                            (imo_number, vessel_name, flag_state,
                             detention_date, release_date,
                             port_name, port_country, authority,
                             deficiency_count, list_source)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        r.get("imo_number"), r.get("vessel_name"), r.get("flag_state"),
                        r.get("detention_date"), r.get("release_date"),
                        r.get("port_name"), r.get("port_country"), r.get("authority"),
                        r.get("deficiency_count"), r.get("list_source"),
                    ))
                    inserted += conn.total_changes
            except Exception:
                pass
    return inserted


# ── Vessel indicator summary ──────────────────────────────────────────────

def get_vessel_indicator_summary(mmsi: str) -> dict:
    """
    Return dark period count + latest event, STS count + latest event,
    AIS last-seen data, and speed-anomaly count + latest for a given MMSI.

    Returns a dict with keys:
      dp_count, dp_last_ts, dp_last_hours, dp_last_lat, dp_last_lon,
      sts_count, sts_last_ts, sts_last_lat, sts_last_lon,
      ais_last_seen, ais_sog, ais_destination, ais_lat, ais_lon,
      spoof_count, spoof_last_ts, spoof_last_lat, spoof_last_lon, spoof_last_speed_kt
    All optional fields default to None if no data exists.
    """
    p = "?" if _BACKEND == "sqlite" else "%s"

    result: dict = {
        "dp_count": 0, "dp_last_ts": None, "dp_last_hours": None,
        "dp_last_lat": None, "dp_last_lon": None,
        "sts_count": 0, "sts_last_ts": None,
        "sts_last_lat": None, "sts_last_lon": None,
        "ais_last_seen": None, "ais_sog": None,
        "ais_destination": None, "ais_lat": None, "ais_lon": None,
        "spoof_count": 0, "spoof_last_ts": None,
        "spoof_last_lat": None, "spoof_last_lon": None, "spoof_last_speed_kt": None,
    }

    with _conn() as conn:
        c = _cursor(conn)

        # ── Dark periods ──────────────────────────────────────────────────
        c.execute(f"SELECT COUNT(*) AS n FROM dark_periods WHERE mmsi = {p}", (mmsi,))
        row = _row(c)
        result["dp_count"] = (row["n"] if row else 0) or 0

        if result["dp_count"] > 0:
            c.execute(f"""
                SELECT gap_start, gap_hours, last_lat, last_lon
                FROM dark_periods
                WHERE mmsi = {p}
                ORDER BY gap_start DESC
                LIMIT 1
            """, (mmsi,))
            row = _row(c)
            if row:
                result["dp_last_ts"]    = row.get("gap_start")
                result["dp_last_hours"] = row.get("gap_hours")
                result["dp_last_lat"]   = row.get("last_lat")
                result["dp_last_lon"]   = row.get("last_lon")

        # ── STS events ────────────────────────────────────────────────────
        c.execute(f"""
            SELECT COUNT(*) AS n FROM sts_events
            WHERE mmsi1 = {p} OR mmsi2 = {p}
        """, (mmsi, mmsi))
        row = _row(c)
        result["sts_count"] = (row["n"] if row else 0) or 0

        if result["sts_count"] > 0:
            c.execute(f"""
                SELECT event_ts, lat, lon
                FROM sts_events
                WHERE mmsi1 = {p} OR mmsi2 = {p}
                ORDER BY event_ts DESC
                LIMIT 1
            """, (mmsi, mmsi))
            row = _row(c)
            if row:
                result["sts_last_ts"]  = row.get("event_ts")
                result["sts_last_lat"] = row.get("lat")
                result["sts_last_lon"] = row.get("lon")

        # ── AIS vessel last-seen ──────────────────────────────────────────
        c.execute(f"""
            SELECT last_seen, last_sog, destination, last_lat, last_lon
            FROM ais_vessels
            WHERE mmsi = {p}
        """, (mmsi,))
        row = _row(c)
        if row:
            result["ais_last_seen"]    = row.get("last_seen")
            result["ais_sog"]          = row.get("last_sog")
            result["ais_destination"]  = row.get("destination")
            result["ais_lat"]          = row.get("last_lat")
            result["ais_lon"]          = row.get("last_lon")

    # ── Speed anomalies (separate connection) ─────────────────────────────
    result.update(get_speed_anomaly_summary(mmsi))

    # ── STS zone count (IND8) ─────────────────────────────────────────────
    result["sts_risk_zone_count"] = get_sts_zone_count(mmsi)

    # ── Loitering events (IND9) ───────────────────────────────────────────
    result.update(get_loitering_summary(mmsi))

    # ── Sanctioned port calls (IND29) ────────────────────────────────────
    result.update(get_port_call_summary(mmsi))

    return result
