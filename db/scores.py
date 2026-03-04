# db/scores.py
"""
Vessel risk score persistence — placeholder for Phase 2.

Phase 2 will add:
  - vessel_scores table (mmsi, composite_score, indicator_json JSONB, computed_at, is_sanctioned)
  - vessel_score_history table (append-only, 90-day retention)
  - upsert_vessel_score(mmsi, score, indicator_json) function
  - get_vessel_score(mmsi) function
  - mark_scores_stale(mmsi_list) function
  - get_stale_vessels() function

TODO (Phase 2): implement pre-computed score CRUD
"""

# TODO(phase-2): add vessel_scores table DDL to init_db() in schema.py
# TODO(phase-2): implement upsert_vessel_score(), get_vessel_scores(),
#                mark_risk_scores_stale(), get_score_history()
