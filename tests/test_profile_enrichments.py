# tests/test_profile_enrichments.py
"""
Phase 8: Vessel Profile Enrichments — acceptance tests.
Requirements: PROF-01, PROF-02

Stubs written in Wave 0 (Plan 08-00). Made to pass in Wave 1 (Plan 08-01).

IMO range: IMO0200001+ (no collision with Phases 2-7).
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


def _flush_history(db_path, imo):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM vessel_score_history WHERE imo_number = ?", (imo,))
    conn.commit()
    conn.close()


def test_profile_has_history_card(app_client, monkeypatch):
    """PROF-01: /vessel/<imo> HTML contains #score-history-card and Chart.js CDN script tag."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()

    imo = "IMO0200001"
    # Insert a vessel score so the profile route renders the {% else %} branch
    db.upsert_vessel_score(imo, {
        "composite_score": 55,
        "is_sanctioned": False,
        "indicator_json": {},
    })

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get(f"/vessel/{imo}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert 'id="score-history-card"' in html, (
        "Expected id='score-history-card' in vessel profile HTML"
    )
    assert 'id="recent-changes-card"' in html, (
        "Expected id='recent-changes-card' in vessel profile HTML"
    )
    assert "chart.js" in html.lower(), (
        "Expected Chart.js CDN script tag in vessel profile HTML"
    )


def test_history_single_snapshot(app_client, monkeypatch):
    """PROF-01: /api/vessels/<imo>/history with exactly 1 row returns valid JSON (not an error)."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()

    imo = "IMO0200002"
    db_path = db._sqlite_path()
    _flush_history(db_path, imo)

    # Insert exactly one history snapshot
    db.upsert_vessel_score(imo, {
        "composite_score": 45,
        "is_sanctioned": False,
        "indicator_json": {"IND1": {"pts": 10}},
    })
    db.append_score_history(imo, {
        "composite_score": 45,
        "is_sanctioned": False,
        "indicator_json": {"IND1": {"pts": 10}},
    })

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get(f"/api/vessels/{imo}/history")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = resp.get_json()
    assert data is not None, "Response was not valid JSON"
    assert "history" in data, f"Response missing 'history' key: {data}"
    assert isinstance(data["history"], list), f"history must be a list, got {type(data['history'])}"
    assert len(data["history"]) == 1, f"Expected exactly 1 history row, got {len(data['history'])}"

    row = data["history"][0]
    assert "composite_score" in row, f"History row missing composite_score: {row}"
    assert "risk_level" in row, f"History row missing risk_level: {row}"
    assert "recorded_at" in row, f"History row missing recorded_at: {row}"


def test_change_log_diff(app_client, monkeypatch):
    """PROF-02: Given 2 snapshots with score delta and indicator changes, history endpoint returns both rows with expected values."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()

    imo = "IMO0200003"
    db_path = db._sqlite_path()
    _flush_history(db_path, imo)

    # snap1 = older snapshot: score 60, MEDIUM, indicator IND3 fired
    db.append_score_history(imo, {
        "composite_score": 60,
        "is_sanctioned": False,
        "indicator_json": {"IND3": {"pts": 20}},
    })
    # snap0 = newer snapshot: score 72, HIGH, indicator IND7 fired (IND3 cleared)
    db.append_score_history(imo, {
        "composite_score": 72,
        "is_sanctioned": False,
        "indicator_json": {"IND7": {"pts": 30}},
    })
    # Also upsert a score so the vessel exists in vessel_scores (for 200 not 404)
    db.upsert_vessel_score(imo, {
        "composite_score": 72,
        "is_sanctioned": False,
        "indicator_json": {"IND7": {"pts": 30}},
    })

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get(f"/api/vessels/{imo}/history")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = resp.get_json()
    assert "history" in data, f"Response missing 'history' key: {data}"
    history = data["history"]
    assert len(history) >= 2, f"Expected at least 2 history rows, got {len(history)}"

    # history[0] = most recent (snap0): score 72, HIGH, IND7 fired
    snap0 = history[0]
    assert snap0["composite_score"] == 72, f"snap0 score should be 72, got {snap0['composite_score']}"
    assert snap0["risk_level"] == "HIGH", f"snap0 risk_level should be HIGH, got {snap0['risk_level']}"
    ind0 = snap0.get("indicator_json") or {}
    assert "IND7" in ind0, f"snap0 indicator_json should contain IND7, got {ind0}"

    # history[1] = prior (snap1): score 60, MEDIUM, IND3 fired
    snap1 = history[1]
    assert snap1["composite_score"] == 60, f"snap1 score should be 60, got {snap1['composite_score']}"
    assert snap1["risk_level"] == "MEDIUM", f"snap1 risk_level should be MEDIUM, got {snap1['risk_level']}"
    ind1 = snap1.get("indicator_json") or {}
    assert "IND3" in ind1, f"snap1 indicator_json should contain IND3, got {ind1}"

    # Verify the delta from JS perspective: snap0.composite_score - snap1.composite_score = +12
    delta = snap0["composite_score"] - snap1["composite_score"]
    assert delta == 12, f"Expected delta +12, got {delta}"

    # Verify IND7 is newly fired (in snap0 but not snap1) — JS change log logic
    assert "IND7" not in ind1, "IND7 should not be in snap1 (it's newly fired in snap0)"
    # Verify IND3 is newly cleared (in snap1 but not snap0) — JS change log logic
    assert "IND3" not in ind0, "IND3 should not be in snap0 (it was cleared)"


def test_change_log_identical_snapshots(app_client, monkeypatch):
    """PROF-02: Identical consecutive snapshots — both history rows have same score/risk/indicators."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()

    imo = "IMO0200004"
    db_path = db._sqlite_path()
    _flush_history(db_path, imo)

    # Insert two identical snapshots
    identical_score = {
        "composite_score": 50,
        "is_sanctioned": False,
        "indicator_json": {"IND5": {"pts": 15}},
    }
    db.append_score_history(imo, identical_score)
    db.append_score_history(imo, identical_score)
    db.upsert_vessel_score(imo, identical_score)

    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get(f"/api/vessels/{imo}/history")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = resp.get_json()
    history = data["history"]
    assert len(history) >= 2, f"Expected at least 2 history rows, got {len(history)}"

    snap0 = history[0]
    snap1 = history[1]

    # Both snapshots must be identical in score, risk level, and indicators
    assert snap0["composite_score"] == snap1["composite_score"], (
        f"Identical snapshots should have same composite_score: {snap0['composite_score']} vs {snap1['composite_score']}"
    )
    assert snap0["risk_level"] == snap1["risk_level"], (
        f"Identical snapshots should have same risk_level: {snap0['risk_level']} vs {snap1['risk_level']}"
    )
    ind0_keys = sorted((snap0.get("indicator_json") or {}).keys())
    ind1_keys = sorted((snap1.get("indicator_json") or {}).keys())
    assert ind0_keys == ind1_keys, (
        f"Identical snapshots should have same indicator keys: {ind0_keys} vs {ind1_keys}"
    )

    # Verify the JS "no changes" condition holds: delta==0, same risk, same indicator keys
    delta = snap0["composite_score"] - snap1["composite_score"]
    assert delta == 0, f"Identical snapshots should have delta=0, got {delta}"
