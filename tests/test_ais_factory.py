"""T03-T06: Self-tests for ais_factory.py shape correctness."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from ais_factory import make_gap, make_position_sequence, make_sts_pair, make_consecutive_pair

GAP_REQUIRED_KEYS = {"mmsi", "imo_number", "vessel_name", "gap_start", "gap_end",
                     "gap_hours", "last_lat", "last_lon", "reappear_lat", "reappear_lon"}
POSITION_REQUIRED_KEYS = {"mmsi", "imo_number", "vessel_name", "lat", "lon", "sog", "position_ts"}
STS_REQUIRED_KEYS = {"mmsi1", "mmsi2", "vessel_name1", "vessel_name2",
                     "lat1", "lon1", "lat2", "lon2", "sog1", "sog2", "ts"}


def test_make_gap_keys():
    """T03: make_gap() returns dict with all required dark_periods input keys."""
    gap = make_gap()
    assert GAP_REQUIRED_KEYS.issubset(gap.keys()), \
        f"Missing keys: {GAP_REQUIRED_KEYS - gap.keys()}"


def test_make_sequence_count():
    """T04: make_position_sequence(count=5) returns exactly 5 dicts."""
    seq = make_position_sequence(count=5)
    assert len(seq) == 5
    for row in seq:
        assert POSITION_REQUIRED_KEYS.issubset(row.keys()), \
            f"Missing keys: {POSITION_REQUIRED_KEYS - row.keys()}"


def test_make_sts_pair_keys():
    """T05: make_sts_pair() returns dict with all required STS candidate keys."""
    pair = make_sts_pair()
    assert STS_REQUIRED_KEYS.issubset(pair.keys()), \
        f"Missing keys: {STS_REQUIRED_KEYS - pair.keys()}"


def test_make_consecutive_pair_keys():
    """T06: make_consecutive_pair() returns dict with time_delta_min."""
    pair = make_consecutive_pair()
    assert "time_delta_min" in pair, "time_delta_min key missing from consecutive pair"
    assert "next_lat" in pair and "next_lon" in pair, "next_lat/next_lon missing"
