"""
tests/test_fe.py — Phase 5 Frontend UX tests (FE-1 through FE-6).

Tests verify the ranking API, map score integration, staleness flags,
indicator breakdown, vessel permalink, and CSV export routes.
"""


def test_ranking_sort(app_client):
    """FE-1: /api/vessels/ranking returns JSON with vessels list when logged in."""
    # Unauthenticated → redirect
    resp_unauth = app_client.get("/api/vessels/ranking", follow_redirects=False)
    assert resp_unauth.status_code in (301, 302), (
        f"Expected redirect for unauthenticated access, got {resp_unauth.status_code}"
    )

    # Authenticate directly via session (avoids APP_PASSWORD env mismatch)
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get("/api/vessels/ranking")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.get_json()
    assert "vessels" in data, f"Missing 'vessels' key in response: {data.keys()}"
    assert isinstance(data["vessels"], list), "vessels must be a list"

    # If there are vessels, verify score order (descending)
    vessels = data["vessels"]
    if len(vessels) >= 2:
        scores = [v.get("composite_score", 0) or 0 for v in vessels]
        assert scores == sorted(scores, reverse=True), (
            f"Vessels not sorted by score desc: {scores[:5]}"
        )


def test_map_data_score(app_client):
    """FE-2: get_map_vessels() result dicts include composite_score field."""
    import map_data
    results = map_data.get_map_vessels(hours=48)
    assert isinstance(results, list), "get_map_vessels() must return a list"
    # Verify composite_score key present in all rows (value may be None)
    for v in results:
        assert "composite_score" in v, (
            f"composite_score key missing from map vessel dict: {list(v.keys())}"
        )


def test_stale_flag(app_client):
    """FE-3: is_stale field present in ranking API response rows."""
    # Authenticate directly via session (avoids APP_PASSWORD env mismatch)
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get("/api/vessels/ranking")
    assert resp.status_code == 200
    data = resp.get_json()
    vessels = data.get("vessels", [])
    for v in vessels:
        assert "is_stale" in v, f"is_stale missing from vessel row: {list(v.keys())}"


def test_indicator_json(app_client):
    """FE-4: indicator_json in /api/vessels/ranking response is a dict (not JSON string)."""
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True
    resp = app_client.get("/api/vessels/ranking")
    assert resp.status_code == 200
    data = resp.get_json()
    vessels = data.get("vessels", [])
    for v in vessels:
        assert "indicator_json" in v, f"indicator_json missing from row: {list(v.keys())}"
        ij = v["indicator_json"]
        assert isinstance(ij, dict), (
            f"indicator_json must be dict (not string), got {type(ij).__name__}"
        )


def test_vessel_permalink(app_client):
    """FE-5: GET /vessel/<imo> returns HTML (200 or 404), not JSON. Requires login."""
    # Unauthenticated → redirect to login
    resp_unauth = app_client.get("/vessel/IMO9999999", follow_redirects=False)
    assert resp_unauth.status_code in (301, 302), (
        f"Expected redirect for unauthenticated access, got {resp_unauth.status_code}"
    )

    # Authenticate directly via session (avoids APP_PASSWORD env mismatch
    # when a local .env overrides the conftest setdefault value).
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    # Unknown IMO → 404 HTML (not JSON)
    resp = app_client.get("/vessel/IMO9999999UNKNOWN")
    assert resp.status_code == 404, f"Expected 404 for unknown IMO, got {resp.status_code}"
    assert resp.content_type.startswith("text/html"), (
        f"Expected HTML response, got {resp.content_type}"
    )


def test_csv_export(app_client):
    """FE-6: GET /export/vessels.csv returns text/csv with correct headers."""
    # Unauthenticated → redirect
    resp_unauth = app_client.get("/export/vessels.csv", follow_redirects=False)
    assert resp_unauth.status_code in (301, 302), (
        f"Expected redirect for unauthenticated access, got {resp_unauth.status_code}"
    )

    # Log in via session_transaction (POST /login returns 302 even on success in test env)
    with app_client.session_transaction() as sess:
        sess["authenticated"] = True

    resp = app_client.get("/export/vessels.csv")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "text/csv" in resp.content_type, (
        f"Expected text/csv content type, got {resp.content_type}"
    )

    # Parse header row
    body = resp.data.decode("utf-8")
    lines = body.strip().splitlines()
    assert len(lines) >= 1, "CSV response must have at least a header row"

    header = lines[0]
    expected_cols = [
        "vessel_name", "imo", "mmsi", "flag",
        "composite_score", "risk_level", "evidence_count",
        "computed_at", "is_stale",
    ]
    for col in expected_cols:
        assert col in header, f"Column '{col}' missing from CSV header: {header}"
