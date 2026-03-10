"""
tests/test_fe.py — Phase 5 Frontend UX test stubs (Wave 0 / RED phase).

All tests use pytest.fail() so the suite exits with code 1 (FAILED)
not code 2 (ERROR). This is the Wave 0 RED state per 05-VALIDATION.md.
"""
import pytest


def test_ranking_sort(app_client):
    """FE-1: /api/vessels/ranking returns vessels sorted by composite_score desc."""
    pytest.fail("stub — implement in plan 05-02")


def test_map_data_score(app_client):
    """FE-2: Map data dict includes composite_score field (not None by default)."""
    pytest.fail("stub — implement in plan 05-02")


def test_stale_flag(app_client):
    """FE-3: is_stale flag propagates correctly in ranking API response."""
    pytest.fail("stub — implement in plan 05-02")


def test_indicator_json(app_client):
    """FE-4: indicator_json present in /api/vessels/ranking response."""
    pytest.fail("stub — implement in plan 05-03")


def test_vessel_permalink(app_client):
    """FE-5: GET /vessel/<imo> returns 200 (or 404 for unknown) with HTML."""
    pytest.fail("stub — implement in plan 05-01")


def test_csv_export(app_client):
    """FE-6: GET /export/vessels.csv returns text/csv with correct column headers."""
    pytest.fail("stub — implement in plan 05-03")
