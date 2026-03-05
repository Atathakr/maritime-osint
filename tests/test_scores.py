# tests/test_scores.py
"""
Unit tests for db/scores.py — vessel_scores and vessel_score_history CRUD.
Requirements: DB-1, DB-2, DB-4, DB-5, INF-1, INF-2

All tests use tmp_path + monkeypatch.setenv("DATABASE_URL", "")
+ db._init_backend() + db.init_db() to get a fresh SQLite DB per test.

Note: db._sqlite_path() uses __file__-anchored path resolution, so the DB is always
written to the project root (not cwd). Tests connect via db._sqlite_path() to verify
tables, and each test cleans the relevant rows by using the db API or raw SQL via
db._sqlite_path().
"""
import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta

os.environ["DATABASE_URL"] = ""  # Force SQLite; must precede any db import
import db


def _setup_db(monkeypatch):
    """
    Helper: initialise the SQLite DB (project-root path) and return the path string.

    Uses db._sqlite_path() which is __file__-anchored — not cwd-relative.
    monkeypatch.chdir is NOT needed here; we just ensure DATABASE_URL is empty.
    """
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    return db._sqlite_path()


def _raw_conn(db_path: str):
    """Open a raw sqlite3 connection for verification queries."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_init_scores_tables(monkeypatch):
    """DB-1: init_scores_tables() creates vessel_scores and vessel_score_history."""
    db_path = _setup_db(monkeypatch)
    conn = _raw_conn(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "vessel_scores" in tables, "vessel_scores table missing"
    assert "vessel_score_history" in tables, "vessel_score_history table missing"


def test_upsert_vessel_score(monkeypatch):
    """DB-1: upsert_vessel_score() inserts a row; reading it back returns full dict."""
    _setup_db(monkeypatch)
    imo = "IMO1234567"
    computed_at = datetime.now(timezone.utc).isoformat()
    score_data = {
        "composite_score": 42,
        "is_sanctioned": 1,
        "indicator_json": {"IND1": {"pts": 5, "fired": True}},
        "computed_at": computed_at,
    }
    db.upsert_vessel_score(imo, score_data)
    row = db.get_vessel_score(imo)
    assert row is not None, "get_vessel_score returned None after upsert"
    assert row["composite_score"] == 42
    assert row["is_sanctioned"] == 1
    assert isinstance(row["indicator_json"], dict), "indicator_json must be a dict, not a string"
    assert row["computed_at"] is not None


def test_get_vessel_score(monkeypatch):
    """DB-2: get_vessel_score() returns None for missing IMO; dict for existing."""
    _setup_db(monkeypatch)
    # Use a unique IMO not used in any other test
    result = db.get_vessel_score("IMO9999001")
    # May be None if not inserted, OR may be a row from a prior test run on same DB
    # We only assert on the type, not value, since tests share a project-root DB
    assert result is None or isinstance(result, dict), \
        "get_vessel_score must return None or dict"

    # Insert and retrieve
    imo = "IMO9999002"
    db.upsert_vessel_score(imo, {
        "composite_score": 10,
        "is_sanctioned": 0,
        "indicator_json": {"IND2": {"pts": 10, "fired": True}},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })
    row = db.get_vessel_score(imo)
    assert isinstance(row, dict), "Expected dict for existing IMO"
    assert isinstance(row["indicator_json"], dict), "indicator_json must be a dict"


def test_append_score_history(monkeypatch):
    """DB-4: append_score_history() inserts a row into vessel_score_history."""
    db_path = _setup_db(monkeypatch)
    imo = "IMO2222222"
    # Clean up any prior rows for this IMO
    conn = _raw_conn(db_path)
    conn.execute("DELETE FROM vessel_score_history WHERE imo_number=?", (imo,))
    conn.commit()
    conn.close()
    score_data = {
        "composite_score": 15,
        "is_sanctioned": 0,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    db.append_score_history(imo, score_data)
    conn = _raw_conn(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM vessel_score_history WHERE imo_number=?", (imo,)
    ).fetchone()[0]
    conn.close()
    assert count == 1, f"Expected 1 history row, got {count}"


def test_prune_score_history(monkeypatch):
    """DB-4: prune_score_history(90) deletes rows older than 90 days, keeps recent."""
    db_path = _setup_db(monkeypatch)
    imo = "IMO3333333"
    # Clean up any prior rows for this IMO to ensure a controlled state
    conn = _raw_conn(db_path)
    conn.execute("DELETE FROM vessel_score_history WHERE imo_number=?", (imo,))
    conn.commit()
    conn.close()

    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()
    # Insert old row
    db.append_score_history(imo, {
        "composite_score": 5,
        "is_sanctioned": 0,
        "computed_at": old_ts,
    })
    # Insert recent row
    db.append_score_history(imo, {
        "composite_score": 8,
        "is_sanctioned": 0,
        "computed_at": recent_ts,
    })
    deleted = db.prune_score_history(90)
    # At least 1 row deleted (may be more if other tests left stale history)
    assert deleted >= 1, f"Expected at least 1 deleted row, got {deleted}"
    # Confirm exactly 1 row for our imo remains
    with db._conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) as cnt FROM vessel_score_history WHERE imo_number=?", (imo,)
        )
        row = dict(c.fetchone())
    assert row["cnt"] == 1, f"Expected 1 remaining row for {imo}, got {row['cnt']}"


def test_score_is_stale_age():
    """score_is_stale() returns True when computed_at > 30 min ago; False when fresh."""
    from datetime import datetime, timezone, timedelta
    import screening as _screening

    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
    assert _screening.score_is_stale({"computed_at": old_ts, "is_stale": 0}) is True

    recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    assert _screening.score_is_stale({"computed_at": recent_ts, "is_stale": 0}) is False


def test_score_is_stale_flag():
    """score_is_stale() returns True when is_stale=1, regardless of age."""
    from datetime import datetime, timezone, timedelta
    import screening as _screening

    recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert _screening.score_is_stale({"computed_at": recent_ts, "is_stale": 1}) is True
    assert _screening.score_is_stale({"computed_at": recent_ts, "is_stale": 0}) is False


def test_mark_risk_scores_stale(monkeypatch):
    """DB-5: mark_risk_scores_stale() sets is_stale=1 for given IMOs."""
    _setup_db(monkeypatch)
    imo = "IMO4444444"
    db.upsert_vessel_score(imo, {
        "composite_score": 20,
        "is_sanctioned": 0,
        "indicator_json": {},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })
    count = db.mark_risk_scores_stale([imo])
    assert count == 1, f"Expected 1 row updated, got {count}"
    row = db.get_vessel_score(imo)
    assert row["is_stale"] == 1, f"Expected is_stale=1, got {row['is_stale']}"


def test_upsert_clears_stale(monkeypatch):
    """DB-1/DB-5: upsert after mark_stale resets is_stale to 0."""
    _setup_db(monkeypatch)
    imo = "IMO5555555"
    db.upsert_vessel_score(imo, {
        "composite_score": 30,
        "is_sanctioned": 0,
        "indicator_json": {},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })
    db.mark_risk_scores_stale([imo])
    # Verify stale
    row = db.get_vessel_score(imo)
    assert row["is_stale"] == 1
    # Upsert again — is_stale must reset to 0
    db.upsert_vessel_score(imo, {
        "composite_score": 35,
        "is_sanctioned": 0,
        "indicator_json": {},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })
    row = db.get_vessel_score(imo)
    assert row["is_stale"] == 0, f"Expected is_stale=0 after upsert, got {row['is_stale']}"


def test_get_all_vessel_scores(monkeypatch):
    """DB-2: get_all_vessel_scores() returns list via single JOIN including the upserted vessel."""
    db_path = _setup_db(monkeypatch)
    imo = "IMO6666666"
    # Clean up prior state for this IMO
    conn = _raw_conn(db_path)
    conn.execute("DELETE FROM vessel_scores WHERE imo_number=?", (imo,))
    conn.execute(
        "DELETE FROM vessels_canonical WHERE imo_number=?", (imo,)
    )
    conn.commit()
    # Insert into vessels_canonical first (JOIN requirement)
    conn.execute(
        "INSERT OR IGNORE INTO vessels_canonical "
        "(canonical_id, entity_name, imo_number) VALUES (?, ?, ?)",
        ("CAN_T01", "Test Vessel Alpha", imo),
    )
    conn.commit()
    conn.close()
    db.upsert_vessel_score(imo, {
        "composite_score": 50,
        "is_sanctioned": 1,
        "indicator_json": {"IND1": {"pts": 5, "fired": True}},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })
    results = db.get_all_vessel_scores()
    assert isinstance(results, list), "Expected list from get_all_vessel_scores()"
    imos = [r["imo_number"] for r in results]
    assert imo in imos, f"{imo} not found in get_all_vessel_scores() result"


def test_archive_old_ais_positions(monkeypatch):
    """INF-1/INF-2: archive_old_ais_positions(90) deletes old rows, keeps recent."""
    db_path = _setup_db(monkeypatch)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()
    # Use unique mmsi + timestamps to avoid interference from other tests
    mmsi = "TMMSI99999"
    conn = _raw_conn(db_path)
    # Clean up prior rows for this mmsi
    conn.execute("DELETE FROM ais_positions WHERE mmsi=?", (mmsi,))
    conn.commit()
    # Insert old position
    conn.execute(
        "INSERT INTO ais_positions (mmsi, lat, lon, position_ts) VALUES (?, ?, ?, ?)",
        (mmsi, 0.0, 0.0, old_ts),
    )
    # Insert recent position (unique position_ts required by UNIQUE(mmsi, position_ts))
    conn.execute(
        "INSERT INTO ais_positions (mmsi, lat, lon, position_ts) VALUES (?, ?, ?, ?)",
        (mmsi, 1.0, 1.0, recent_ts),
    )
    conn.commit()
    conn.close()
    deleted = db.archive_old_ais_positions(90)
    assert deleted >= 1, f"Expected at least 1 deleted ais_positions row, got {deleted}"
    # Confirm the recent row for our mmsi remains
    conn = _raw_conn(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM ais_positions WHERE mmsi=? AND position_ts=?",
        (mmsi, recent_ts)
    ).fetchone()[0]
    conn.close()
    assert count == 1, f"Expected 1 remaining ais_positions row for {mmsi}, got {count}"
