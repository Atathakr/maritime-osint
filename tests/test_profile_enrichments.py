# tests/test_profile_enrichments.py
"""
Phase 8: Vessel Profile Enrichments — acceptance tests.
Requirements: PROF-01, PROF-02

Stubs written in Wave 0 (Plan 08-00). Made to pass in Wave 1 (Plan 08-01).

IMO range: IMO0200001+ (no collision with Phases 2-7).
"""
import os
import pytest


def test_profile_has_history_card(app_client):
    """PROF-01: /vessel/<imo> HTML contains #score-history-card and Chart.js CDN script tag."""
    pytest.fail("stub")


def test_history_single_snapshot(app_client):
    """PROF-01: /api/vessels/<imo>/history with exactly 1 row returns valid JSON (not an error)."""
    pytest.fail("stub")


def test_change_log_diff(app_client):
    """PROF-02: Given 2 snapshots with score delta and indicator changes, change log returns expected delta/fired/cleared."""
    pytest.fail("stub")


def test_change_log_identical_snapshots(app_client):
    """PROF-02: Identical consecutive snapshots produce the 'no changes since last run' signal."""
    pytest.fail("stub")
