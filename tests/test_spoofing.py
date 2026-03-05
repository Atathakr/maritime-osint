"""
Boundary tests for spoofing.detect() — T26 through T29.
Default coordinates in make_consecutive_pair() yield ~157 kt over 60 min (above threshold).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import risk_config
import spoofing
from ais_factory import make_consecutive_pair

THRESHOLD = risk_config.SPEED_ANOMALY_THRESHOLD_KT  # 50.0 kt


def test_detect_empty():
    """T26: detect([]) returns []."""
    assert spoofing.detect([]) == []


def test_below_threshold_not_anomaly():
    """
    T27: Pair at implied speed below threshold is NOT flagged.
    ~0.1 degree lat change in 60 min ≈ 11 km ≈ 9 kt — well below 50 kt.
    """
    pair = make_consecutive_pair(
        lat=22.5, lon=57.0,
        next_lat=22.6, next_lon=57.0,   # ~11 km north
        time_delta_min=60.0,
    )
    result = spoofing.detect([pair], threshold_kt=THRESHOLD)
    assert result == [], (
        f"Implied speed of ~9 kt should be below threshold {THRESHOLD} kt"
    )


def test_above_threshold_is_anomaly():
    """
    T28: Pair at implied speed above threshold IS flagged.
    Default make_consecutive_pair(): next_lat=22.6, next_lon=58.5 in 60 min ≈ 157 kt.
    """
    pair = make_consecutive_pair()  # default: ~157 kt
    result = spoofing.detect([pair], threshold_kt=THRESHOLD)
    assert len(result) == 1, (
        f"Implied speed ~157 kt should exceed threshold {THRESHOLD} kt"
    )


def test_zero_time_delta_ignored():
    """T29: Pair with time_delta_min=0 must NOT be flagged (guard clause)."""
    pair = make_consecutive_pair(
        next_lat=25.0, next_lon=60.0,   # far away
        time_delta_min=0.0,              # zero time = undefined speed
    )
    result = spoofing.detect([pair], threshold_kt=THRESHOLD)
    assert result == [], "time_delta_min=0 should be skipped (division-by-zero guard)"
