# tests/test_db_package.py
"""DB-3 — verify db/ package re-exports all public functions and private helpers."""
import os
os.environ["DATABASE_URL"] = ""  # Force SQLite; must precede any db import

import db

PUBLIC_FUNCTIONS = [
    # schema
    "init_db",
    # vessels
    "upsert_sanctions_entries", "get_sanctions_entries", "get_sanctions_counts",
    "get_vessels", "get_vessel", "get_vessel_count",
    "get_vessel_memberships", "get_vessel_ownership", "get_vessel_flag_history",
    "get_ais_vessel_by_imo",
    "search_sanctions_by_imo", "search_sanctions_by_mmsi", "search_sanctions_by_name",
    # sanctions/reconcile
    "find_imo_collisions", "find_mmsi_imo_collisions",
    "merge_canonical", "rebuild_all_source_tags",
    # ais
    "insert_ais_positions", "upsert_ais_vessel", "update_ais_vessel_position",
    "get_ais_vessels", "get_recent_positions", "find_ais_gaps",
    "get_consecutive_ais_pairs", "get_ais_positions", "get_active_mmsis",
    "get_vessel_track", "find_sts_candidates",
    # findings
    "upsert_dark_periods", "get_dark_periods",
    "upsert_sts_events", "get_sts_events", "get_sts_zone_count",
    "upsert_speed_anomalies", "get_speed_anomaly_summary",
    "upsert_loitering_events", "get_loitering_summary",
    "upsert_port_calls", "get_port_call_summary",
    "upsert_psc_detentions", "get_psc_detentions",
    "get_vessel_indicator_summary",
    # ingest log + stats
    "log_ingest_start", "log_ingest_complete", "get_ingest_log",
    "get_stats", "get_map_vessels_raw",
]

SEMI_PRIVATE = ["_BACKEND", "_conn", "_cursor", "_rows", "_row"]

def test_all_public_functions_exported():
    for fn in PUBLIC_FUNCTIONS:
        assert hasattr(db, fn), f"db.{fn} missing from __init__.py"

def test_private_helpers_exported():
    for name in SEMI_PRIVATE:
        assert hasattr(db, name), f"db.{name} missing — loitering.py/ports.py use it"

def test_backend_is_sqlite():
    assert db._BACKEND == "sqlite", "Expected sqlite when DATABASE_URL=''"

def test_import_and_init(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    db._init_backend()
    db.init_db()  # Should not raise
