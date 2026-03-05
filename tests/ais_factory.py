"""
tests/ais_factory.py — Synthetic AIS position sequence generators.

Plain functions (not pytest fixtures) so tests can call them with custom parameters.
Each function returns the exact dict shape consumed by the corresponding detection module.

Data shapes sourced from 03-RESEARCH.md and confirmed against source code:
- make_gap():              dark_periods.detect() input (gap rows from db.find_ais_gaps)
- make_position_sequence(): loitering.detect() input (low-speed positions)
- make_sts_pair():          sts_detection.detect() input (candidate pairs)
- make_consecutive_pair():  spoofing.detect() input (consecutive AIS pairs)
"""
from datetime import datetime, timezone, timedelta

BASE_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_gap(
    mmsi="123456789",
    gap_hours=3.0,
    last_lat=22.5,
    last_lon=57.0,
    reappear_lat=None,
    reappear_lon=None,
    imo_number=None,
    vessel_name="TEST VESSEL",
) -> dict:
    """Build a single AIS gap dict for dark_periods.detect() input."""
    start = BASE_TS
    end = start + timedelta(hours=gap_hours)
    return {
        "mmsi": mmsi,
        "imo_number": imo_number,
        "vessel_name": vessel_name,
        "gap_start": start.isoformat(),
        "gap_end": end.isoformat(),
        "gap_hours": gap_hours,
        "last_lat": last_lat,
        "last_lon": last_lon,
        "reappear_lat": reappear_lat,
        "reappear_lon": reappear_lon,
    }


def make_position_sequence(
    mmsi="123456789",
    count=10,
    sog=1.5,
    lat=22.5,
    lon=57.0,
    interval_minutes=30,
    imo_number=None,
    vessel_name="TEST VESSEL",
) -> list:
    """
    Build a sequence of AIS position rows for loitering.detect() input.
    Rows are sorted ascending by position_ts (matches _get_low_speed_positions() output).
    """
    rows = []
    ts = BASE_TS
    for _ in range(count):
        rows.append({
            "mmsi": mmsi,
            "imo_number": imo_number,
            "vessel_name": vessel_name,
            "lat": lat,
            "lon": lon,
            "sog": sog,
            "position_ts": ts.isoformat(),
        })
        ts += timedelta(minutes=interval_minutes)
    return rows


def make_sts_pair(
    mmsi1="123456789",
    mmsi2="987654321",
    lat1=22.5,
    lon1=57.0,
    lat2=22.501,
    lon2=57.001,
    sog1=0.5,
    sog2=2.8,
    ts=None,
) -> dict:
    """Build a single STS candidate pair for sts_detection.detect() input."""
    if ts is None:
        ts = BASE_TS.isoformat()
    return {
        "mmsi1": mmsi1,
        "mmsi2": mmsi2,
        "vessel_name1": "VESSEL A",
        "vessel_name2": "VESSEL B",
        "lat1": lat1,
        "lon1": lon1,
        "lat2": lat2,
        "lon2": lon2,
        "sog1": sog1,
        "sog2": sog2,
        "ts": ts,
    }


def make_consecutive_pair(
    mmsi="123456789",
    lat=22.5,
    lon=57.0,
    next_lat=22.6,
    next_lon=58.5,
    time_delta_min=60.0,
    imo_number=None,
    vessel_name="TEST VESSEL",
) -> dict:
    """
    Build a consecutive AIS position pair for spoofing.detect() input.
    Default next_lat/next_lon are ~157 km from lat/lon at time_delta_min=60,
    giving an implied speed of ~157 kt — well above SPEED_ANOMALY_THRESHOLD_KT=50.
    """
    ts = BASE_TS + timedelta(minutes=time_delta_min)
    return {
        "mmsi": mmsi,
        "imo_number": imo_number,
        "vessel_name": vessel_name,
        "lat": lat,
        "lon": lon,
        "next_lat": next_lat,
        "next_lon": next_lon,
        "next_ts": ts.isoformat(),
        "time_delta_min": time_delta_min,
    }
