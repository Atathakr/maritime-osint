# Testing Patterns

**Analysis Date:** 2026-03-03

## Test Framework

**Status:** No automated test framework configured.

**Runner:**
- Not detected — no test framework installed or configured
- No pytest, vitest, unittest, or similar in `pyproject.toml` or `requirements.txt`

**Assertion Library:**
- Not applicable — no testing library in use

**Run Commands:**
- No test commands available
- Tests must be added as part of future development

## Manual Testing Approach

The project currently relies on manual testing and integration testing during development. No CI/CD test pipeline is configured in `.github/workflows/`.

**Development verification approach:**
- Flask app tested locally via `python app.py` (development mode)
- API endpoints tested via HTTP client (curl, Postman, or browser)
- Database operations verified against local SQLite or test PostgreSQL instance
- AIS listener tested via manual WebSocket connection to aisstream.io

## Test File Organization

**Location:**
- No test directory structure exists
- No test files (`*_test.py`, `test_*.py`) in repository

**Recommended structure (when tests are added):**
- `tests/` directory at project root
- `tests/unit/` for isolated unit tests
- `tests/integration/` for database and external API integration tests
- `tests/fixtures/` for test data and mock responses

**Naming convention (to adopt):**
- Test files: `test_<module>.py` (e.g., `test_db.py`, `test_screening.py`)
- Test functions: `test_<function>_<scenario>()` (e.g., `test_clean_imo_valid()`, `test_clean_imo_invalid()`)
- Test classes (if used): `Test<Module>` (e.g., `TestScreening`, `TestDarkPeriods`)

## Test Structure (Recommended Pattern)

Based on the modular design of the codebase, the following test structure is recommended when tests are implemented:

**Unit Tests:**
- Validation functions: `_clean_imo()`, `_clean_mmsi()`, `_detect_query_type()`
- Utility functions: zone classification, risk scoring calculations
- Data transformation functions: XML parsing, JSON unpacking
- Expected test framework: pytest with simple assert statements

**Example (not yet implemented):**
```python
import pytest
from screening import _clean_imo, _detect_query_type

def test_clean_imo_valid():
    assert _clean_imo("1234567") == "1234567"
    assert _clean_imo("IMO: 1234567") == "1234567"

def test_clean_imo_invalid():
    assert _clean_imo("12345") is None
    assert _clean_imo(None) is None
    assert _clean_imo("") is None

def test_detect_query_type_imo():
    assert _detect_query_type("1234567") == "imo"

def test_detect_query_type_mmsi():
    assert _detect_query_type("123456789") == "mmsi"

def test_detect_query_type_name():
    assert _detect_query_type("EVER GIVEN") == "name"
```

**Integration Tests:**
- Database operations: upsert, query, filtering
- API endpoints: screening, ingest, AIS listener control
- Data ingestion: OFAC, OpenSanctions, NOAA CSV parsing
- Expected test framework: pytest with Flask test client

**Example (not yet implemented):**
```python
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}

def test_screening_endpoint_requires_auth(client):
    app.config['APP_PASSWORD'] = "test_password"
    response = client.post("/api/screen", json={"query": "1234567"})
    assert response.status_code == 302  # Redirect to login
```

## Mocking (Recommended)

**Framework:** `unittest.mock` (standard library) or `pytest-mock`

**Patterns (to adopt):**

**External API mocking:**
- OFAC SDN XML fetches: mock `requests.get()` to return fixture XML
- OpenSanctions streaming: mock response generator
- AISSTREAM WebSocket: mock asyncio connection
- PostgreSQL connections (when testing postgres path): use SQLite in-memory for tests

**Database mocking:**
- Two approaches:
  1. Real database (preferred for integration tests): use temporary SQLite in-memory DB
  2. Mocked database (unit tests): mock `db._conn()` and `db._cursor()` to return mock cursors

**Example (not yet implemented):**
```python
from unittest.mock import patch, MagicMock
import ingest

@patch('ingest.requests.get')
def test_fetch_ofac_sdn_success(mock_get):
    with open('tests/fixtures/ofac_sample.xml', 'r') as f:
        mock_get.return_value.content = f.read()

    result = ingest.fetch_ofac_sdn(vessel_only=True)
    assert isinstance(result, list)
    assert len(result) > 0
    mock_get.assert_called_once()

@patch('db._conn')
def test_upsert_sanctions_entries(mock_conn):
    mock_cursor = MagicMock()
    mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

    entries = [{"entity_name": "Test Vessel", "imo_number": "1234567"}]
    result = db.upsert_sanctions_entries(entries, "TEST_LIST")
    assert result[0] > 0  # inserted count
```

## What to Mock

**External Services:**
- HTTP requests to OFAC, OpenSanctions, NOAA APIs
- AISSTREAM WebSocket connections
- PostgreSQL connections (in unit tests; use SQLite in integration tests)

