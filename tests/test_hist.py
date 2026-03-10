# tests/test_hist.py
"""
Phase 6: Score History Infrastructure — acceptance tests.
Requirements: HIST-01, HIST-02

Stubs written in Wave 0 (Plan 6-00). Made to pass in Wave 1 (Plan 6-01).

IMO range: IMO8000001+ (no collision with Phases 2-5).
"""
import os
import pytest

os.environ["DATABASE_URL"] = ""  # Force SQLite; must precede any db import


# ── HIST-01: history row is written when score changes ────────────────────────

def test_history_row_written(monkeypatch):
    """HIST-01: A history row is written when composite_score or is_sanctioned changes."""
    pytest.fail("stub")


def test_no_spurious_row(monkeypatch):
    """HIST-01: No history row is written when the score is identical to the last snapshot."""
    pytest.fail("stub")


# ── HIST-02: /api/vessels/<imo>/history endpoint ──────────────────────────────

def test_history_endpoint(app_client):
    """HIST-02: GET /api/vessels/<imo>/history returns up to 30 rows, newest first."""
    pytest.fail("stub")


def test_history_endpoint_404(app_client):
    """HIST-02: GET /api/vessels/<imo>/history returns 404 for unrecognized IMO."""
    pytest.fail("stub")
