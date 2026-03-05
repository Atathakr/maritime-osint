"""
Boundary tests for loitering.detect() — T20 through T25.
All fixture values reference loitering module constants + delta.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import loitering
from ais_factory import make_position_sequence

# Positions at 30-min intervals: N positions = (N-1) * 0.5 hours duration
# To hit MIN_LOITER_HOURS=12.0: need 25 positions at 30-min intervals (24 * 0.5 = 12.0h)
# Below threshold: 23 positions (22 * 0.5 = 11.0h)
# Above threshold: 27 positions (26 * 0.5 = 13.0h)


def test_detect_empty():
    """T20: detect([]) returns []."""
    assert loitering.detect([]) == []


def test_episode_below_threshold():
    """T21: Episode duration below MIN_LOITER_HOURS must NOT be recorded."""
    # 23 positions at 30-min intervals = 22 * 0.5h = 11.0h < MIN_LOITER_HOURS (12.0)
    positions = make_position_sequence(count=23, sog=loitering.SOG_THRESHOLD_KT - 0.5,
                                       interval_minutes=30)
    result = loitering.detect(positions, sog_threshold_kt=loitering.SOG_THRESHOLD_KT,
                              min_hours=loitering.MIN_LOITER_HOURS)
    assert result == [], (
        f"Episode of 11.0h should not meet MIN_LOITER_HOURS={loitering.MIN_LOITER_HOURS}"
    )


def test_episode_at_threshold():
    """T22: Episode at MIN_LOITER_HOURS + buffer must be recorded as MEDIUM."""
    # 27 positions at 30-min intervals = 26 * 0.5h = 13.0h > MIN_LOITER_HOURS (12.0)
    positions = make_position_sequence(count=27, sog=loitering.SOG_THRESHOLD_KT - 0.5,
                                       interval_minutes=30)
    result = loitering.detect(positions, sog_threshold_kt=loitering.SOG_THRESHOLD_KT,
                              min_hours=loitering.MIN_LOITER_HOURS)
    assert len(result) >= 1, (
        f"Episode of 13.0h should meet MIN_LOITER_HOURS={loitering.MIN_LOITER_HOURS}"
    )
    assert result[0]["risk_level"] in ("MEDIUM", "HIGH", "CRITICAL")


def test_critical_loiter():
    """T23: Episode >= 48h is classified as CRITICAL."""
    # 49h = 98 positions at 30-min intervals
    positions = make_position_sequence(count=98, sog=0.5, interval_minutes=30)
    result = loitering.detect(positions, sog_threshold_kt=loitering.SOG_THRESHOLD_KT,
                              min_hours=loitering.MIN_LOITER_HOURS)
    assert len(result) >= 1
    assert result[0]["risk_level"] == "CRITICAL", (
        f"48h+ episode should be CRITICAL, got {result[0]['risk_level']}"
    )


def test_gap_breaks_episode():
    """T24: A >6h gap in position timestamps breaks one sequence into two episodes."""
    from datetime import datetime, timezone, timedelta
    # First batch: 27 positions (13h) — should form one episode
    seq1 = make_position_sequence(count=27, sog=0.5, interval_minutes=30)
    # Second batch: 27 positions starting >6h after seq1 ends — second episode
    last_ts = datetime.fromisoformat(seq1[-1]["position_ts"])
    gap_start = last_ts + timedelta(hours=7)  # > 6h gap breaks continuity
    seq2 = make_position_sequence(count=27, sog=0.5, interval_minutes=30)
    # Shift seq2 timestamps to start after the gap
    delta = gap_start - datetime.fromisoformat(seq2[0]["position_ts"])
    for row in seq2:
        ts = datetime.fromisoformat(row["position_ts"]) + delta
        row["position_ts"] = ts.isoformat()
    positions = seq1 + seq2
    result = loitering.detect(positions, sog_threshold_kt=loitering.SOG_THRESHOLD_KT,
                              min_hours=loitering.MIN_LOITER_HOURS)
    assert len(result) == 2, (
        f"6h+ gap should produce 2 episodes, got {len(result)}"
    )


def test_zone_triggers_high():
    """T25: Episode >= MIN_LOITER_HOURS inside high-risk zone is classified HIGH."""
    # Gulf of Oman coordinates
    positions = make_position_sequence(count=27, sog=0.5, interval_minutes=30,
                                       lat=22.5, lon=57.0)
    result = loitering.detect(positions, sog_threshold_kt=loitering.SOG_THRESHOLD_KT,
                              min_hours=loitering.MIN_LOITER_HOURS)
    assert len(result) >= 1
    assert result[0]["risk_level"] in ("HIGH", "CRITICAL"), (
        f"Episode in high-risk zone should be HIGH or CRITICAL, got {result[0]['risk_level']}"
    )
