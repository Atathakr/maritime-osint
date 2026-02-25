
import os
import datetime
import db
import spoof_detector
from app import app

# Set environment variables for testing
os.environ["DATABASE_URL"] = "sqlite:///maritime_osint.db"

def verify():
    print("Initializing test database...")
    db.init_db()

    mmsi = "999999999"
    vessel_name = "SPOOF_TEST_VESSEL"
    
    # 1. Inject two ais_positions that are far apart in space but close in time
    # Pos 1: (25.0, -90.0) at T
    # Pos 2: (26.0, -90.0) at T + 1 minute
    # Distance: 1 degree latitude is approx 111 km.
    # Speed: 111 km in 1 min = 111 * 60 = 6660 km/h
    # 6660 km/h / 1.852 = ~3600 kts (Definitely > 30 kts)

    t1 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    t2 = t1 + datetime.timedelta(minutes=1)

    t1_str = t1.isoformat()
    t2_str = t2.isoformat()

    print(f"Injecting test positions for MMSI {mmsi}...")
    db.insert_ais_positions([
        {
            "mmsi": mmsi,
            "vessel_name": vessel_name,
            "lat": 25.0,
            "lon": -90.0,
            "sog": 10.0,
            "position_ts": t1_str
        },
        {
            "mmsi": mmsi,
            "vessel_name": vessel_name,
            "lat": 26.0,
            "lon": -90.0,
            "sog": 10.0,
            "position_ts": t2_str
        }
    ])

    # 2. Call the detector directly
    print("Running spoof detection via detector directly...")
    events = spoof_detector.run_detection(mmsi=mmsi, hours_back=1)
    assert len(events) >= 1, "Should have found at least one TELEPORT event via direct call"

    # 3. Call via API (using test client)
    print("Running spoof detection via API...")
    with app.test_client() as client:
        # We need to bypass login_required if APP_PASSWORD is set.
        # In development/testing, we can set session['authenticated'] = True
        with client.session_transaction() as sess:
            sess['authenticated'] = True
        
        # Test POST /api/spoof/run
        resp = client.post("/api/spoof/run", json={"mmsi": mmsi, "hours_back": 1})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["mmsi"] == mmsi
        
        # Test GET /api/spoof/events
        resp = client.get(f"/api/spoof/events?mmsi={mmsi}")
        assert resp.status_code == 200
        events_api = resp.get_json()
        assert len(events_api) >= 1
        assert events_api[0]["mmsi"] == mmsi
        assert events_api[0]["spoof_type"] == "TELEPORT"

    print("API verification successful!")

    # 4. Cleanup
    print("Cleaning up test data...")
    with db._conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM ais_positions WHERE mmsi = ?", (mmsi,))
        c.execute("DELETE FROM spoof_events WHERE mmsi = ?", (mmsi,))
    print("Cleanup complete.")

if __name__ == "__main__":
    try:
        verify()
    except Exception as e:
        print(f"Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
