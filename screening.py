"""
Vessel screening module — query sanctions lists by IMO, MMSI, or name.

Screening is the core Session 1 deliverable: given any vessel identifier,
return all matching sanctions entries with confidence metadata.
"""

import re

import db


def _clean_imo(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 7 else None


def _clean_mmsi(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 9 else None


def _detect_query_type(query: str) -> str:
    """
    Classify the query string as 'imo', 'mmsi', or 'name'.

    IMO numbers are 7 consecutive digits.
    MMSI numbers are exactly 9 consecutive digits.
    Everything else is treated as a vessel name.
    """
    digits = re.sub(r"\D", "", query)
    if len(digits) == 7 and re.fullmatch(r"\d{7}", digits):
        return "imo"
    if len(digits) == 9 and re.fullmatch(r"\d{9}", digits):
        return "mmsi"
    return "name"


def screen(query: str) -> dict:
    """
    Screen a vessel against all loaded sanctions lists.

    Input: any of —
      - IMO number (7 digits, e.g. "9876543" or "IMO 9876543")
      - MMSI (9 digits)
      - Vessel name (partial match)

    Returns a dict with:
      - query, query_type
      - sanctioned (bool)
      - total_hits (int)
      - hits (list of sanitized sanctions entry dicts)
    """
    query = query.strip()
    if not query:
        return {"error": "Empty query", "hits": []}

    query_type = _detect_query_type(query)
    hits: list[dict] = []

    if query_type == "imo":
        imo = _clean_imo(query)
        hits = db.search_sanctions_by_imo(imo)
    elif query_type == "mmsi":
        mmsi = _clean_mmsi(query)
        hits = db.search_sanctions_by_mmsi(mmsi)
    else:
        hits = db.search_sanctions_by_name(query)

    # If an IMO/MMSI query returned nothing, try a name fallback so that
    # e.g. "9876543" typed as a vessel name still finds partial matches.
    if not hits and query_type in ("imo", "mmsi"):
        fallback = db.search_sanctions_by_name(query)
        if fallback:
            hits = fallback
            query_type = f"{query_type}_name_fallback"

    # Annotate each hit with a plain-language confidence label
    for hit in hits:
        if hit.get("imo_number") and query_type == "imo":
            hit["match_confidence"] = "HIGH — exact IMO match"
        elif hit.get("mmsi") and query_type == "mmsi":
            hit["match_confidence"] = "HIGH — exact MMSI match"
        else:
            hit["match_confidence"] = "MEDIUM — name match (verify IMO)"

        # Deserialise JSONB aliases for display
        aliases = hit.get("aliases")
        if isinstance(aliases, str):
            try:
                hit["aliases"] = __import__("json").loads(aliases)
            except Exception:
                hit["aliases"] = []

    return {
        "query":        query,
        "query_type":   query_type,
        "sanctioned":   len(hits) > 0,
        "total_hits":   len(hits),
        "hits":         hits,
    }


def screen_vessel_detail(imo: str) -> dict:
    """
    Full screening report for a known vessel (by IMO).
    Fetches vessel registry record plus all sanctions list appearances.
    """
    imo = re.sub(r"\D", "", imo)
    vessel = db.get_vessel(imo)
    sanctions_hits = db.search_sanctions_by_imo(imo)

    # Basic risk indicators we can score from available data (Session 1)
    risk_factors: list[str] = []
    if sanctions_hits:
        lists = {h["list_name"] for h in sanctions_hits}
        risk_factors.append(f"Listed on: {', '.join(sorted(lists))}")

    risk_score = min(len(sanctions_hits) * 25, 100)  # crude initial score

    return {
        "imo_number":    imo,
        "vessel":        vessel,
        "sanctions_hits": sanctions_hits,
        "risk_factors":  risk_factors,
        "risk_score":    risk_score,
        "sanctioned":    len(sanctions_hits) > 0,
    }
