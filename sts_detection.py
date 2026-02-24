"""
Session 3: Ship-to-Ship (STS) proximity detection — Indicator 7.

Algorithm
─────────
1. Pull candidate position pairs from ais_positions via a bounding-box
   SQL self-join (pre-filter to ≤ 0.05° × 0.05° and ≤ 30-min window).
2. Apply exact Haversine filter in Python (≤ STS_DISTANCE_KM).
3. Require at least ONE vessel to be near-stationary (SOG ≤ MAX_SOG).
4. Deduplicate: same pair within DEDUP_HOURS is one event.
5. Cross-check both MMSIs against the sanctions DB.
6. Score risk: CRITICAL / HIGH / MEDIUM / LOW.
7. Persist to sts_events table (upsert on mmsi1+mmsi2+event_ts).

Shadow Fleet indicators addressed
──────────────────────────────────
IND7 — Ship-to-ship transfer at sea (both vessels slow, close proximity)
"""

import math
from datetime import datetime

import db

# ── Detection thresholds ──────────────────────────────────────────────────

STS_DISTANCE_KM = 0.926   # 0.5 nautical miles
STS_TIME_WINDOW_MIN = 30  # max time gap between matched positions
MAX_SOG = 3.0             # knots — at least one vessel must be ≤ this
DEDUP_HOURS = 2.0         # same pair within this window = same event
DEFAULT_HOURS_BACK = 48   # how far back to scan

# ── High-risk zones (reuse same bboxes as dark_periods) ──────────────────

_ZONES = [
    ("Riau Archipelago",        (0.5,  1.5,  103.5, 104.5)),
    ("Gulf of Oman",            (22.0, 26.5,  56.0,  60.5)),
    ("Strait of Malacca",       (1.0,  5.5,  100.0, 104.5)),
    ("Singapore Strait",        (1.1,  1.5,  103.6, 104.2)),
    ("South China Sea",         (5.0, 22.0,  109.0, 120.0)),
    ("East Mediterranean",      (31.0, 37.0,  28.0,  37.0)),
    ("West Africa - Gulf",      (-5.0, 5.0,    2.0,   9.0)),
    ("Red Sea",                 (12.0, 28.0,   32.0,  44.0)),
    ("Persian Gulf",            (23.0, 30.0,   47.0,  57.0)),
]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.asin(math.sqrt(min(a, 1.0)))


def _classify_zone(lat: float, lon: float) -> str | None:
    for name, (lat_min, lat_max, lon_min, lon_max) in _ZONES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def _risk_level(
    distance_km: float,
    sanctions_hit: bool,
    risk_zone: str | None,
    sog1: float | None,
    sog2: float | None,
) -> str:
    both_slow = (sog1 is not None and sog1 <= 1.0) and \
                (sog2 is not None and sog2 <= 1.0)

    if sanctions_hit and both_slow and risk_zone:
        return "CRITICAL"
    if sanctions_hit and (both_slow or risk_zone):
        return "HIGH"
    if sanctions_hit:
        return "HIGH"
    if both_slow and risk_zone:
        return "MEDIUM"
    if risk_zone or both_slow:
        return "LOW"
    return "LOW"


def _ts_to_epoch(ts) -> float:
    """Convert timestamp string or datetime to epoch seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        return ts.timestamp()
    # ISO string — strip Z/+00:00 for fromisoformat
    s = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def _deduplicate(events: list[dict]) -> list[dict]:
    """
    Collapse same-pair events within DEDUP_HOURS into a single representative
    event (the one with the smallest distance).
    """
    threshold = DEDUP_HOURS * 3600  # seconds
    kept: list[dict] = []

    for ev in sorted(events, key=lambda e: e["distance_km"]):
        ev_ts = _ts_to_epoch(ev["event_ts"])
        pair = tuple(sorted([ev["mmsi1"], ev["mmsi2"]]))

        duplicate = False
        for k in kept:
            if tuple(sorted([k["mmsi1"], k["mmsi2"]])) == pair and abs(
                _ts_to_epoch(k["event_ts"]) - ev_ts
            ) <= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(ev)

    return kept


# ── Public API ────────────────────────────────────────────────────────────

def run_detection(
    hours_back: int = DEFAULT_HOURS_BACK,
    max_distance_km: float = STS_DISTANCE_KM,
    max_sog: float = MAX_SOG,
) -> list[dict]:
    """
    Scan recent AIS positions for STS rendezvous candidates.
    Returns list of event dicts; also persists them to sts_events table.
    """
    # Step 1 — bounding-box candidates from DB
    raw = db.find_sts_candidates(
        hours_back=hours_back,
        max_sog=max_sog,
    )

    events: list[dict] = []

    for c in raw:
        lat1, lon1 = c.get("lat1"), c.get("lon1")
        lat2, lon2 = c.get("lat2"), c.get("lon2")

        # Skip if coordinates missing
        if None in (lat1, lon1, lat2, lon2):
            continue

        # Step 2 — exact Haversine check
        dist_km = _haversine(lat1, lon1, lat2, lon2)
        if dist_km > max_distance_km:
            continue

        # Step 3 — at least one vessel slow
        sog1 = c.get("sog1")
        sog2 = c.get("sog2")
        if (
            sog1 is not None
            and sog2 is not None
            and sog1 > max_sog
            and sog2 > max_sog
        ):
            continue

        # Mid-point for zone lookup
        mid_lat = (lat1 + lat2) / 2.0
        mid_lon = (lon1 + lon2) / 2.0
        zone = _classify_zone(mid_lat, mid_lon)

        # Step 4 — sanctions cross-check (cached single-shot query)
        mmsi1, mmsi2 = c["mmsi1"], c["mmsi2"]
        sanc1 = bool(db.search_sanctions_by_mmsi(mmsi1))
        sanc2 = bool(db.search_sanctions_by_mmsi(mmsi2))
        sanctions_hit = sanc1 or sanc2

        risk = _risk_level(dist_km, sanctions_hit, zone, sog1, sog2)

        events.append({
            "mmsi1":        mmsi1,
            "mmsi2":        mmsi2,
            "vessel_name1": c.get("vessel_name1"),
            "vessel_name2": c.get("vessel_name2"),
            "event_ts":     c.get("ts"),
            "lat":          mid_lat,
            "lon":          mid_lon,
            "distance_m":   dist_km * 1000,
            "distance_km":  dist_km,
            "sog1":         sog1,
            "sog2":         sog2,
            "risk_zone":    zone,
            "risk_level":   risk,
            "sanctions_hit": sanctions_hit,
            "indicator_code": "IND7",
        })

    # Step 5 — deduplicate
    events = _deduplicate(events)

    # Step 6 — persist
    db.upsert_sts_events(events)

    return events


def summarise(events: list[dict]) -> dict:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for ev in events:
        lvl = ev.get("risk_level", "LOW")
        counts[lvl] = counts.get(lvl, 0) + 1
    return counts
