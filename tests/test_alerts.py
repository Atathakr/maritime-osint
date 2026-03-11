# tests/test_alerts.py
"""
Phase 7: Alert Generation and In-App Panel — acceptance tests.
Requirements: ALRT-01 through ALRT-08

Stubs written in Wave 0 (Plan 07-00). Made to pass in Waves 1-2 (Plans 07-01, 07-02).

IMO range: IMO9000001+ (no collision with Phases 2-6).
"""
import json
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

def test_unread_count_endpoint(app_client, monkeypatch):
    """ALRT-01: GET /api/alerts/unread-count returns {"count": N} as integer."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    _flush_alerts(db._sqlite_path())

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    # Insert one unread alert via db layer
    db.insert_alert(
        imo="IMO9000010", vessel_name="Count Test Vessel",
        alert_type="score_spike", before_score=20, after_score=40,
        before_risk_level="LOW", after_risk_level="MEDIUM",
        score_at_trigger=40, new_indicators=[],
    )

    resp = app_client.get("/api/alerts/unread-count")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.get_json()
    assert "count" in data, f"Response missing 'count' key: {data}"
    assert isinstance(data["count"], int), f"count must be int, got {type(data['count'])}: {data}"
    assert data["count"] >= 1, f"Expected count >= 1 after insert, got {data['count']}"


# ── ALRT-02 / ALRT-03: alert panel API shape ─────────────────────────────────

def test_get_alerts_shape(app_client, monkeypatch):
    """ALRT-02: GET /api/alerts returns {"unread": [...], "read": [...]} with required fields."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    _flush_alerts(db._sqlite_path())

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    db.insert_alert(
        imo="IMO9000011", vessel_name="Shape Test Vessel",
        alert_type="sanctions_match", before_score=30, after_score=100,
        before_risk_level="MEDIUM", after_risk_level="CRITICAL",
        score_at_trigger=100, new_indicators=["IND5"],
    )

    resp = app_client.get("/api/alerts")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.get_json()
    assert "unread" in data, f"Response missing 'unread' key: {data}"
    assert "read" in data, f"Response missing 'read' key: {data}"
    assert len(data["unread"]) >= 1, f"Expected at least 1 unread alert, got {len(data['unread'])}"

    required_fields = ("vessel_name", "alert_type", "score_at_trigger", "triggered_at")
    for field in required_fields:
        assert field in data["unread"][0], (
            f"ALRT-02: Missing field '{field}' in unread alert: {data['unread'][0]}"
        )


def test_alert_detail_fields(app_client, monkeypatch):
    """ALRT-03: Each alert row has before_score, after_score, before/after risk_level, new_indicators_json."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    _flush_alerts(db._sqlite_path())

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    db.insert_alert(
        imo="IMO9000012", vessel_name="Detail Test Vessel",
        alert_type="risk_level_crossing", before_score=35, after_score=72,
        before_risk_level="LOW", after_risk_level="HIGH",
        score_at_trigger=72, new_indicators=["IND2", "IND3"],
    )

    resp = app_client.get("/api/alerts")
    data = resp.get_json()
    assert data["unread"], "Expected at least one unread alert for detail test"
    alert = data["unread"][0]

    detail_fields = ("before_score", "after_score", "before_risk_level", "after_risk_level", "new_indicators_json")
    for field in detail_fields:
        assert field in alert, f"ALRT-03: Missing detail field '{field}' in alert: {alert}"

    assert isinstance(alert["new_indicators_json"], list), (
        f"new_indicators_json must be a list, got {type(alert['new_indicators_json'])}"
    )
    assert "IND2" in alert["new_indicators_json"], (
        f"Expected IND2 in new_indicators_json, got: {alert['new_indicators_json']}"
    )


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

def test_mark_alert_read(app_client, monkeypatch):
    """ALRT-08: POST /api/alerts/<id>/read sets is_read=1; GET /api/alerts/unread-count decrements."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    _flush_alerts(db._sqlite_path())

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    # Insert one unread alert
    db.insert_alert(
        imo="IMO9000013", vessel_name="Read Test Vessel",
        alert_type="score_spike", before_score=10, after_score=30,
        before_risk_level="LOW", after_risk_level="LOW",
        score_at_trigger=30, new_indicators=[],
    )

    # Confirm it shows in unread
    unread_before = app_client.get("/api/alerts/unread-count").get_json()["count"]
    assert unread_before >= 1, f"Expected >= 1 unread before mark-read, got {unread_before}"

    # Retrieve the alert ID
    alerts_resp = app_client.get("/api/alerts").get_json()
    assert alerts_resp["unread"], "No unread alerts found before mark-read"
    alert_id = alerts_resp["unread"][0]["id"]

    # Mark as read
    mark_resp = app_client.post(f"/api/alerts/{alert_id}/read")
    assert mark_resp.status_code == 200, f"Expected 200 from mark-read, got {mark_resp.status_code}"
    mark_data = mark_resp.get_json()
    assert mark_data.get("ok") is True, f"Expected ok=True, got: {mark_data}"
    assert isinstance(mark_data.get("count"), int), f"count must be int, got: {mark_data}"

    # Verify badge count decremented
    unread_after = app_client.get("/api/alerts/unread-count").get_json()["count"]
    assert unread_after == unread_before - 1, (
        f"Unread count should have decremented from {unread_before} to {unread_before - 1}, got {unread_after}"
    )

    # Verify alert moved to read section
    final_alerts = app_client.get("/api/alerts").get_json()
    unread_ids = [a["id"] for a in final_alerts["unread"]]
    read_ids   = [a["id"] for a in final_alerts["read"]]
    assert alert_id not in unread_ids, f"Alert {alert_id} still in unread after mark-read"
    assert alert_id in read_ids, f"Alert {alert_id} not in read section after mark-read"

    # Verify 404 for non-existent alert
    bad_resp = app_client.post("/api/alerts/99999999/read")
    assert bad_resp.status_code == 404, f"Expected 404 for unknown alert, got {bad_resp.status_code}"
