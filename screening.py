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
from datetime import date, datetime, timedelta, timezone

import db
from db.scores import SCORE_STALENESS_MINUTES
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


def _check_ownership_chain(canonical_id: str) -> tuple[list[dict], int]:
    """
    Check whether any entity in the vessel's ownership / management chain
    appears on a sanctions list (IND21).

    Uses the existing fuzzy-name search against vessels_canonical.
    Returns (hits_list, score_contribution).

    Each hit dict:
      entity_name    — the ownership-chain entity that matched
      role           — e.g. 'owner', 'operator', 'manager'
      source         — data source for the ownership record
      matched_sanctions — list of up to 3 matching sanctioned entity names
    """
    ownership = db.get_vessel_ownership(canonical_id)
    if not ownership:
        return [], 0

    found: list[dict] = []
    seen: set[str] = set()

    for entry in ownership:
        entity_name = (entry.get("entity_name") or "").strip()
        if not entity_name or entity_name in seen:
            continue
        seen.add(entity_name)
        matches = db.search_sanctions_by_name(entity_name)
        if matches:
            found.append({
                "entity_name":        entity_name,
                "role":               entry.get("role"),
                "source":             entry.get("source"),
                "matched_sanctions":  [m.get("entity_name") for m in matches[:3]],
            })

    score = min(len(found) * risk_config.IND21_OWNER_SANCTION, 40)
    return found, score


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


