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
import schemas

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
                  min_hours: float = DARK_THRESHOLD_HOURS) -> list[schemas.DarkPeriod]:
    """
    Detect AIS dark periods, persist them, and return the results.

    Args:
        mmsi:      Limit detection to a specific vessel. None = all vessels.
        min_hours: Minimum gap length to report (default 2 h).

    Returns:
        List of DarkPeriod instances.
    """
    raw_gaps = db.find_ais_gaps(mmsi=mmsi, min_hours=min_hours)
    if not raw_gaps:
        return []

    enriched: list[schemas.DarkPeriod] = []
    for row in raw_gaps:
        gap = dict(row)
        gap_h = float(gap.get("gap_hours") or 0)

        # Risk level
        risk_level = "MEDIUM"
        if gap_h >= CRITICAL_HOURS:
            risk_level = "CRITICAL"
        elif gap_h >= HIGH_RISK_HOURS:
            risk_level = "HIGH"

        # Zone classification
        last_lat = gap.get("last_lat")
        last_lon = gap.get("last_lon")
        risk_zone = _classify_zone(
            float(last_lat) if last_lat is not None else None,
            float(last_lon) if last_lon is not None else None,
        )

        # Boost risk level if in a high-risk zone
        if risk_zone and risk_level == "MEDIUM":
            risk_level = "HIGH"

        # Approximate distance between disappear and reappear points
        reappear_lat = gap.get("reappear_lat")
        reappear_lon = gap.get("reappear_lon")
        distance_km = _haversine(
            float(last_lat) if last_lat is not None else None,
            float(last_lon) if last_lon is not None else None,
            float(reappear_lat) if reappear_lat is not None else None,
            float(reappear_lon) if reappear_lon is not None else None,
        )

        # Sanctions cross-reference
        mmsi_val = gap.get("mmsi")
        imo_val  = gap.get("imo_number")
        sanctions_hits = []
        if mmsi_val:
            sanctions_hits += db.search_sanctions_by_mmsi(mmsi_val)
        if imo_val and not sanctions_hits:
            sanctions_hits += db.search_sanctions_by_imo(imo_val)
        sanctions_hit = bool(sanctions_hits)

        try:
            dp = schemas.DarkPeriod(
                mmsi=str(mmsi_val),
                imo_number=str(imo_val) if imo_val else None,
                vessel_name=gap.get("vessel_name"),
                gap_start=gap["gap_start"],
                gap_end=gap["gap_end"],
                gap_hours=gap_h,
                last_lat=float(last_lat) if last_lat is not None else None,
                last_lon=float(last_lon) if last_lon is not None else None,
                reappear_lat=float(reappear_lat) if reappear_lat is not None else None,
                reappear_lon=float(reappear_lon) if reappear_lon is not None else None,
                distance_km=distance_km,
                risk_zone=risk_zone,
                risk_level=risk_level,
                sanctions_hit=sanctions_hit,
                indicator_code="IND1",
            )
            enriched.append(dp)
        except Exception as e:
            logger.debug("Validation failed for dark period MMSI %s: %s", mmsi_val, e)

    # Persist (needs dicts for the DB layer)
    inserted = db.upsert_dark_periods([p.model_dump() for p in enriched])
    logger.info("Dark period detection: %d gaps found, %d persisted", len(enriched), inserted)
    return enriched


def summarise(periods: list[schemas.DarkPeriod]) -> dict:
    """Return a counts summary dict for API responses."""
    if not periods:
        return {"total": 0, "medium": 0, "high": 0, "critical": 0,
                "with_sanctions": 0, "in_risk_zone": 0}
    return {
        "total":          len(periods),
        "medium":         sum(1 for p in periods if p.risk_level == "MEDIUM"),
        "high":           sum(1 for p in periods if p.risk_level == "HIGH"),
        "critical":       sum(1 for p in periods if p.risk_level == "CRITICAL"),
        "with_sanctions": sum(1 for p in periods if p.sanctions_hit),
        "in_risk_zone":   sum(1 for p in periods if p.risk_zone),
    }


# ── Helpers ───────────────────────────────────────────────────────────────

def _classify_zone(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    for lat_min, lat_max, lon_min, lon_max, name in HIGH_RISK_ZONES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def _haversine(lat1: float | None, lon1: float | None,
               lat2: float | None, lon2: float | None) -> float | None:
    """Great-circle distance in km between two points."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return round(r * 2 * math.asin(math.sqrt(a)), 1)