**What NOT to Mock:**
- Database queries (use real SQLite in-memory for integration tests)
- Pydantic validation (test actual validation logic)
- Core business logic (risk scoring, zone classification) — should be unit-tested with real calculations
- Flask app initialization — test real app in integration tests

## Fixtures and Factories

**Test Data (to create):**
- `tests/fixtures/ofac_sample.xml` — Sample OFAC SDN XML with 2–3 vessel entries
- `tests/fixtures/opensanctions_sample.json` — Sample OpenSanctions FTM entries
- `tests/fixtures/noaa_sample.csv` — Sample NOAA Marine Cadastre CSV (tankers, small subset)
- `tests/fixtures/ais_positions.json` — Sample AIS position reports for dark-period detection
- `tests/fixtures/sts_events.json` — Sample proximity events for STS testing

**Location:**
- `tests/fixtures/` directory
- Loaded in tests via: `with open('tests/fixtures/sample.xml')` or pytest fixture parametrization

**Factory Pattern (for Pydantic models):**

Example (not yet implemented):
```python
import pytest
from schemas import AisPosition, SanctionsEntry
from datetime import datetime, timezone

@pytest.fixture
def sample_ais_position():
    return AisPosition(
        mmsi="123456789",
        lat=25.5,
        lon=55.3,
        vessel_name="Test Tanker",
        vessel_type=80,
        sog=12.5,
        position_ts=datetime.now(timezone.utc)
    )

@pytest.fixture
def sample_sanctions_entry():
    return SanctionsEntry(
        list_name="OFAC_SDN",
        source_id="12345",
        entity_name="Test Vessel",
        imo_number="1234567",
        flag_state="Panama"
    )
```

## Coverage

**Requirements:** Not enforced (no pytest-cov configuration)

**Recommendation for future:**
- Target 70%+ coverage for database layer (`db.py`)
- Target 80%+ coverage for validation/screening logic (`screening.py`)
- Target 60%+ coverage for ingestion pipelines (`ingest.py`, `noaa_ingest.py`)
- Allow lower coverage (40%+) for UI layer and daemon threads (threading/async code)

**View Coverage (when pytest-cov added):**
```bash
pytest --cov=. --cov-report=html
# Open htmlcov/index.html
```

## Test Types (to Implement)

**Unit Tests:**
- Scope: Individual functions with no external dependencies
- Approach: Mock external APIs, test with parametrized inputs
- Files: `tests/unit/test_screening.py`, `tests/unit/test_ingest.py`, `tests/unit/test_dark_periods.py`
- Validation functions, helper utilities, risk calculation logic

**Integration Tests:**
- Scope: Database operations, API endpoints, data pipelines
- Approach: Real SQLite in-memory database, Flask test client
- Files: `tests/integration/test_db.py`, `tests/integration/test_api.py`, `tests/integration/test_ingest.py`
- Full ingest workflows, API request/response cycles, database state verification

**End-to-End Tests:**
- Scope: Full platform workflows (not yet implemented)
- Approach: Docker compose with real PostgreSQL, sample data ingestion, manual verification
- Future: Consider Playwright for browser-based testing of frontend

## Async Testing

**Framework:** pytest-asyncio (to add)

**Pattern (to adopt for `ais_listener.py`):**

Example (not yet implemented):
```python
import pytest
import asyncio
from ais_listener import _connect_websocket

@pytest.mark.asyncio
async def test_websocket_connection_retry():
    with patch('websockets.connect') as mock_connect:
        mock_connect.side_effect = ConnectionError("Network error")

        with pytest.raises(ConnectionError):
            await _connect_websocket("wss://stream.aisstream.io/v0/stream", "test_key")

@pytest.mark.asyncio
async def test_message_parsing():
    sample_message = '{"Type": "PositionReport", ...}'
    result = await _parse_ais_message(sample_message)
    assert result["mmsi"] == "123456789"
```

## Error Testing

**Pattern (to adopt):**
- Test that validation errors return 400 with error details
- Test that database errors return 502 (bad gateway / service error)
- Test that invalid parameters are rejected early
- Use pytest parametrization for multiple error scenarios

**Example (not yet implemented):**
```python
@pytest.mark.parametrize("invalid_query", [
    "",                    # Empty query
    "x" * 1000,          # Too long
    None,                # Null
])
def test_screening_invalid_query(client, invalid_query):
    response = client.post("/api/screen", json={"query": invalid_query})
    assert response.status_code == 400

def test_database_error_returns_502(client, monkeypatch):
    def mock_error(*args, **kwargs):
        raise Exception("Connection lost")

    monkeypatch.setattr("db.upsert_sanctions_entries", mock_error)
    response = client.post("/api/ingest/ofac")
    assert response.status_code == 502
```

---

*Testing analysis: 2026-03-03*

**Note:** The project currently has no automated test suite. These recommendations describe patterns to adopt when implementing tests. Start with unit tests for validation functions, then add integration tests for database and API layers.
