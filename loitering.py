"""
Loitering detection — Indicator 9: Vessel stationary in open water (IND9).

Identifies vessels maintaining low speed (< 2 kt) for an extended period
(≥ 12 hours) outside designated anchorage zones.  This is a strong precursor
to ship-to-ship (STS) cargo transfers and a recognised shadow-fleet evasion
tactic.

Risk levels:
  MEDIUM  — loitering ≥ 12 h
  HIGH    — loitering ≥ 24 h  OR  ≥ 12 h in a high-risk zone
  CRITICAL — loitering ≥ 48 h
"""

import logging
from datetime import datetime, timezone

import db
from dark_periods import HIGH_RISK_ZONES   # reuse existing zone constants

logger = logging.getLogger(__name__)

SOG_THRESHOLD_KT: float = 2.0    # kt — below this = "loitering"
MIN_LOITER_HOURS: float = 12.0   # minimum episode duration to record


# ── Zone classification ────────────────────────────────────────────────────

def _classify_zone(lat, lon) -> str | None:
    """Return the name of the first matching high-risk zone, or None."""
    if lat is None or lon is None:
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    for lat_min, lat_max, lon_min, lon_max, name in HIGH_RISK_ZONES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def _risk_level(hours: float, zone: str | None) -> str:
    if hours >= 48:
        return "CRITICAL"
    if hours >= 24 or (hours >= 12 and zone):
        return "HIGH"
    return "MEDIUM"


# ── Episode grouping ───────────────────────────────────────────────────────

