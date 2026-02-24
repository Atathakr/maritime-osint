"""
Dark period detector — Indicator 1: AIS transponder gaps.

Queries the ais_positions time-series for each tracked vessel,
identifies gaps greater than the threshold, classifies risk level,
checks for sanctions matches, and persists results to dark_periods.

Thresholds (per the Shadow Fleet Framework):
  ≥ 2 hours  — recorded as a dark period (MEDIUM risk)
  ≥ 6 hours  — elevated risk (HIGH)
  ≥ 24 hours — critical (matches documented shadow fleet behaviour)

High-risk zones accelerate the risk classification: a 3-hour gap in
the Gulf of Oman scores higher than the same gap in the North Sea.
"""

import logging
import math

import db

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────

DARK_THRESHOLD_HOURS    = 2.0    # minimum gap to record
HIGH_RISK_HOURS         = 6.0    # elevated risk
CRITICAL_HOURS          = 24.0   # critical / shadow fleet pattern

# High-risk STS / evasion zones (lat_min, lat_max, lon_min, lon_max, name)
HIGH_RISK_ZONES = [
    (0,    4,    103,   108,   "Riau Archipelago"),
    (21,   26,    55,    63,   "Gulf of Oman"),
    (1,    3,    103,  104.5,  "Strait of Malacca"),
    (32,   37,    28,    37,   "East Mediterranean"),
    (24,   26,    56,    58,   "Offshore Fujairah"),
    (28,   31,    49,    51,   "Kharg Island Area"),
    (0,    6,      2,     8,   "West Africa Offshore"),
    (35,   37,    27,    29,   "Offshore Izmir"),
    (-34, -30,   16,    20,   "Offshore South Africa"),
]


# ── Public interface ──────────────────────────────────────────────────────

def run_detection(mmsi: str | None = None,
                  min_hours: float = DARK_THRESHOLD_HOURS) -> list[dict]:
    """
    Detect AIS dark periods, persist them, and return the results.

    Args:
        mmsi:      Limit detection to a specific vessel. None = all vessels.
        min_hours: Minimum gap length to report (default 2 h).

    Returns:
        List of dark-period dicts, each enriched with:
          - risk_level   ('MEDIUM' | 'HIGH' | 'CRITICAL')
          - risk_zone    (name of high-risk zone, or None)
          - distance_km  (approximate drift distance, or None)
          - sanctions_hit (bool — MMSI or IMO matches a sanctions entry)
    """
    raw_gaps = db.find_ais_gaps(mmsi=mmsi, min_hours=min_hours)
    if not raw_gaps:
        return []

    enriched: list[dict] = []
    for gap in raw_gaps:
        gap = dict(gap)
        gap_h = float(gap.get("gap_hours") or 0)

        # Risk level
        if gap_h >= CRITICAL_HOURS:
            gap["risk_level"] = "CRITICAL"
        elif gap_h >= HIGH_RISK_HOURS:
            gap["risk_level"] = "HIGH"
        else:
            gap["risk_level"] = "MEDIUM"

        # Zone classification
        gap["risk_zone"] = _classify_zone(
            gap.get("last_lat"), gap.get("last_lon")
        )

        # Boost risk level if in a high-risk zone
        if gap["risk_zone"] and gap["risk_level"] == "MEDIUM":
            gap["risk_level"] = "HIGH"

        # Approximate distance between disappear and reappear points
        gap["distance_km"] = _haversine(
            gap.get("last_lat"),    gap.get("last_lon"),
            gap.get("reappear_lat"), gap.get("reappear_lon"),
        )

        # Sanctions cross-reference
        mmsi_val = gap.get("mmsi")
        imo_val  = gap.get("imo_number")
        sanctions_hits = []
        if mmsi_val:
            sanctions_hits += db.search_sanctions_by_mmsi(mmsi_val)
        if imo_val and not sanctions_hits:
            sanctions_hits += db.search_sanctions_by_imo(imo_val)
        gap["sanctions_hit"] = bool(sanctions_hits)

        gap["indicator_code"] = "IND1"
        enriched.append(gap)

    # Persist
    inserted = db.upsert_dark_periods(enriched)
    logger.info("Dark period detection: %d gaps found, %d persisted", len(enriched), inserted)
    return enriched


def summarise(periods: list[dict]) -> dict:
    """Return a counts summary dict for API responses."""
    if not periods:
        return {"total": 0, "medium": 0, "high": 0, "critical": 0,
                "with_sanctions": 0, "in_risk_zone": 0}
    return {
        "total":          len(periods),
        "medium":         sum(1 for p in periods if p.get("risk_level") == "MEDIUM"),
        "high":           sum(1 for p in periods if p.get("risk_level") == "HIGH"),
        "critical":       sum(1 for p in periods if p.get("risk_level") == "CRITICAL"),
        "with_sanctions": sum(1 for p in periods if p.get("sanctions_hit")),
        "in_risk_zone":   sum(1 for p in periods if p.get("risk_zone")),
    }


# ── Helpers ───────────────────────────────────────────────────────────────

def _classify_zone(lat, lon) -> str | None:
    if lat is None or lon is None:
        return None
    for lat_min, lat_max, lon_min, lon_max, name in HIGH_RISK_ZONES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


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
