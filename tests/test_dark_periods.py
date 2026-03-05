"""
Boundary tests for dark_periods.detect() — T07 through T13.
All fixture values reference dark_periods module constants + EPSILON.
No assertions on sanctions_hit == True (pure function cannot call db).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import dark_periods
from ais_factory import make_gap

EPSILON = 0.01  # fractional hours — small enough to be below any threshold


def test_detect_empty():
    """T07: detect([]) returns []."""
    assert dark_periods.detect([]) == []


def test_medium_below_threshold():
    """T08: Gap at DARK_THRESHOLD_HOURS - epsilon must NOT be detected."""
    gap = make_gap(gap_hours=dark_periods.DARK_THRESHOLD_HOURS - EPSILON)
    result = dark_periods.detect([gap])
    assert result == [], (
        f"Gap of {gap['gap_hours']}h should not trigger at threshold "
        f"{dark_periods.DARK_THRESHOLD_HOURS}h"
    )


def test_medium_at_threshold():
    """T09: Gap at DARK_THRESHOLD_HOURS + epsilon must be detected as MEDIUM.
    Uses open-ocean coords (0.0, 0.0) which are outside all high-risk zones to
    ensure baseline MEDIUM is not upgraded by zone logic.
    """
    gap = make_gap(gap_hours=dark_periods.DARK_THRESHOLD_HOURS + EPSILON,
                   last_lat=0.0, last_lon=0.0)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["risk_level"] == "MEDIUM", (
        f"Expected MEDIUM for {gap['gap_hours']}h gap, got {result[0]['risk_level']}"
    )


def test_high_at_threshold():
    """T10: Gap at HIGH_RISK_HOURS + epsilon must be detected as HIGH."""
    gap = make_gap(gap_hours=dark_periods.HIGH_RISK_HOURS + EPSILON)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["risk_level"] == "HIGH", (
        f"Expected HIGH for {gap['gap_hours']}h gap, got {result[0]['risk_level']}"
    )


def test_critical_at_threshold():
    """T11: Gap at CRITICAL_HOURS + epsilon must be detected as CRITICAL."""
    gap = make_gap(gap_hours=dark_periods.CRITICAL_HOURS + EPSILON)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["risk_level"] == "CRITICAL", (
        f"Expected CRITICAL for {gap['gap_hours']}h gap, got {result[0]['risk_level']}"
    )


def test_zone_upgrade_medium_to_high():
    """
    T12: A MEDIUM gap (3.0h) with coords inside a high-risk zone must be upgraded to HIGH.
    Gulf of Oman coordinates: lat ~22.5, lon ~57.0.
    """
    # 3.0h is above DARK_THRESHOLD_HOURS (2.0) but below HIGH_RISK_HOURS (6.0) -> MEDIUM baseline
    gap = make_gap(gap_hours=3.0, last_lat=22.5, last_lon=57.0)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    risk = result[0]["risk_level"]
    # Zone upgrade: MEDIUM in high-risk zone should become HIGH
    assert risk in ("HIGH", "CRITICAL"), (
        f"Expected zone upgrade to HIGH or CRITICAL for Gulf of Oman coords, got {risk}"
    )


def test_detect_no_db():
    """T13: detect() returns sanctions_hit=False — no db call possible in pure function."""
    gap = make_gap(gap_hours=dark_periods.HIGH_RISK_HOURS + EPSILON)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0].get("sanctions_hit") is False, (
        "Pure detect() must return sanctions_hit=False; db lookup not possible"
    )


def test_detect_with_reappear_coords():
    """Extra: detect() with reappear coords computes distance_km via haversine."""
    gap = make_gap(
        gap_hours=dark_periods.HIGH_RISK_HOURS + EPSILON,
        last_lat=0.0, last_lon=0.0,
        reappear_lat=0.1, reappear_lon=0.1,
    )
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["distance_km"] is not None
    assert result[0]["distance_km"] > 0


def test_detect_outside_zone_no_upgrade():
    """Extra: MEDIUM gap with coords outside all zones stays MEDIUM."""
    gap = make_gap(gap_hours=3.0, last_lat=0.0, last_lon=0.0)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["risk_level"] == "MEDIUM"
    assert result[0]["risk_zone"] is None


def test_detect_none_coords_no_zone():
    """Extra: gap with last_lat=None has risk_zone=None and distance_km=None."""
    gap = make_gap(gap_hours=dark_periods.HIGH_RISK_HOURS + EPSILON,
                   last_lat=None, last_lon=None)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["risk_zone"] is None
    assert result[0]["distance_km"] is None


def test_summarise_empty():
    """Extra: summarise([]) returns zero counts."""
    summary = dark_periods.summarise([])
    assert summary["total"] == 0


def test_summarise_nonempty():
    """Extra: summarise returns correct counts for a list of periods."""
    periods = [
        {"risk_level": "MEDIUM", "sanctions_hit": False, "risk_zone": None},
        {"risk_level": "HIGH", "sanctions_hit": True, "risk_zone": "Gulf of Oman"},
        {"risk_level": "CRITICAL", "sanctions_hit": False, "risk_zone": "Gulf of Oman"},
    ]
    s = dark_periods.summarise(periods)
    assert s["total"] == 3
    assert s["medium"] == 1
    assert s["high"] == 1
    assert s["critical"] == 1
    assert s["with_sanctions"] == 1
    assert s["in_risk_zone"] == 2


# ── Extra coverage tests for _classify_zone() and _haversine() ────────────

def test_classify_zone_none_returns_none():
    """_classify_zone with None coord returns None (line 205)."""
    result = dark_periods._classify_zone(None, 57.0)
    assert result is None


def test_classify_zone_open_ocean():
    """_classify_zone with open-ocean coords returns None (line 209)."""
    result = dark_periods._classify_zone(0.0, 0.0)
    assert result is None


def test_classify_zone_gulf_of_oman():
    """_classify_zone with Gulf of Oman coords returns zone name."""
    result = dark_periods._classify_zone(22.5, 57.0)
    assert result == "Gulf of Oman"


def test_haversine_none_returns_none():
    """_haversine with None coordinate returns None (line 215)."""
    result = dark_periods._haversine(None, 57.0, 22.6, 58.5)
    assert result is None


def test_haversine_valid_coords():
    """_haversine returns positive float for valid coordinates."""
    result = dark_periods._haversine(22.5, 57.0, 22.6, 57.0)
    assert result is not None
    assert result > 0