def _parse_ts(val) -> datetime | None:
    """Parse timestamp from DB (string or datetime) to UTC-aware datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    try:
        # ISO-8601 string from SQLite
        s = str(val).rstrip("Z").replace(" ", "T")
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _group_episodes(
    rows: list[dict],
    sog_threshold: float,
    min_hours: float,
) -> list[dict]:
    """
    Group consecutive low-speed AIS positions into loitering episodes.

    A new episode starts when:
      - the gap between consecutive positions is > 6 h (vessel resumed normal operations)
      - or SOG rises above the threshold and stays above it

    Args:
        rows: AIS position rows sorted ascending by position_ts.
              Each row must have: mmsi, imo_number, vessel_name, lat, lon, sog, position_ts.
        sog_threshold: Speed threshold in knots.
        min_hours: Minimum episode duration in hours to keep.

    Returns:
        List of episode dicts ready for db.upsert_loitering_events().
    """
    episodes: list[dict] = []
    if not rows:
        return episodes

    # Seed first row
    ep_start_ts: datetime | None = None
    ep_lats: list[float] = []
    ep_lons: list[float] = []
    ep_end_ts: datetime | None = None
    in_episode = False
    ep_mmsi = ep_imo = ep_name = None

    for row in rows:
        sog = row.get("sog")
        ts  = _parse_ts(row.get("position_ts"))
        lat = row.get("lat")
        lon = row.get("lon")

        if sog is None or ts is None or lat is None or lon is None:
            continue

        low_speed = float(sog) <= sog_threshold

        if low_speed:
            if not in_episode:
                # Start new episode
                in_episode = True
                ep_start_ts = ts
                ep_lats = [float(lat)]
                ep_lons = [float(lon)]
                ep_end_ts = ts
                ep_mmsi  = row.get("mmsi")
                ep_imo   = row.get("imo_number")
                ep_name  = row.get("vessel_name")
            else:
                # Continue episode — check for gap > 6 h (indicates resumed transit)
                gap_h = (ts - ep_end_ts).total_seconds() / 3600.0
                if gap_h > 6:
                    # Close current episode before starting new one
                    _maybe_save(
                        episodes, ep_mmsi, ep_imo, ep_name,
                        ep_start_ts, ep_end_ts, ep_lats, ep_lons, min_hours,
                    )
                    ep_start_ts = ts
                    ep_lats = [float(lat)]
                    ep_lons = [float(lon)]
                    ep_mmsi = row.get("mmsi")
                    ep_imo  = row.get("imo_number")
                    ep_name = row.get("vessel_name")
                else:
                    ep_lats.append(float(lat))
                    ep_lons.append(float(lon))
                ep_end_ts = ts
        else:
            if in_episode:
                _maybe_save(
                    episodes, ep_mmsi, ep_imo, ep_name,
                    ep_start_ts, ep_end_ts, ep_lats, ep_lons, min_hours,
                )
                in_episode = False
                ep_lats = []
                ep_lons = []

    # Close any open episode at the end of the data window
    if in_episode and ep_start_ts and ep_end_ts:
        _maybe_save(
            episodes, ep_mmsi, ep_imo, ep_name,
            ep_start_ts, ep_end_ts, ep_lats, ep_lons, min_hours,
        )

    return episodes


def _maybe_save(
    episodes: list[dict],
    mmsi, imo, name,
    start: datetime, end: datetime,
    lats: list[float], lons: list[float],
    min_hours: float,
) -> None:
    """Compute episode metadata and append if it meets the minimum duration."""
    if not lats or start is None or end is None:
        return
    hours = (end - start).total_seconds() / 3600.0
    if hours < min_hours:
        return

    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    zone       = _classify_zone(center_lat, center_lon)
    level      = _risk_level(hours, zone)

    episodes.append({
        "mmsi":          mmsi,
        "imo_number":    imo,
        "vessel_name":   name,
        "loiter_start":  start.isoformat(),
        "loiter_end":    end.isoformat(),
        "loiter_hours":  round(hours, 2),
        "center_lat":    round(center_lat, 5),
        "center_lon":    round(center_lon, 5),
        "risk_zone":     zone,
        "risk_level":    level,
        "sanctions_hit": False,
        "indicator_code": "IND9",
    })


# ── Pure public interface ──────────────────────────────────────────────────

def detect(positions: list, sog_threshold_kt: float = SOG_THRESHOLD_KT,
           min_hours: float = MIN_LOITER_HOURS) -> list:
    """
    Pure classification of AIS position sequences into loitering episodes — no database calls.

    Accepts position dicts in the shape returned by db (or ais_factory.make_position_sequence()).
    Positions should be sorted ascending by position_ts per vessel.

    This is a thin public wrapper over the private _group_episodes() function which already
    contains all the pure classification logic. Do NOT call _get_low_speed_positions() here —
    that function calls db._BACKEND, db._conn(), and db._cursor() directly.
    """
    return _group_episodes(positions, sog_threshold=sog_threshold_kt, min_hours=min_hours)


# ── DB query ───────────────────────────────────────────────────────────────

def _get_low_speed_positions(
    mmsi: str | None,
    sog_threshold: float,
    hours_back: int,
    limit: int,
) -> list[dict]:
    """
    Fetch recent AIS positions filtered by SOG ≤ threshold.
    Returns rows sorted ascending by (mmsi, position_ts).
    """
    p = "?" if db._BACKEND == "sqlite" else "%s"
    cutoff_expr = (
        f"NOW() - INTERVAL '{hours_back} hours'"
        if db._BACKEND == "postgres"
        else f"datetime('now', '-{hours_back} hours')"
    )
    mmsi_filter = f"AND mmsi = {p}" if mmsi else ""
    params: list = ([mmsi] if mmsi else []) + [sog_threshold, limit]

    with db._conn() as conn:
        c = db._cursor(conn)
        c.execute(f"""
            SELECT mmsi, imo_number, vessel_name, lat, lon, sog, position_ts
            FROM ais_positions
            WHERE position_ts >= {cutoff_expr}
              {mmsi_filter}
              AND sog IS NOT NULL
              AND sog <= {p}
            ORDER BY mmsi ASC, position_ts ASC
            LIMIT {p}
        """, params)
        return db._rows(c)


# ── Public interface ───────────────────────────────────────────────────────

def detect_loitering_episodes(
    mmsi: str | None = None,
    sog_threshold_kt: float = SOG_THRESHOLD_KT,
    min_hours: float = MIN_LOITER_HOURS,
    hours_back: int = 168,
    limit: int = 50_000,
) -> list[dict]:
    """
    Find loitering episodes in recent AIS positions.

    Args:
        mmsi:             Limit detection to a specific vessel (None = all).
        sog_threshold_kt: Speed-over-ground threshold (default 2.0 kt).
        min_hours:        Minimum loitering duration in hours (default 12).
        hours_back:       Look-back window in hours (default 168 = 7 days).
        limit:            Maximum AIS rows to process.

    Returns:
        List of episode dicts matching the loitering_events table schema.
    """
    rows = _get_low_speed_positions(mmsi, sog_threshold_kt, hours_back, limit)

    # Group by MMSI before episode detection
    by_mmsi: dict[str, list[dict]] = {}
    for r in rows:
        key = r.get("mmsi") or ""
        by_mmsi.setdefault(key, []).append(r)

    all_episodes: list[dict] = []
    for vessel_rows in by_mmsi.values():
        all_episodes.extend(
            _group_episodes(vessel_rows, sog_threshold_kt, min_hours)
        )
    return all_episodes


def run_loitering_detection(
    sog_threshold_kt: float = SOG_THRESHOLD_KT,
    min_hours: float = MIN_LOITER_HOURS,
    hours_back: int = 168,
) -> dict:
    """
    Run loitering detection across all tracked vessels, persist results,
    and return a summary dict.
    """
    episodes = detect_loitering_episodes(
        mmsi=None,
        sog_threshold_kt=sog_threshold_kt,
        min_hours=min_hours,
        hours_back=hours_back,
    )
    inserted = db.upsert_loitering_events(episodes)
    vessels_affected = len({e["mmsi"] for e in episodes if e.get("mmsi")})

    logger.info(
        "Loitering detection: %d episodes found, %d new, %d vessels affected",
        len(episodes), inserted, vessels_affected,
    )
    return {
        "episodes_found":    len(episodes),
        "episodes_inserted": inserted,
        "vessels_affected":  vessels_affected,
        "sog_threshold_kt":  sog_threshold_kt,
        "min_hours":         min_hours,
        "hours_back":        hours_back,
    }
