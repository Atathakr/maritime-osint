"""
map_data.py — Risk aggregation for the live maritime risk map.

For each AIS vessel we compute a single composite risk_level by taking
the maximum of:
  - sanctions membership         → always CRITICAL when sanctioned
  - worst dark-period in window  → dp_risk_num (0-4)
  - worst STS event in window    → sts_risk_num (0-4)

The result is a list of vessel dicts ready for JSON serialisation and
direct consumption by the Leaflet front-end.
"""

from __future__ import annotations

import json

import db

# ── Risk tables ────────────────────────────────────────────────────────────

_NUM_TO_LABEL: dict[int, str] = {
    0: "NONE",
    1: "LOW",
    2: "MEDIUM",
    3: "HIGH",
    4: "CRITICAL",
}

# Hex colours that mirror style.css design tokens
RISK_COLOURS: dict[str, str] = {
    "CRITICAL":   "#e84040",   # sanctioned / critical dark period / critical STS
    "HIGH":       "#f97316",   # --accent (orange)
    "MEDIUM":     "#eab308",   # --warn  (yellow)
    "LOW":        "#94a3b8",   # light slate
    "NONE":       "#475569",   # muted slate (clean vessel)
    "SANCTIONED": "#e84040",   # alias kept for backwards compat
}

# Circle radii (pixels) per risk level
RISK_RADIUS: dict[str, int] = {
    "CRITICAL": 9,
    "HIGH":     7,
    "MEDIUM":   6,
    "LOW":      5,
    "NONE":     4,
}


# ── Core function ──────────────────────────────────────────────────────────

def get_map_vessels(
    hours: int = 48,
    dp_days: int = 7,
    sts_days: int = 7,
    risk_filter: str = "all",
) -> list[dict]:
    """
    Return vessel dicts for the live risk map, sorted highest risk first.

    Parameters
    ----------
    hours       : only include vessels seen in the last N hours
    dp_days     : dark-period look-back window in days
    sts_days    : STS-event look-back window in days
    risk_filter : "all" | "medium_plus" | "high_plus" | "sanctioned"

    Each returned dict has:
        mmsi, imo_number, vessel_name, vessel_type, flag_state,
        lat, lon, cog, sog, nav_status, last_seen,
        destination, call_sign, length, draft,
        sanctioned (bool),
        source_tags (list[str]),
        dp_risk,     sts_risk           — label strings
        risk_level  — composite label: CRITICAL/HIGH/MEDIUM/LOW/NONE
        risk_num    — numeric 0-4 (for client-side sorting / filtering)
        risk_colour — hex colour string
        risk_radius — circle radius int
        risk_reasons — list[str] describing contributing factors
    """
    raw = db.get_map_vessels_raw(hours=hours, dp_days=dp_days, sts_days=sts_days)

    results: list[dict] = []
    for r in raw:
        sanctioned   = bool(r.get("sanctioned", 0))
        dp_risk_num  = int(r.get("dp_risk_num",  0))
        sts_risk_num = int(r.get("sts_risk_num", 0))

        # Sanctioned vessels are always CRITICAL (num=4)
        sanc_num = 4 if sanctioned else 0

        composite_num = max(sanc_num, dp_risk_num, sts_risk_num)
        risk_level    = _NUM_TO_LABEL[composite_num]

        # Human-readable reason list
        reasons: list[str] = []
        if sanctioned:
            reasons.append("Sanctioned vessel")
        if dp_risk_num > 0:
            reasons.append(f"Dark period: {_NUM_TO_LABEL[dp_risk_num]}")
        if sts_risk_num > 0:
            reasons.append(f"STS event: {_NUM_TO_LABEL[sts_risk_num]}")

        # Deserialise source_tags (stored as JSON string in DB)
        raw_tags = r.get("source_tags")
        if isinstance(raw_tags, str):
            try:
                source_tags = json.loads(raw_tags)
            except json.JSONDecodeError:
                source_tags = []
        elif isinstance(raw_tags, list):
            source_tags = raw_tags
        else:
            source_tags = []

        # Apply risk_filter
        if risk_filter == "sanctioned" and not sanctioned:
            continue
        if risk_filter == "high_plus" and composite_num < 3:
            continue
        if risk_filter == "medium_plus" and composite_num < 2:
            continue

        results.append({
            "mmsi":         r.get("mmsi"),
            "imo_number":   r.get("imo_number"),
            "vessel_name":  r.get("vessel_name") or "Unknown",
            "vessel_type":  r.get("vessel_type"),
            "flag_state":   r.get("flag_state"),
            "lat":          r.get("last_lat"),
            "lon":          r.get("last_lon"),
            "cog":          r.get("last_cog"),
            "sog":          r.get("last_sog"),
            "nav_status":   r.get("last_nav_status"),
            "last_seen":    r.get("last_seen"),
            "destination":  r.get("destination"),
            "call_sign":    r.get("call_sign"),
            "length":       r.get("length"),
            "draft":        r.get("draft"),
            "sanctioned":   sanctioned,
            "source_tags":  source_tags,
            "dp_risk":      _NUM_TO_LABEL[dp_risk_num],
            "sts_risk":     _NUM_TO_LABEL[sts_risk_num],
            "risk_level":   risk_level,
            "risk_num":     composite_num,
            "risk_colour":  RISK_COLOURS[risk_level],
            "risk_radius":  RISK_RADIUS[risk_level],
            "risk_reasons": reasons,
        })

    # Sort: highest risk first, then by last_seen descending
    results.sort(key=lambda v: (-v["risk_num"], v.get("last_seen") or ""), reverse=False)
    return results
