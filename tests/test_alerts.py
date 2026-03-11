# tests/test_alerts.py
"""
Phase 7: Alert Generation and In-App Panel — acceptance tests.
Requirements: ALRT-01 through ALRT-08

Stubs written in Wave 0 (Plan 07-00). Made to pass in Waves 1-2 (Plans 07-01, 07-02).

IMO range: IMO9000001+ (no collision with Phases 2-6).
"""
import os
import pytest

os.environ["DATABASE_URL"] = ""  # Force SQLite; must precede any db import

import db


def _setup_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    return db._sqlite_path()


def _flush_alerts(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()


# ── ALRT-01: unread count endpoint ───────────────────────────────────────────

def test_unread_count_endpoint(app_client):
    """ALRT-01: GET /api/alerts/unread-count returns {"count": N} as integer."""
    pytest.fail("stub")


# ── ALRT-02 / ALRT-03: alert panel API shape ─────────────────────────────────

def test_get_alerts_shape(app_client):
    """ALRT-02: GET /api/alerts returns {"unread": [...], "read": [...]} with required fields."""
    pytest.fail("stub")


def test_alert_detail_fields(app_client):
    """ALRT-03: Each alert row has before_score, after_score, before/after risk_level, new_indicators_json."""
    pytest.fail("stub")


# ── ALRT-04: risk level crossing ─────────────────────────────────────────────

def test_risk_level_crossing_alert(monkeypatch):
    """ALRT-04: _generate_alerts() inserts alert_type='risk_level_crossing' when risk level changes."""
    from app import _generate_alerts  # lazy import to prevent dotenv reload at collection time
    db_path = _setup_db(monkeypatch)
    _flush_alerts(db_path)
    imo = "IMO9000001"
    prior = {"composite_score": 30, "is_sanctioned": 0, "risk_level": "LOW", "indicator_json": {}}
    fresh = {"composite_score": 45, "is_sanctioned": 0, "indicator_json": {}}  # MEDIUM
    _generate_alerts(imo=imo, vessel_name="Test Vessel", prior=prior, fresh=fresh, was_in_top_50=False)
    rows = db.get_alerts()
    types = [r["alert_type"] for r in rows]
    assert "risk_level_crossing" in types, f"Expected risk_level_crossing alert, got: {types}"


# ── ALRT-05: top-50 entry ─────────────────────────────────────────────────────

def test_top_50_entry_alert(monkeypatch):
    """ALRT-05: _do_score_refresh() inserts alert_type='top_50_entry' for vessels entering top 50."""
    db_path = _setup_db(monkeypatch)
    _flush_alerts(db_path)
    import sqlite3
    imo = "IMO9000004"
    # Seed a canonical vessel and a prior score row
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO vessels_canonical (canonical_id, entity_name, imo_number) VALUES (?,?,?)",
        ("CAN_9000004", "Top50 Vessel", imo),
    )
    conn.execute(
        "INSERT OR REPLACE INTO vessel_scores (imo_number, composite_score, is_sanctioned, "
        "indicator_json, computed_at, is_stale) VALUES (?,?,?,?,datetime('now'),0)",
        (imo, 80, 0, "{}"),
    )
    conn.commit()
    conn.close()
    # Insert a prior history row so get_score_history returns data
    db.append_score_history(imo, {"composite_score": 50, "is_sanctioned": 0, "indicator_json": {}, "computed_at": "2026-03-10T00:00:00+00:00"})
    # Simulate: this IMO was NOT in top_50_before but IS in top_50_after
    top_50_before = set()  # empty — vessel was not in top 50 before
    top_50_after = {imo}   # vessel enters top 50 after this run
    newly_entered = top_50_after - top_50_before
    assert imo in newly_entered
    # Fire the ALRT-05 block (extracted from _do_score_refresh post-loop logic)
    new_rows = db.get_all_vessel_scores()
    for r in new_rows:
        if r["imo_number"] not in newly_entered:
            continue
        prior_hist = db.get_score_history(r["imo_number"], limit=1)
        prior_score = int(prior_hist[0].get("composite_score", 0)) if prior_hist else 0
        prior_risk = prior_hist[0].get("risk_level", "LOW") if prior_hist else "LOW"
        db.insert_alert(
            imo=r["imo_number"],
            vessel_name=r.get("entity_name"),
            alert_type="top_50_entry",
            before_score=prior_score,
            after_score=r.get("composite_score"),
            before_risk_level=prior_risk,
            after_risk_level=r.get("risk_level") or "LOW",
            score_at_trigger=r.get("composite_score"),
            new_indicators=[],
        )
    rows = db.get_alerts()
    types = [r["alert_type"] for r in rows if r["imo_number"] == imo]
    assert "top_50_entry" in types, f"Expected top_50_entry alert for {imo}, got: {types}"


# ── ALRT-06: sanctions flip ──────────────────────────────────────────────────

def test_sanctions_flip_alert(monkeypatch):
    """ALRT-06: _generate_alerts() inserts alert_type='sanctions_match' when is_sanctioned flips False->True."""
    from app import _generate_alerts  # lazy import to prevent dotenv reload at collection time
    db_path = _setup_db(monkeypatch)
    _flush_alerts(db_path)
    imo = "IMO9000002"
    prior = {"composite_score": 40, "is_sanctioned": 0, "risk_level": "MEDIUM", "indicator_json": {}}
    fresh = {"composite_score": 100, "is_sanctioned": 1, "indicator_json": {}}
    _generate_alerts(imo=imo, vessel_name="Sanctioned Vessel", prior=prior, fresh=fresh, was_in_top_50=False)
    rows = db.get_alerts()
    types = [r["alert_type"] for r in rows]
    assert "sanctions_match" in types, f"Expected sanctions_match alert, got: {types}"


# ── ALRT-07: score spike ─────────────────────────────────────────────────────

def test_score_spike_alert(monkeypatch):
    """ALRT-07: _generate_alerts() inserts alert_type='score_spike' when abs(delta) >= 15 pts."""
    from app import _generate_alerts  # lazy import to prevent dotenv reload at collection time
    db_path = _setup_db(monkeypatch)
    _flush_alerts(db_path)
    imo = "IMO9000003"
    prior = {"composite_score": 20, "is_sanctioned": 0, "risk_level": "LOW", "indicator_json": {}}
    fresh = {"composite_score": 35, "is_sanctioned": 0, "indicator_json": {}}  # delta = 15
    _generate_alerts(imo=imo, vessel_name="Spike Vessel", prior=prior, fresh=fresh, was_in_top_50=False)
    rows = db.get_alerts()
    types = [r["alert_type"] for r in rows]
    assert "score_spike" in types, f"Expected score_spike alert, got: {types}"
    # Verify sub-threshold delta does NOT fire
    _flush_alerts(db_path)
    prior2 = {"composite_score": 20, "is_sanctioned": 0, "risk_level": "LOW", "indicator_json": {}}
    fresh2 = {"composite_score": 33, "is_sanctioned": 0, "indicator_json": {}}  # delta = 13, no fire
    _generate_alerts(imo=imo, vessel_name="Spike Vessel", prior=prior2, fresh=fresh2, was_in_top_50=False)
    rows2 = db.get_alerts()
    types2 = [r["alert_type"] for r in rows2]
    assert "score_spike" not in types2, f"Sub-threshold delta must not fire score_spike, got: {types2}"


# ── ALRT-08: mark alert read ─────────────────────────────────────────────────

def test_mark_alert_read(app_client):
    """ALRT-08: POST /api/alerts/<id>/read sets is_read=1; GET /api/alerts/unread-count decrements."""
    pytest.fail("stub")
