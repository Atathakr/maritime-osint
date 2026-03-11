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
    pytest.fail("stub")


# ── ALRT-05: top-50 entry ─────────────────────────────────────────────────────

def test_top_50_entry_alert(monkeypatch):
    """ALRT-05: _do_score_refresh() inserts alert_type='top_50_entry' for vessels entering top 50."""
    pytest.fail("stub")


# ── ALRT-06: sanctions flip ──────────────────────────────────────────────────

def test_sanctions_flip_alert(monkeypatch):
    """ALRT-06: _generate_alerts() inserts alert_type='sanctions_match' when is_sanctioned flips False->True."""
    pytest.fail("stub")


# ── ALRT-07: score spike ─────────────────────────────────────────────────────

def test_score_spike_alert(monkeypatch):
    """ALRT-07: _generate_alerts() inserts alert_type='score_spike' when abs(delta) >= 15 pts."""
    pytest.fail("stub")


# ── ALRT-08: mark alert read ─────────────────────────────────────────────────

def test_mark_alert_read(app_client):
    """ALRT-08: POST /api/alerts/<id>/read sets is_read=1; GET /api/alerts/unread-count decrements."""
    pytest.fail("stub")
