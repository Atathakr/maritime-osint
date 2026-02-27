"""
AIS spoofing proxy — Indicator 10: Speed anomaly detection (IND10).

Identifies consecutive AIS position pairs implying physically impossible
vessel speeds (>50 knots default).  These are strong indicators of GPS
spoofing, data injection, or identity switching between broadcasts.

Merchant vessel maximum practical speed ≈ 25 knots.
The 50-knot threshold is deliberately conservative to minimise false
positives from terrestrial AIS timing skew and late packet delivery.
"""

import logging
import math

import db
import risk_config

logger = logging.getLogger(__name__)

_KM_PER_NM = 1.852   # 1 nautical mile = 1.852 km


# ── Haversine ─────────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2) -> float | None:
    """Great-circle distance in km, or None if any coordinate is missing."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(float(lat1)))
         * math.cos(math.radians(float(lat2)))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


# ── Public interface ───────────────────────────────────────────────────────

def detect_speed_anomalies(
    mmsi: str | None = None,
    threshold_kt: float = risk_config.SPEED_ANOMALY_THRESHOLD_KT,
    hours_back: int = 168,
    limit: int = 5000,
) -> list[dict]:
    """
    Find consecutive AIS position pairs implying impossible vessel speed.

    Args:
        mmsi:         Limit detection to a specific vessel (None = all).
        threshold_kt: Implied speed threshold in knots (default 50).
        hours_back:   Look back this many hours in ais_positions (default 168 = 7 days).
        limit:        Maximum position pairs to evaluate.

    Returns:
        List of anomaly dicts matching the ais_anomalies table schema.
    """
    pairs = db.get_consecutive_ais_pairs(
        mmsi=mmsi, hours_back=hours_back, limit=limit
    )
    anomalies: list[dict] = []

    for row in pairs:
        lat1 = row.get("lat")
        lon1 = row.get("lon")
        lat2 = row.get("next_lat")
        lon2 = row.get("next_lon")
        ts2  = row.get("next_ts")

        if None in (lat1, lon1, lat2, lon2, ts2):
            continue

        km = _haversine(lat1, lon1, lat2, lon2)
        if km is None or km < 0.01:
            continue

        try:
            td_min = float(row.get("time_delta_min") or 0)
        except (TypeError, ValueError):
            continue
        if td_min <= 0:
            continue

        implied_speed_kt = (km / _KM_PER_NM) / (td_min / 60.0)
        if implied_speed_kt > threshold_kt:
            anomalies.append({
                "mmsi":             row.get("mmsi"),
                "imo_number":       row.get("imo_number"),
                "vessel_name":      row.get("vessel_name"),
                "anomaly_type":     "speed_jump",
                "event_ts":         str(ts2),
                "lat":              lat2,
                "lon":              lon2,
                "prev_lat":         lat1,
                "prev_lon":         lon1,
                "implied_speed_kt": round(implied_speed_kt, 1),
                "distance_km":      round(km, 3),
                "time_delta_min":   round(td_min, 2),
                "risk_level":       "HIGH",
                "indicator_code":   "IND10",
            })

    return anomalies


def run_speed_anomaly_detection(
    threshold_kt: float = risk_config.SPEED_ANOMALY_THRESHOLD_KT,
    hours_back: int = 168,
) -> dict:
    """
    Run speed-anomaly detection across all tracked vessels, persist results,
    and return a summary dict.
    """
    anomalies = detect_speed_anomalies(
        mmsi=None, threshold_kt=threshold_kt, hours_back=hours_back
    )
    inserted = db.upsert_speed_anomalies(anomalies)
    vessels_affected = len({a["mmsi"] for a in anomalies if a.get("mmsi")})

    logger.info(
        "Speed anomaly detection: %d anomalies found, %d new, %d vessels affected",
        len(anomalies), inserted, vessels_affected,
    )
    return {
        "anomalies_found":    len(anomalies),
        "anomalies_inserted": inserted,
        "vessels_affected":   vessels_affected,
        "threshold_kt":       threshold_kt,
        "hours_back":         hours_back,
    }
