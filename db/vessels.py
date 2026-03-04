# db/vessels.py
"""Vessel registry CRUD, ingest log, and aggregate stats."""

import json

import normalize  # project root — not db/normalize.py

from .connection import _BACKEND, _conn, _cursor, _rows, _row, _ph, _ilike, _jp  # noqa: F401


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

            # ── Promote build_year / call_sign / gross_tonnage to canonical ──
            for col, val in [
                ("build_year",    ent.get("build_year")),
                ("call_sign",     ent.get("call_sign")),
                ("gross_tonnage", ent.get("gross_tonnage")),
            ]:
                if val is not None:
                    c.execute(
                        f"UPDATE vessels_canonical SET {col} = {p} "
                        f"WHERE canonical_id = {p} AND {col} IS NULL",
                        (val, canonical_id),
                    )

            # ── Populate vessel_flag_history from past_flags ──────────────
            past_flags = ent.get("past_flags") or []
            if imo and past_flags:
                for flag_code in past_flags:
                    if not flag_code:
                        continue
                    if _BACKEND == "postgres":
                        c.execute("""
                            INSERT INTO vessel_flag_history (imo_number, flag_state, source)
                            SELECT %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM vessel_flag_history
                                WHERE imo_number = %s AND flag_state = %s AND source = %s
                            )
                        """, (imo, flag_code, list_name, imo, flag_code, list_name))
                    else:
                        c.execute("""
                            INSERT INTO vessel_flag_history (imo_number, flag_state, source)
                            SELECT ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM vessel_flag_history
                                WHERE imo_number = ? AND flag_state = ? AND source = ?
                            )
                        """, (imo, flag_code, list_name, imo, flag_code, list_name))

            # ── Populate vessel_ownership ─────────────────────────────────
            for own in (ent.get("ownership_entries") or []):
                role_val    = own.get("role", "owner")
                entity_name = (own.get("entity_name") or "").strip()
                source_val  = own.get("source", list_name)
                if not entity_name:
                    continue
                if _BACKEND == "postgres":
                    c.execute("""
                        INSERT INTO vessel_ownership (canonical_id, role, entity_name, source)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (canonical_id, role, entity_name, source) DO NOTHING
                    """, (canonical_id, role_val, entity_name, source_val))
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO vessel_ownership
                            (canonical_id, role, entity_name, source)
                        VALUES (?, ?, ?, ?)
                    """, (canonical_id, role_val, entity_name, source_val))

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
                   flag_normalized, aliases, source_tags, match_method, created_at,
                   build_year, call_sign, gross_tonnage
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


def get_ais_vessel_by_imo(imo: str) -> dict | None:
    """Look up an AIS vessel record by IMO number (fallback for vessels not in sanctions DB)."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(
            f"SELECT mmsi, imo_number, vessel_name, vessel_type, call_sign, "
            f"flag_state, last_lat, last_lon, last_sog, last_seen, destination "
            f"FROM ais_vessels WHERE imo_number = {p} LIMIT 1",
            (imo,),
        )
        return _row(c)


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


def get_vessel_ownership(canonical_id: str) -> list[dict]:
    """Return all ownership / management entries for one canonical vessel."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT role, entity_name, source
            FROM vessel_ownership
            WHERE canonical_id = {p}
            ORDER BY role, entity_name
        """, (canonical_id,))
        return _rows(c)


def get_vessel_flag_history(imo_number: str) -> list[dict]:
    """Return historical flag states for a vessel, newest first."""
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute(f"""
            SELECT flag_state, effective_date, source
            FROM vessel_flag_history
            WHERE imo_number = {p}
            ORDER BY created_at DESC
        """, (imo_number,))
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
        except Exception:
            total_ais_positions = total_ais_vessels = total_dark_periods = total_sts_events = 0

    return {
        "total_sanctions":     total_sanctions,
        "total_vessels":       total_sanctions,   # backward compat alias
        "by_list":             by_list,
        "recent_ingests":      recent_ingests,
        "total_ais_positions": total_ais_positions,
        "total_ais_vessels":   total_ais_vessels,
        "total_dark_periods":  total_dark_periods,
        "total_sts_events":    total_sts_events,
    }


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
