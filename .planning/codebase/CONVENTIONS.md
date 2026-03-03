# Coding Conventions

**Analysis Date:** 2026-03-03

## Naming Patterns

**Files:**
- Snake_case for module names: `app.py`, `ais_listener.py`, `db.py`, `dark_periods.py`
- Database and module-specific naming reflects purpose: `sts_detection.py`, `noaa_ingest.py`, `screening.py`

**Functions:**
- Snake_case for all functions: `run_detection()`, `get_stats()`, `fetch_ofac_sdn()`
- Private/internal functions prefixed with underscore: `_clean_imo()`, `_detect_query_type()`, `_check_ownership_chain()`
- Descriptive verb-noun pattern: `run_detection()`, `fetch_opensanctions_vessels()`, `upsert_sanctions_entries()`

**Variables:**
- Snake_case for variables and parameters: `min_hours`, `max_distance_km`, `vessel_type`, `gap_hours`
- Constants in UPPER_CASE with underscores: `TANKER_TYPES`, `BUFFER_SIZE`, `DARK_THRESHOLD_HOURS`
- Module-level state with underscore prefix: `_buffer`, `_stats`, `_thread`, `_BACKEND`, `_POOL`

**Types:**
- Union types using pipe syntax (Python 3.10+): `str | None`, `dict | list`, `dict[str, Any]`
- Pydantic BaseModel classes use PascalCase: `ScreeningRequest`, `DarkPeriod`, `StsEvent`, `AisPosition`
- Type hints in function signatures are comprehensive and explicit

## Code Style

**Formatting:**
- Tool: Ruff (configured in `pyproject.toml`)
- Line length: 100 characters
- Target Python: 3.11

**Linting:**
- Tool: Ruff with `select = ["ALL"]`
- Key exemptions (in `pyproject.toml`):
  - `D` — No docstring requirements
  - `ANN` — Type annotation not required (explicit hints still used)
  - `S608` — SQL injection ignored (backend-agnostic placeholder pattern)
  - `BLE001` — Broad exception catching allowed
  - `PLR` — Refactoring rules skipped
  - `PLW` — Pylint warnings disabled (globals/overwrites)
- McCabe complexity max: 20

**Spacing & Structure:**
- Two blank lines between top-level module functions/classes
- One blank line between methods
- Logical section separators using `# ── Section Name ──` pattern (seen in `app.py`, `db.py`)
- Docstrings use triple quotes and include purpose/args/returns format

## Import Organization

**Order:**
1. Standard library: `import os`, `import json`, `import sqlite3`, `import logging`
2. Third-party: `import requests`, `from flask import Flask`, `from pydantic import BaseModel`
3. Local modules: `import db`, `import screening`, `import schemas`
4. Blank line between groups

**Path Aliases:**
- No path aliases used; direct imports from project root
- Relative imports not used; all imports treat project root as module root

**Lazy loading:**
- Used for conditional imports: `from psycopg2.pool import ThreadedConnectionPool` inside functions (only loaded if postgres backend detected)
- Reduces startup overhead for development (SQLite) vs production (PostgreSQL)

## Error Handling

**Patterns:**
- Broad try-except for external API calls: `except Exception as exc:` with logging
- Context manager pattern for database connections (`@contextmanager` in `db.py`)
- Pydantic validation errors caught and returned as JSON 400 responses
- External fetch failures caught and logged with `logger.error()`, returned to caller with error dict
- Database transactions: automatic rollback on exception within context manager

**Examples:**
```python
# API ingestion with error logging
try:
    entries = fetch_fn()
    inserted, updated = db.upsert_sanctions_entries(entries, list_name)
    return {"status": "success", "processed": len(entries)}
except Exception as exc:
    return {"status": "error", "error": str(exc)}

# Pydantic validation
try:
    data = schemas.ScreeningRequest.model_validate(request.get_json(silent=True) or {})
except ValidationError as e:
    return jsonify({"error": e.errors()}), 400

# Database context manager handles rollback automatically
with _conn() as conn:
    cursor = _cursor(conn)
    cursor.execute(sql, params)
    # Auto-commits on clean exit, rolls back on exception
```

