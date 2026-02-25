import pytest
from unittest.mock import patch, MagicMock
import datetime
import spoof_detector
import db

@pytest.fixture
def mock_db():
    """Mock all db calls in run_detection to decouple from actual database."""
    with (
        patch("db.get_recent_positions") as m_recent,
        patch("db.find_teleport_candidates") as m_teleport,
        patch("db.find_imo_conflicts") as m_imo_conf,
        patch("db.find_identity_flips") as m_id_flips,
        patch("db.search_sanctions_by_mmsi") as m_sanc_mmsi,
        patch("db.search_sanctions_by_imo") as m_sanc_imo,
        patch("db.upsert_spoof_events") as m_upsert
    ):
        yield {
            "recent": m_recent,
            "teleport": m_teleport,
            "imo_conf": m_imo_conf,
            "id_flips": m_id_flips,
            "sanc_mmsi": m_sanc_mmsi,
            "sanc_imo": m_sanc_imo,
            "upsert": m_upsert
        }

def test_overland_detection_logic(mock_db):
    """Verify that run_detection correctly identifies OVERLAND events from positions."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Mock positions: one at sea, one on land
    mock_db["recent"].return_value = [
        {"mmsi": "111222333", "lat": 0.0, "lon": 0.0, "position_ts": now_iso, "vessel_name": "SEA_DOG"},
        {"mmsi": "222333444", "lat": 20.0, "lon": 20.0, "position_ts": now_iso, "vessel_name": "LAND_ROVER"}
    ]
    # No other events
    mock_db["teleport"].return_value = []
    mock_db["imo_conf"].return_value = []
    mock_db["id_flips"].return_value = []
    mock_db["sanc_mmsi"].return_value = []
    
    # Mock is_overland to return True for the land position
    with patch("spoof_detector.is_overland") as m_is_overland:
        m_is_overland.side_effect = lambda lat, lon: lat == 20.0 and lon == 20.0
        
        events = spoof_detector.run_detection()
        
        # Verify 1 event found
        assert len(events) == 1
        ev = events[0]
        assert ev["mmsi"] == "222333444"
        assert ev["spoof_type"] == "OVERLAND"
        assert ev["risk_level"] == "CRITICAL"
        
        # Verify it was persisted
        mock_db["upsert"].assert_called_once()
        persisted_list = mock_db["upsert"].call_args[0][0]
        assert len(persisted_list) == 1
        assert persisted_list[0]["mmsi"] == "222333444"

def test_full_suite_integration(mock_db):
    """Verify TELEPORT, ID_MISMATCH and OVERLAND work together."""
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()
    prev_iso = (now - datetime.timedelta(hours=1)).isoformat()
    
    # 1. TELEPORT candidate (Speed > 30 kts)
    # 0,0 to 1,1 in 1 hour is ~157km, which is ~85 knots
    mock_db["teleport"].return_value = [{
        "mmsi": "333444555", "lat": 0.0, "lon": 0.0, "position_ts": prev_iso,
        "next_lat": 1.0, "next_lon": 1.0, "next_ts": now_iso,
        "vessel_name": "SPEEDY", "imo_number": "9123456"
    }]
    
    # 2. ID_MISMATCH (IMO conflict)
    mock_db["imo_conf"].return_value = [{
        "imo_number": "8123456", "mmsis": "444555666, 555666777", "mmsi_count": 2,
        "last_seen": now_iso, "lat": 5.0, "lon": 5.0, "vessel_name": "CLONE"
    }]
    
    # 3. OVERLAND
    mock_db["recent"].return_value = [
        {"mmsi": "222333444", "lat": 20.0, "lon": 20.0, "position_ts": now_iso, "vessel_name": "LAND_ROVER"}
    ]
    
    mock_db["id_flips"].return_value = []
    mock_db["sanc_mmsi"].return_value = []
    mock_db["sanc_imo"].return_value = []

    with patch("spoof_detector.is_overland") as m_is_overland:
        m_is_overland.return_value = True # All recent positions considered on land for this test
        
        events = spoof_detector.run_detection()
        
        # We expect at least 4 events:
        # 1x TELEPORT (MMSI 333)
        # 2x ID_MISMATCH (MMSIs 444 and 555)
        # 1x OVERLAND (MMSI 222)
        
        types = [e["spoof_type"] for e in events]
        assert "TELEPORT" in types
        assert "ID_MISMATCH" in types
        assert "OVERLAND" in types
        
        mmsis = [e["mmsi"] for e in events]
        assert "333444555" in mmsis
        assert "444555666" in mmsis
        assert "555666777" in mmsis
        assert "222333444" in mmsis

def test_is_overland_graceful_fallback():
    """Verify is_overland returns False when shapefile is missing (real logic check)."""
    # Assuming shapefile is missing in this environment
    # We don't patch anything here to test the actual fallback
    result = spoof_detector.is_overland(20.0, 20.0)
    assert result is False

def test_land_geometry_loader_mocking():
    """Verify LandGeometryLoader can be mocked to simulate land detection without shapefile."""
    with patch("spoof_detector.LandGeometryLoader") as m_loader_cls:
        instance = m_loader_cls.return_value
        instance.contains.return_value = True
        
        assert spoof_detector.is_overland(10, 10) is True
        instance.contains.assert_called_with(10, 10)
