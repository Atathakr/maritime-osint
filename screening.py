"""
Vessel screening module — query sanctions lists by IMO, MMSI, or name.

Screening is the core Session 1 deliverable: given any vessel identifier,
return all matching sanctions entries with confidence metadata.

Session 4 update: hits now come from vessels_canonical (one row per unique
vessel) with attached memberships list for data lineage.  Each hit includes:
  - canonical_id, entity_name, imo_number, mmsi, vessel_type, flag_state
  - source_tags     — ordered list of sanctions list display labels
                      e.g. ["OFAC SDN", "EU", "UN SC"]
  - memberships     — full list of per-source membership rows (for profiles)
  - match_method    — how the canonical record was identified
  - match_confidence — human-readable screening confidence label (added here)
"""

import re

import db
import schemas
import risk_config


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


def _annotate_hit(hit: dict, query_type: str) -> None:
    """
    Annotate a single hit dict in-place with match_confidence.
    JSON parsing and list initialisation are handled by ScreeningHit's
    model_validator, so no pre-processing is needed here.
    """
    if hit.get("imo_number") and query_type == "imo":
        hit["match_confidence"] = "HIGH — exact IMO match"
    elif hit.get("mmsi") and query_type == "mmsi":
        hit["match_confidence"] = "HIGH — exact MMSI match"
    else:
        hit["match_confidence"] = "MEDIUM — name match (verify IMO)"


def screen(query: str) -> schemas.ScreeningResult:
    """
    Screen a vessel against all loaded sanctions lists.

    Input: any of —
      - IMO number (7 digits, e.g. "9876543" or "IMO 9876543")
      - MMSI (9 digits)
      - Vessel name (partial match)

    Returns a ScreeningResult model.
    """
    query = query.strip()
    if not query:
        return schemas.ScreeningResult(
            query="", query_type="name", sanctioned=False, total_hits=0, hits=[], error="Empty query"
        )

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

    # If an IMO/MMSI query returned nothing, try a name fallback
    if not hits and query_type in ("imo", "mmsi"):
        fallback = db.search_sanctions_by_name(query)
        if fallback:
            hits = fallback
            query_type = f"{query_type}_name_fallback"

    sanitized_hits = []
    for hit in hits:
        _annotate_hit(hit, query_type)
        # Attach ownership opacity data
        canonical_id = hit.get("canonical_id")
        imo = hit.get("imo_number")
        if canonical_id:
            hit["ownership"]    = db.get_vessel_ownership(canonical_id)
            hit["flag_history"] = db.get_vessel_flag_history(imo) if imo else []
        try:
            sanitized_hits.append(schemas.ScreeningHit.model_validate(hit))
        except Exception:
            # Skip invalid hits for now, log if needed
            continue

    return schemas.ScreeningResult(
        query=query,
        query_type=query_type,
        sanctioned=len(sanitized_hits) > 0,
        total_hits=len(sanitized_hits),
        hits=sanitized_hits,
    )


def screen_vessel_detail(imo: str) -> schemas.VesselDetail:
    """
    Full screening report for a known vessel (by IMO).
    Fetches the canonical vessel record, all sanctions list memberships,
    and AIS intelligence signals (dark periods, STS events, last position,
    speed anomalies, flag risk, and flag hopping).

    Risk score formula:
      sanctioned → 100 (hard ceiling)
      else       → min(
          min(dp×10, 40) + min(sts×15, 45)          (IND1 + IND7)
          + flag_tier×7                              (IND17, max 21)
          + min(hop_count×8, 16)                     (IND15)
          + min(spoof_count×8, 24),                  (IND10)
          99
      )

    Returns a VesselDetail model.
    """
    imo_clean = re.sub(r"\D", "", imo)
    vessel = db.get_vessel(imo_clean)
    sanctions_hits = db.search_sanctions_by_imo(imo_clean)

    processed_hits = []
    for hit in sanctions_hits:
        _annotate_hit(hit, "imo")
        canonical_id = hit.get("canonical_id")
        imo_num = hit.get("imo_number")
        if canonical_id:
            hit["ownership"]    = db.get_vessel_ownership(canonical_id)
            hit["flag_history"] = db.get_vessel_flag_history(imo_num) if imo_num else []
        try:
            processed_hits.append(schemas.ScreeningHit.model_validate(hit))
        except Exception:
            continue

    # Collect all unique source-list display labels
    all_tags: list[str] = []
    total_memberships = 0
    for h in processed_hits:
        for tag in h.source_tags:
            if tag not in all_tags:
                all_tags.append(tag)
        total_memberships += len(h.memberships)

    risk_factors: list[str] = []
    if all_tags:
        risk_factors.append(f"Listed on: {', '.join(sorted(all_tags))}")

    # ── Flag state risk (IND17) ───────────────────────────────────────────
    flag_code: str | None = None
    if vessel and vessel.get("flag_normalized"):
        flag_code = vessel["flag_normalized"]
    elif processed_hits and processed_hits[0].flag_state:
        flag_code = processed_hits[0].flag_state
    flag_tier  = risk_config.FLAG_RISK_TIERS.get((flag_code or "").upper(), 0)
    flag_score = flag_tier * 7

    # ── Flag hopping (IND15) ──────────────────────────────────────────────
    flag_history = db.get_vessel_flag_history(imo_clean)
    distinct_flags = len({f.get("flag_state") for f in flag_history if f.get("flag_state")})
    hop_count  = max(0, distinct_flags - 1)
    hop_score  = min(hop_count * 8, 16)

    # ── Indicator summary (dark periods + STS + AIS + speed anomalies) ────
    # Prefer MMSI from vessel record; fall back to first sanctions hit
    mmsi: str | None = None
    if vessel and vessel.get("mmsi"):
        mmsi = vessel["mmsi"]
    elif processed_hits and processed_hits[0].mmsi:
        mmsi = processed_hits[0].mmsi

    indicator_summary: schemas.IndicatorSummary | None = None
    if mmsi:
        try:
            raw = db.get_vessel_indicator_summary(mmsi)
            # Attach flag/hop counts so the schema carries them through to the UI
            raw["flag_risk_tier"] = flag_tier
            raw["flag_hop_count"] = hop_count
            indicator_summary = schemas.IndicatorSummary.model_validate(raw)
        except Exception:
            pass

    # ── Composite risk score ──────────────────────────────────────────────
    if processed_hits:
        risk_score = 100
    else:
        dp    = indicator_summary.dp_count    if indicator_summary else 0
        sts   = indicator_summary.sts_count   if indicator_summary else 0
        spoof = indicator_summary.spoof_count if indicator_summary else 0
        risk_score = min(
            min(dp * 10, 40) + min(sts * 15, 45)
            + flag_score + hop_score + min(spoof * 8, 24),
            99,
        )

    return schemas.VesselDetail(
        imo_number=imo_clean,
        vessel=vessel,
        sanctions_hits=processed_hits,
        source_tags=all_tags,
        total_memberships=total_memberships,
        risk_factors=risk_factors,
        risk_score=risk_score,
        sanctioned=len(processed_hits) > 0,
        indicator_summary=indicator_summary,
    )