## Logging

**Framework:** Standard `logging` module (no external library)

**Patterns:**
- Logger created per module: `logger = logging.getLogger(__name__)`
- Used in data ingestion modules: `ingest.py`, `ais_listener.py`, `noaa_ingest.py`, `dark_periods.py`, etc.
- Log levels: `logger.info()` for operations, `logger.error()` for failures
- Includes operation context: `logger.info("Fetching OFAC SDN XML from %s", OFAC_SDN_URL)`

**Example:**
```python
import logging
logger = logging.getLogger(__name__)

def fetch_ofac_sdn():
    logger.info("Fetching OFAC SDN XML from %s", OFAC_SDN_URL)
    resp = requests.get(OFAC_SDN_URL, timeout=90)
```

## Comments

**When to Comment:**
- Algorithm explanations: risk scoring logic, zone classification algorithms
- Non-obvious business rules: WHY something is done, not WHAT is being done
- Complex data transformations (XML parsing, JSON unpacking)
- Commented-out code generally avoided; not found in codebase

**Docstring Format:**
- Module-level docstring: triple-quoted string at top describing purpose
- Function docstring: brief description, Args section, Returns section (when needed)
- Used selectively; not enforced by linter (D rules ignored)

**Example from `dark_periods.py`:**
```python
"""
Dark period detector — Indicator 1: AIS transponder gaps.

Queries the ais_positions time-series for each tracked vessel,
identifies gaps greater than the threshold, classifies risk level,
checks for sanctions matches, and persists results to dark_periods.

Thresholds (per the Shadow Fleet Framework):
  ≥ 2 hours  — recorded as a dark period (MEDIUM risk)
  ≥ 6 hours  — elevated risk (HIGH)
  ≥ 24 hours — critical (matches documented shadow fleet behaviour)
"""

def run_detection(mmsi: str | None = None,
                  min_hours: float = DARK_THRESHOLD_HOURS) -> list[dict]:
    """
    Detect AIS dark periods, persist them, and return the results.

    Args:
        mmsi:      Limit detection to a specific vessel. None = all vessels.
        min_hours: Minimum gap length to report (default 2 h).

    Returns:
        List of dark-period dicts, each enriched with risk_level, risk_zone, etc.
    """
```

## Function Design

**Size:**
- Typical functions: 20–60 lines
- Complex functions broken into private helpers with underscore prefix
- Example: `screening.py` has `_check_ownership_chain()`, `_annotate_hit()`, `_clean_imo()` supporting larger `screen()` and `screen_vessel_detail()` functions

**Parameters:**
- Explicit over implicit: all required params listed
- Type hints on all parameters and return values
- Optional params use None default with type hint: `mmsi: str | None = None`
- Multiple params organized by logical grouping (required first, optional/config later)

**Return Values:**
- Single return value preferred; complex returns use Pydantic models or dicts
- Pydantic models used for API responses: `ScreeningResult`, `VesselDetail`, `IndicatorSummary`
- Dicts used for internal function returns and logging results
- Boolean for simple success/failure: `is_running()`, `start(api_key)`

## Module Design

**Exports:**
- Public functions (no leading underscore): callable from other modules
- Private functions (leading underscore): used only within module
- Module-level state (globals): documented at module top with comments
- No `__all__` lists; relies on convention

**Example from `ais_listener.py`:**
```python
# ── Public API ────────────────────────────────────────────────────────────
def get_stats() -> dict:
    """Return current listener statistics."""
    ...

def is_running() -> bool:
    """Check if listener thread is active."""
    ...

def start(api_key: str) -> bool:
    """Start the background listener thread."""
    ...

def stop() -> None:
    """Signal the listener to shut down gracefully."""
    ...

# ── Background thread ─────────────────────────────────────────────────────
def _thread_main(api_key: str) -> None:
    """Entry point for the daemon thread — owns its own asyncio event loop."""
    ...
```

**Barrel Files:**
- Not used; imports are direct from source modules
- Example: `import db` not `from db import *`

---

*Convention analysis: 2026-03-03*
