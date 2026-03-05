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
    """T09: Gap at DARK_THRESHOLD_HOURS + epsilon must be detected as MEDIUM."""
    gap = make_gap(gap_hours=dark_periods.DARK_THRESHOLD_HOURS + EPSILON)
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