def score_is_stale(score_row: dict, minutes: int = SCORE_STALENESS_MINUTES) -> bool:
    """
    Return True if the cached score should be recomputed.
    Triggers on: is_stale flag set, computed_at missing/unparseable, or age > minutes.
    """
    if score_row.get("is_stale"):
        return True
    computed_at_str = score_row.get("computed_at")
    if not computed_at_str:
        return True
    try:
        # Strip trailing 'Z' for Python <3.11 compatibility; then attach UTC
        ts = datetime.fromisoformat(computed_at_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts > timedelta(minutes=minutes)
    except (ValueError, TypeError):
        return True


def compute_vessel_score(imo: str) -> dict:
    """
    Compute composite risk score and full indicator breakdown for a vessel.

    Returns a dict with:
      composite_score  int         0-100 (100 = sanctioned)
      is_sanctioned    bool
      indicator_json   dict        all 31 IND keys; see 02-CONTEXT.md schema
      computed_at      str         ISO 8601 UTC timestamp

    Called by:
      - APScheduler refresh job (_do_score_refresh in app.py)
      - screen_vessel_detail() staleness fallback
    """
    imo_clean = re.sub(r"\D", "", imo)
    computed_at = datetime.now(timezone.utc).isoformat()

    # ── Initialise all 31 indicators to not-fired ─────────────────────
    ind: dict[str, dict] = {f"IND{i}": {"pts": 0, "fired": False} for i in range(1, 32)}

    # ── Vessel and sanctions lookup ───────────────────────────────────
    vessel = db.get_vessel(imo_clean)
    if vessel is None:
        vessel = db.get_ais_vessel_by_imo(imo_clean)
    sanctions_hits_raw = db.search_sanctions_by_imo(imo_clean)
    is_sanctioned = len(sanctions_hits_raw) > 0

    # ── IND17: Flag risk tier (static — no fired_at) ──────────────────
    flag_code: str | None = None
    if vessel and vessel.get("flag_normalized"):
        flag_code = vessel["flag_normalized"]
    elif sanctions_hits_raw:
        flag_code = sanctions_hits_raw[0].get("flag_state")
    flag_tier = risk_config.get_flag_tier(flag_code)
    flag_score = flag_tier * 7
    if flag_tier > 0:
        ind["IND17"] = {"pts": flag_score, "fired": True}

    # ── IND15: Flag hopping (static — no fired_at) ───────────────────
    flag_history = db.get_vessel_flag_history(imo_clean)
    distinct_flags = len({f.get("flag_state") for f in flag_history if f.get("flag_state")})
    hop_count = max(0, distinct_flags - 1)
    hop_score = min(hop_count * 8, 16)
    if hop_count > 0:
        ind["IND15"] = {"pts": hop_score, "fired": True}

    # ── AIS-based indicators (require MMSI) ──────────────────────────
    mmsi: str | None = None
    if vessel and vessel.get("mmsi"):
        mmsi = vessel["mmsi"]
    elif sanctions_hits_raw:
        mmsi = sanctions_hits_raw[0].get("mmsi")

    dp = sts = sts_zones = spoof = port = loiter = 0
    if mmsi:
        raw = db.get_vessel_indicator_summary(mmsi)

        # IND1: Dark periods
        dp = raw.get("dp_count") or 0
        pts = min(dp * 10, 40)
        if dp > 0:
            ind["IND1"] = {"pts": pts, "fired": True, "fired_at": raw.get("dp_last_ts") or computed_at}

        # IND7: STS events
        sts = raw.get("sts_count") or 0
        pts = min(sts * 15, 45)
        if sts > 0:
            ind["IND7"] = {"pts": pts, "fired": True, "fired_at": raw.get("sts_last_ts") or computed_at}

        # IND8: STS in risk zone (fired_at reuses STS timestamp)
        sts_zones = raw.get("sts_risk_zone_count") or 0
        pts = min(sts_zones * 5, 10)
        if sts_zones > 0:
            ind["IND8"] = {"pts": pts, "fired": True, "fired_at": raw.get("sts_last_ts") or computed_at}

        # IND10: Speed anomaly / AIS spoofing
        spoof = raw.get("spoof_count") or 0
        pts = min(spoof * 8, 24)
        if spoof > 0:
            ind["IND10"] = {"pts": pts, "fired": True, "fired_at": raw.get("spoof_last_ts") or computed_at}

        # IND9: Loitering
        loiter = raw.get("loiter_count") or 0
        pts = min(loiter * 5, 15)
        if loiter > 0:
            ind["IND9"] = {"pts": pts, "fired": True, "fired_at": raw.get("loiter_last_ts") or computed_at}

        # IND29: Sanctioned port calls
        port = raw.get("port_count") or 0
        pts = min(port * 20, 40)
        if port > 0:
            ind["IND29"] = {"pts": pts, "fired": True, "fired_at": raw.get("port_last_ts") or computed_at}

    # ── IND23: Vessel age (static — no fired_at) ──────────────────────
    build_year = vessel.get("build_year") if vessel else None
    age_score = 0
    if build_year and isinstance(build_year, int):
        vessel_age = date.today().year - build_year
        age_score = max(
            0,
            min(
                (vessel_age - risk_config.IND23_AGE_THRESHOLD) * risk_config.IND23_PTS_PER_YEAR,
                risk_config.IND23_CAP,
            ),
        )
        if age_score > 0:
            ind["IND23"] = {"pts": age_score, "fired": True}

    # ── IND21: Ownership-chain sanctions match (static — no fired_at) ──
    canonical_id: str | None = None
    if vessel and vessel.get("canonical_id"):
        canonical_id = vessel["canonical_id"]
    elif sanctions_hits_raw:
        canonical_id = sanctions_hits_raw[0].get("canonical_id")

    owner_sanctions_score = 0
    if canonical_id and not is_sanctioned:
        _, owner_sanctions_score = _check_ownership_chain(canonical_id)
        if owner_sanctions_score > 0:
            ind["IND21"] = {"pts": owner_sanctions_score, "fired": True}

    # ── IND31: PSC detentions (fired_at = detention_date) ─────────────
    psc_detentions = db.get_psc_detentions(imo_clean)
    psc_score = min(len(psc_detentions) * risk_config.IND31_PER_DETENTION, risk_config.IND31_CAP)
    if psc_detentions:
        ind["IND31"] = {
            "pts": psc_score,
            "fired": True,
            "fired_at": psc_detentions[0].get("detention_date") or computed_at,
        }

    # ── IND16: Name discrepancy (static — no fired_at) ────────────────
    if vessel and vessel.get("entity_name") and mmsi:
        canonical_name = vessel["entity_name"].strip().upper()
        ais_vessel = db.get_ais_vessel_by_imo(imo_clean)
        if ais_vessel and ais_vessel.get("vessel_name"):
            ais_name = ais_vessel["vessel_name"].strip().upper()
            if ais_name and ais_name != canonical_name:
                if canonical_name not in ais_name and ais_name not in canonical_name:
                    ind["IND16"] = {"pts": 0, "fired": True}  # detected but no pts in current formula

    # ── Composite score ────────────────────────────────────────────────
    if is_sanctioned:
        composite_score = 100
    else:
        composite_score = min(
            min(dp * 10, 40) + min(sts * 15, 45) + min(sts_zones * 5, 10)
            + flag_score + hop_score + min(spoof * 8, 24)
            + min(port * 20, 40) + min(loiter * 5, 15) + age_score
            + owner_sanctions_score + psc_score,
            99,
        )

    return {
        "composite_score": composite_score,
        "is_sanctioned":   is_sanctioned,
        "indicator_json":  ind,
        "computed_at":     computed_at,
    }


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
          + min(sts_zone_count×5, 10)                (IND8)
          + flag_tier×7                              (IND17, max 21)
          + min(hop_count×8, 16)                     (IND15)
          + min(spoof_count×8, 24)                   (IND10)
          + min(port_count×20, 40)                   (IND29)
          + min(loiter_count×5, 15),                 (IND9)
          99
      )

    Returns a VesselDetail model.
    """
    imo_clean = re.sub(r"\D", "", imo)

    # ── Cached score — check freshness before running expensive queries ────
    score_row = db.get_vessel_score(imo_clean)
    if score_row is None or score_is_stale(score_row):
        fresh = compute_vessel_score(imo_clean)
        db.upsert_vessel_score(imo_clean, fresh)
        _cached_score = fresh["composite_score"]
        _cached_sanctioned = fresh["is_sanctioned"]
    else:
        _cached_score = score_row["composite_score"]
        _cached_sanctioned = bool(score_row.get("is_sanctioned"))

    vessel = db.get_vessel(imo_clean)
    # For vessels tracked via AIS but not listed in the sanctions DB, fall back
    # to the ais_vessels table so the profile header has a name and MMSI.
    if vessel is None:
        vessel = db.get_ais_vessel_by_imo(imo_clean)
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
    flag_tier  = risk_config.get_flag_tier(flag_code)
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

    # Build indicator_summary — always include flag/hop signals; add AIS signals if MMSI available
    indicator_summary: schemas.IndicatorSummary | None = None
    try:
        if mmsi:
            raw = db.get_vessel_indicator_summary(mmsi)
        else:
            raw = {}
        raw["flag_risk_tier"] = flag_tier
        raw["flag_hop_count"] = hop_count
        indicator_summary = schemas.IndicatorSummary.model_validate(raw)
    except Exception:
        pass

    # ── Vessel age (IND23) ────────────────────────────────────────────────
    build_year = vessel.get("build_year") if vessel else None
    if build_year and isinstance(build_year, int):
        vessel_age = date.today().year - build_year
        age_score  = max(
            0,
            min(
                (vessel_age - risk_config.IND23_AGE_THRESHOLD) * risk_config.IND23_PTS_PER_YEAR,
                risk_config.IND23_CAP,
            ),
        )
        if age_score > 0:
            risk_factors.append(f"Vessel age: {vessel_age} years (+{age_score} pts, IND23)")
    else:
        vessel_age = None
        age_score  = 0

    # Attach vessel_age to indicator_summary so the frontend can render it
    if indicator_summary is not None and vessel_age is not None:
        indicator_summary.vessel_age = vessel_age

    # ── IND21: Ownership-chain sanctions match ────────────────────────────
    owner_sanctions_hits: list[dict] = []
    owner_sanctions_score = 0
    # Prefer canonical_id from vessel record (sanctions DB entry), else first hit
    canonical_id_for_chain: str | None = None
    if vessel and vessel.get("canonical_id"):
        canonical_id_for_chain = vessel["canonical_id"]
    elif processed_hits and processed_hits[0].canonical_id:
        canonical_id_for_chain = processed_hits[0].canonical_id

    if canonical_id_for_chain and not processed_hits:
        # Only score ownership chain for vessels not directly sanctioned
        owner_sanctions_hits, owner_sanctions_score = _check_ownership_chain(canonical_id_for_chain)
        if owner_sanctions_hits:
            names = ", ".join(h["entity_name"] for h in owner_sanctions_hits[:2])
            risk_factors.append(
                f"Ownership chain sanctions match: {names}"
                + (f" and {len(owner_sanctions_hits) - 2} more" if len(owner_sanctions_hits) > 2 else "")
                + f" (+{owner_sanctions_score} pts, IND21)"
            )
    elif canonical_id_for_chain:
        # Still run the check for informational display even on sanctioned vessels
        owner_sanctions_hits, _ = _check_ownership_chain(canonical_id_for_chain)

    # ── IND16: Vessel name discrepancy (AIS vs canonical) ────────────────
    name_discrepancy: str | None = None
    if vessel and vessel.get("entity_name"):
        canonical_name = vessel["entity_name"].strip().upper()
        ais_vessel = db.get_ais_vessel_by_imo(imo_clean)
        if ais_vessel and ais_vessel.get("vessel_name"):
            ais_name = ais_vessel["vessel_name"].strip().upper()
            if ais_name and ais_name != canonical_name:
                # Flag only when neither name is a prefix/substring of the other
                # (handles common cases like "VESSEL NAME" vs "VESSEL NAME I")
                if canonical_name not in ais_name and ais_name not in canonical_name:
                    name_discrepancy = f'AIS: "{ais_vessel["vessel_name"]}" ≠ Canonical: "{vessel["entity_name"]}"'

    # ── IND31: PSC detention record ───────────────────────────────────────
    psc_detentions = db.get_psc_detentions(imo_clean)
    psc_score = min(len(psc_detentions) * risk_config.IND31_PER_DETENTION, risk_config.IND31_CAP)
    if psc_detentions and not processed_hits:
        authorities = sorted({d.get("authority", "") for d in psc_detentions if d.get("authority")})
        risk_factors.append(
            f"PSC detentions: {len(psc_detentions)} in last 24 months"
            + (f" ({', '.join(authorities)})" if authorities else "")
            + f" (+{psc_score} pts, IND31)"
        )

    # ── Composite risk score — use pre-computed cache ─────────────────────
    # compute_vessel_score() / staleness fallback above already persisted the score.
    # Use _cached_score here; processed_hits is still used for sanctioned display.
    risk_score = _cached_score

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
        owner_sanctions_hits=owner_sanctions_hits,
        psc_detentions=[dict(d) for d in psc_detentions],
        name_discrepancy=name_discrepancy,
    )
