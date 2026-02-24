"""
reconcile.py — cross-list canonical vessel reconciliation.

Run after each ingest (or on demand via POST /api/reconcile) to link
sanctions entries from different sources that refer to the same vessel.

Tier 1 — IMO exact match
  Handled implicitly during upsert: both OFAC and OpenSanctions entries
  that share an IMO number already resolve to canonical_id="IMO:{imo}" and
  merge into the same row.  This pass is a safety sweep for any edge cases.

Tier 2 — MMSI match
  OFAC sometimes has an MMSI but no IMO for a vessel; OpenSanctions may
  carry the same vessel with an IMO.  After both ingests, we have:
    canonical "MMSI:123456789"  ← OFAC entry
    canonical "IMO:9228538"     ← OpenSanctions entry (also has mmsi=123456789)
  This pass detects the overlap and merges the MMSI canonical into the
  IMO canonical, reassigning all memberships and combining source_tags.

Data-lineage note
  merge_canonical() preserves all sanctions_memberships rows — no source
  data is deleted, only the canonical pointer is updated.  The match_method
  on the surviving canonical record documents how the link was established.
"""

import logging

import db

logger = logging.getLogger(__name__)


def run_reconciliation() -> dict:
    """
    Execute Tier 1 and Tier 2 reconciliation passes.
    Rebuilds source_tags on all canonical records afterwards.
    Returns a summary dict suitable for the API response.
    """
    tier1 = _reconcile_tier1_imo()
    tier2 = _reconcile_tier2_mmsi()
    db.rebuild_all_source_tags()

    logger.info(
        "Reconciliation complete — Tier 1 merges: %d, Tier 2 merges: %d",
        tier1, tier2,
    )
    return {
        "tier1_imo_merges":  tier1,
        "tier2_mmsi_merges": tier2,
    }


# ── Tier 1: IMO safety sweep ──────────────────────────────────────────────

def _reconcile_tier1_imo() -> int:
    """
    If two canonical records somehow share the same imo_number (shouldn't
    happen after upsert logic, but guard against it), merge the non-IMO-keyed
    one into the IMO-keyed canonical.
    """
    collisions = db.find_imo_collisions()
    merged = 0
    for imo_number, canonical_ids in collisions:
        winner = f"IMO:{imo_number}"
        for loser in canonical_ids:
            if loser != winner:
                logger.info(
                    "Tier 1 merge: %s → %s (shared IMO %s)", loser, winner, imo_number
                )
                db.merge_canonical(loser, winner)
                merged += 1
    return merged


# ── Tier 2: MMSI→IMO merge ───────────────────────────────────────────────

def _reconcile_tier2_mmsi() -> int:
    """
    Find MMSI-keyed canonicals whose MMSI value also appears in an IMO-keyed
    canonical.  Merge the MMSI canonical into the IMO canonical.

    Confidence: MEDIUM-HIGH.  MMSI reassignment is rare for sanctioned vessels.
    The surviving canonical retains match_method="imo_exact" (the stronger key).
    """
    collisions = db.find_mmsi_imo_collisions()
    merged = 0
    for mmsi_cid, imo_cid in collisions:
        logger.info(
            "Tier 2 merge: %s → %s (shared MMSI)", mmsi_cid, imo_cid
        )
        db.merge_canonical(mmsi_cid, imo_cid)
        merged += 1
    return merged
