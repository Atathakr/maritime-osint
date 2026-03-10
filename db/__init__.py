# db/__init__.py
"""
Maritime OSINT database package — public re-export surface.

All callers use `import db; db.fn()`. This file is the only module they see.
Sub-modules are implementation details extracted incrementally (plans 01-01 through 01-02).

noqa: F401 suppresses "imported but unused" for intentional re-exports.
"""

# ── Connection layer ──────────────────────────────────────────────────────────
# Extracted: plan 01-01
# Private helpers re-exported for loitering.py and ports.py (use db._conn, db._BACKEND etc.)
from .connection import (  # noqa: F401
    _BACKEND,
    _conn,
    _cursor,
    _rows,
    _row,
    _ph,
    _ilike,
    _jp,
    _init_backend,
    _get_pool,
    _sqlite_path,
)

# ── Schema ────────────────────────────────────────────────────────────────────
# Extracted: plan 01-02 step 1
from .schema import init_db  # noqa: F401

# ── Vessels CRUD ──────────────────────────────────────────────────────────────
# Extracted: plan 01-02 step 2
from .vessels import (  # noqa: F401
    upsert_sanctions_entries, get_sanctions_entries, get_sanctions_counts,
    get_vessels, get_vessel, get_vessel_count,
    get_vessel_memberships, get_vessel_ownership, get_vessel_flag_history,
    get_ais_vessel_by_imo,
    search_sanctions_by_imo, search_sanctions_by_mmsi, search_sanctions_by_name,
    log_ingest_start, log_ingest_complete, get_ingest_log,
    get_stats, get_map_vessels_raw,
)

# ── Sanctions / reconcile ─────────────────────────────────────────────────────
# Extracted: plan 01-02 step 3
from .sanctions import (  # noqa: F401
    find_imo_collisions, find_mmsi_imo_collisions,
    merge_canonical, rebuild_all_source_tags,
)

# ── AIS CRUD ──────────────────────────────────────────────────────────────────
# Extracted: plan 01-02 step 4
from .ais import (  # noqa: F401
    insert_ais_positions, upsert_ais_vessel, update_ais_vessel_position,
    get_ais_vessels, get_recent_positions, find_ais_gaps,
    get_consecutive_ais_pairs, get_ais_positions, get_active_mmsis,
    get_vessel_track, find_sts_candidates,
)

# ── Findings / detection results ──────────────────────────────────────────────
# Extracted: plan 01-02 step 5
from .findings import (  # noqa: F401
    upsert_dark_periods, get_dark_periods,
    upsert_sts_events, get_sts_events, get_sts_zone_count,
    upsert_speed_anomalies, get_speed_anomaly_summary,
    upsert_loitering_events, get_loitering_summary,
    upsert_port_calls, get_port_call_summary,
    upsert_psc_detentions, get_psc_detentions,
    get_vessel_indicator_summary,
)

# ── Scores (Phase 2) ──────────────────────────────────────────────────────────
# Plan 02-01: vessel_scores + vessel_score_history DDL and CRUD
from .scores import (  # noqa: F401
    init_scores_tables, upsert_vessel_score, get_vessel_score,
    get_all_vessel_scores, mark_risk_scores_stale,
    append_score_history, prune_score_history,
    get_score_history,
    archive_old_ais_positions,
)
