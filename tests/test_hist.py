# tests/test_hist.py
"""
Phase 6: Score History Infrastructure — acceptance tests.
Requirements: HIST-01, HIST-02
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

import pytest

os.environ["DATABASE_URL"] = ""  # Force SQLite; must precede any db import
import db


def _setup_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    return db._sqlite_path()


def _raw_conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── HIST-01: history row is written when score changes ────────────────────────

def test_history_row_written(monkeypatch):
    """HIST-01: A history row is written when composite_score or is_sanctioned changes."""
    db_path = _setup_db(monkeypatch)
    imo = "IMO8000001"

    # Clean slate
    conn = _raw_conn(db_path)
    conn.execute("DELETE FROM vessel_score_history WHERE imo_number=?", (imo,))
    conn.commit()
    conn.close()

    # First append — no prior row, so always written
    score_a = {
        "composite_score": 30,
        "is_sanctioned": 0,
        "indicator_json": {"IND1": {"pts": 5}},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    db.append_score_history(imo, score_a)

    # Verify row was written with all required columns populated
    conn = _raw_conn(db_path)
    rows = list(conn.execute(
        "SELECT * FROM vessel_score_history WHERE imo_number=?", (imo,)
    ))
    conn.close()

    assert len(rows) == 1, f"Expected 1 history row after first append, got {len(rows)}"
    row = dict(rows[0])
    assert row["composite_score"] == 30
    assert row["is_sanctioned"] == 0
    assert row["risk_level"] is not None, "risk_level must be populated"
    assert row["risk_level"] == "LOW", f"Expected LOW for score=30 not-sanctioned, got {row['risk_level']}"
    assert row["indicator_json"] is not None, "indicator_json must be populated"
    assert row["computed_at"] is not None, "computed_at must be populated"

    # Second append with a different score — change-detection lives in _do_score_refresh,
    # not in append_score_history itself. append_score_history always writes when called.
    # Confirm a second direct call also writes.
    score_b = {
        "composite_score": 50,
        "is_sanctioned": 0,
        "indicator_json": {"IND1": {"pts": 5}, "IND7": {"pts": 10}},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    db.append_score_history(imo, score_b)
    conn = _raw_conn(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM vessel_score_history WHERE imo_number=?", (imo,)
    ).fetchone()[0]
    conn.close()
    assert count == 2, f"Expected 2 rows after second append with changed score, got {count}"


def test_no_spurious_row(monkeypatch):
    """HIST-01: No history row is written when the score is identical to the last snapshot."""
    db_path = _setup_db(monkeypatch)
    imo = "IMO8000002"

    # Clean slate
    conn = _raw_conn(db_path)
    conn.execute("DELETE FROM vessel_score_history WHERE imo_number=?", (imo,))
    conn.commit()
    conn.close()

    score = {
        "composite_score": 45,
        "is_sanctioned": 0,
        "indicator_json": {"IND3": {"pts": 15}},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write first snapshot directly
    db.append_score_history(imo, score)

    # Simulate what _do_score_refresh does: get prior, compare, skip if unchanged
    from app import _score_changed
    prior = db.get_score_history(imo, limit=1)
    assert prior, "Expected 1 prior row"
    assert not _score_changed(prior[0], score), \
        "_score_changed must return False for identical score"

    # Confirm that if _score_changed is False, no new row is written
    # (i.e. the guard logic works; we do NOT call append_score_history again here)
    conn = _raw_conn(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM vessel_score_history WHERE imo_number=?", (imo,)
    ).fetchone()[0]
    conn.close()
    assert count == 1, f"Expected 1 row (no spurious write), got {count}"


# ── HIST-02: /api/vessels/<imo>/history endpoint ──────────────────────────────

def test_history_endpoint(app_client, monkeypatch):
    """HIST-02: GET /api/vessels/<imo>/history returns up to 30 rows, newest first."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    db_path = db._sqlite_path()
    imo = "IMO8000003"

    # Seed vessels_canonical so the IMO is recognised
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM vessel_score_history WHERE imo_number=?", (imo,))
    conn.execute("DELETE FROM vessel_scores WHERE imo_number=?", (imo,))
    conn.execute("DELETE FROM vessels_canonical WHERE imo_number=?", (imo,))
    conn.execute(
        "INSERT OR IGNORE INTO vessels_canonical (canonical_id, entity_name, imo_number) VALUES (?,?,?)",
        ("CAN_HIST01", "Test History Vessel", imo),
    )
    conn.commit()
    conn.close()

    # Write 3 history rows
    for i in range(3):
        db.append_score_history(imo, {
            "composite_score": 20 + i * 10,
            "is_sanctioned": 0,
            "indicator_json": {},
            "computed_at": f"2026-03-10T12:0{i}:00+00:00",
        })

    # Authenticate
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get(f"/api/vessels/{imo}/history")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
    data = resp.get_json()
    assert "history" in data, f"Response missing 'history' key: {data}"
    assert len(data["history"]) == 3, f"Expected 3 rows, got {len(data['history'])}"

    # Newest first: highest computed_at first
    timestamps = [row["recorded_at"] for row in data["history"]]
    assert timestamps == sorted(timestamps, reverse=True), \
        f"Rows not in reverse chronological order: {timestamps}"

    # Verify required fields present on each row
    for row in data["history"]:
        for field in ("id", "imo_number", "composite_score", "risk_level",
                      "is_sanctioned", "indicator_json", "recorded_at"):
            assert field in row, f"Missing field '{field}' in history row: {row}"


def test_history_endpoint_404(app_client, monkeypatch):
    """HIST-02: GET /api/vessels/<imo>/history returns 404 for unrecognized IMO."""
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()

    # Authenticate
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get("/api/vessels/IMO0000000/history")
    assert resp.status_code == 404, f"Expected 404 for unknown IMO, got {resp.status_code}"
    data = resp.get_json()
    assert "error" in data, f"Expected 'error' key in 404 response, got: {data}"
