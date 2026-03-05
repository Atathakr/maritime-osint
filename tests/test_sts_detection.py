"""
Boundary tests for sts_detection.detect() — T14 through T19.
All fixture values reference sts_detection module constants + EPSILON.
"""
import sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import sts_detection
from ais_factory import make_sts_pair

# Latitude delta that yields approximately STS_DISTANCE_KM at lat 22.5
# 1 degree latitude ≈ 111.32 km; STS_DISTANCE_KM = 0.926 km
# Delta for ~0.923 km (just inside): 0.0083 degrees * 111.32 km/deg ≈ 0.924 km
# Delta for ~1.001 km (just outside): 0.0090 degrees * 111.32 km/deg ≈ 1.001 km
INSIDE_DELTA  = 0.0083   # ~0.923 km — inside STS_DISTANCE_KM threshold
OUTSIDE_DELTA = 0.0090   # ~1.001 km — outside STS_DISTANCE_KM threshold


def test_detect_empty():
    """T14: detect([]) returns []."""
    assert sts_detection.detect([]) == []


def test_distance_above_threshold_not_detected():
    """T15: Pair where distance > STS_DISTANCE_KM is NOT detected."""
    pair = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + OUTSIDE_DELTA, lon2=57.0,
        sog1=0.5, sog2=0.5,
    )
    result = sts_detection.detect([pair])
    assert result == [], (
        f"Pair outside {sts_detection.STS_DISTANCE_KM}km threshold should not be detected"
    )


def test_distance_within_threshold_detected():
    """T16: Pair where distance <= STS_DISTANCE_KM IS detected."""
    pair = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + INSIDE_DELTA, lon2=57.0,
        sog1=0.5, sog2=0.5,
    )
    result = sts_detection.detect([pair])
    assert len(result) == 1, (
        f"Pair inside {sts_detection.STS_DISTANCE_KM}km threshold should be detected"
    )


def test_both_fast_not_detected():
    """T17: Pair where both vessels > MAX_SOG is NOT detected."""
    pair = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + INSIDE_DELTA, lon2=57.0,
        sog1=sts_detection.MAX_SOG + 0.1,
        sog2=sts_detection.MAX_SOG + 0.1,
    )
    result = sts_detection.detect([pair])
    assert result == [], (
        f"Both vessels at SOG {sts_detection.MAX_SOG + 0.1} should not be STS candidates"
    )


def test_one_slow_detected():
    """T18: Pair where sog1 <= MAX_SOG qualifies as STS (sog2 may be above)."""
    pair = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + INSIDE_DELTA, lon2=57.0,
        sog1=sts_detection.MAX_SOG - 0.1,   # slow vessel
        sog2=sts_detection.MAX_SOG + 1.0,   # fast vessel — should still count
    )
    result = sts_detection.detect([pair])
    assert len(result) == 1, (
        f"One slow vessel (sog1={sts_detection.MAX_SOG - 0.1}) should be STS candidate"
    )


def test_deduplication():
    """T19: Two identical pairs within DEDUP_HOURS are deduplicated to 1 event."""
    base_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pair1 = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + INSIDE_DELTA, lon2=57.0,
        sog1=0.5, sog2=0.5,
        ts=base_ts.isoformat(),
    )
    # Same pair, 1 hour later — within DEDUP_HOURS (2.0)
    pair2 = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + INSIDE_DELTA, lon2=57.0,
        sog1=0.5, sog2=0.5,
        ts=(base_ts + timedelta(hours=1)).isoformat(),
    )
    result = sts_detection.detect([pair1, pair2])
    assert len(result) == 1, (
        f"Two identical pairs within {sts_detection.DEDUP_HOURS}h should deduplicate to 1"
    )


def test_detect_result_fields():
    """Extra: detected pair has required output fields."""
    pair = make_sts_pair(
        lat1=22.5, lon1=57.0,
        lat2=22.5 + INSIDE_DELTA, lon2=57.0,
        sog1=0.5, sog2=0.5,
    )
    result = sts_detection.detect([pair])
    assert len(result) == 1
    ev = result[0]
    assert "distance_km" in ev
    assert "risk_level" in ev
    assert "risk_zone" in ev
    assert ev["sanctions_hit"] is False


def test_no_zone_outside_region():
    """Extra: pair in open ocean (lat=0, lon=0) has risk_zone=None."""
    pair = make_sts_pair(
        lat1=0.0, lon1=0.0,
        lat2=0.0 + INSIDE_DELTA, lon2=0.0,
        sog1=0.5, sog2=0.5,
    )
    result = sts_detection.detect([pair])
    assert len(result) == 1
    assert result[0]["risk_zone"] is None


def test_detect_pair_outside_dedup_window():
    """Extra: Two identical pairs OUTSIDE DEDUP_HOURS produce 2 events."""
    base_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pair1 = make_sts_pair(
        lat1=0.0, lon1=0.0,
        lat2=0.0 + INSIDE_DELTA, lon2=0.0,
        sog1=0.5, sog2=0.5,
        ts=base_ts.isoformat(),
    )
    # Same pair, 3 hours later — outside DEDUP_HOURS (2.0)
    pair2 = make_sts_pair(
        lat1=0.0, lon1=0.0,
        lat2=0.0 + INSIDE_DELTA, lon2=0.0,
        sog1=0.5, sog2=0.5,
        ts=(base_ts + timedelta(hours=3)).isoformat(),
    )
    result = sts_detection.detect([pair1, pair2])
    assert len(result) == 2, (
        f"Pairs outside {sts_detection.DEDUP_HOURS}h window should NOT deduplicate"
    )


def test_summarise_empty():
    """Extra: summarise([]) returns zero counts."""
    counts = sts_detection.summarise([])
    assert counts == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}


def test_summarise_nonempty():
    """Extra: summarise counts risk levels correctly."""
    events = [
        {"risk_level": "CRITICAL"},
        {"risk_level": "HIGH"},
        {"risk_level": "LOW"},
    ]
    counts = sts_detection.summarise(events)
    assert counts["CRITICAL"] == 1
    assert counts["HIGH"] == 1
    assert counts["LOW"] == 1
    assert counts["MEDIUM"] == 0
