"""
Spoofing detector — Core logic for identifying AIS manipulation.

Primary indicators:
  • TELEPORT — Physically impossible speed between consecutive reports (>30 kts).
  • OVERLAND — AIS positions reported over land (requires spatial analysis).
  • ID_MISMATCH — MMSI/IMO/Name inconsistencies.
"""

import logging
import math
import datetime
import db
import schemas

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────

SPEED_THRESHOLD_KNOTS = 30.0


# ── Public interface ──────────────────────────────────────────────────────

def run_detection(mmsi: str | None = None,
                  hours_back: int = 48) -> list[dict]:
    """
    Detect AIS spoofing events, specifically teleportation.

    Args:
        mmsi:       Limit detection to a specific vessel. None = all vessels.
        hours_back: How far back to look for position pairs.

    Returns:
        List of SpoofEvent dicts.
    """
    candidates = db.find_teleport_candidates(hours_back=hours_back, mmsi=mmsi)
    if not candidates:
        return []

    spoof_events: list[dict] = []
    for pair in candidates:
        lat1, lon1 = pair.get("lat"), pair.get("lon")
        lat2, lon2 = pair.get("next_lat"), pair.get("next_lon")
        ts1_str, ts2_str = pair.get("position_ts"), pair.get("next_ts")

        # Distance calculation
        dist_km = _haversine(lat1, lon1, lat2, lon2)
        if dist_km is None:
            continue

        # Time delta calculation
        try:
            if isinstance(ts1_str, str):
                ts1 = datetime.datetime.fromisoformat(ts1_str.replace('Z', '+00:00'))
                ts2 = datetime.datetime.fromisoformat(ts2_str.replace('Z', '+00:00'))
            else:
                ts1 = ts1_str
                ts2 = ts2_str

            delta = ts2 - ts1
            hours = delta.total_seconds() / 3600.0
        except Exception as e:
            logger.error("Error parsing timestamps for MMSI %s: %s", pair.get("mmsi"), e)
            continue

        if hours <= 0:
            continue

        # Implied Speed Over Ground (SOG) in knots
        # (1 nautical mile = 1.852 km)
        implied_sog = (dist_km / hours) / 1.852

        if implied_sog > SPEED_THRESHOLD_KNOTS:
            # Sanctions cross-reference
            mmsi_val = pair.get("mmsi")
            imo_val  = pair.get("imo_number")
            sanctions_hits = []
            if mmsi_val:
                sanctions_hits += db.search_sanctions_by_mmsi(mmsi_val)
            if imo_val and not sanctions_hits:
                sanctions_hits += db.search_sanctions_by_imo(imo_val)
            sanctions_hit = bool(sanctions_hits)

            try:
                event = schemas.SpoofEvent(
                    mmsi=mmsi_val,
                    imo_number=imo_val,
                    vessel_name=pair.get("vessel_name"),
                    spoof_type="TELEPORT",
                    detected_at=ts2_str,
                    lat=lat2,
                    lon=lon2,
                    risk_level="HIGH",
                    sanctions_hit=sanctions_hit,
                    detail={
                        "distance_km": dist_km,
                        "hours": round(hours, 2),
                        "implied_sog_knots": round(implied_sog, 1),
                        "prev_lat": lat1,
                        "prev_lon": lon1,
                        "prev_ts": ts1_str
                    },
                    indicator_code="IND_SPOOF"
                )
                spoof_events.append(event.model_dump())
            except Exception as e:
                logger.debug("Validation failed for spoof event MMSI %s: %s", mmsi_val, e)

    # Persist findings
    if spoof_events:
        db.upsert_spoof_events(spoof_events)

    logger.info("Spoof detection: %d TELEPORT events found for %d candidates",
                len(spoof_events), len(candidates))
    return spoof_events


def summarise(events: list[dict]) -> dict:
    """Return a count of events by type."""
    if not events:
        return {"total": 0, "types": {}}

    summary = {
        "total": len(events),
        "types": {}
    }
    for ev in events:
        etype = ev.get("spoof_type", "UNKNOWN")
        summary["types"][etype] = summary["types"].get(etype, 0) + 1
    return summary


# ── Helpers ───────────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2) -> float | None:
    """Great-circle distance in km between two points."""
    if any(v is None for v in (lat1, lon1, lat2, lon2)):
        return None
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return round(r * 2 * math.asin(math.sqrt(a)), 1)
