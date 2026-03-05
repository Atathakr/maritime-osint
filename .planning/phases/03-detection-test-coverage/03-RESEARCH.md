# Phase 3: Detection Test Coverage - Research

**Researched:** 2026-03-05
**Domain:** pytest testing, detection module refactoring, pure function extraction, mock/patch patterns
**Confidence:** HIGH

---

## Summary

All five detection modules exist and work correctly but are structured as database-coupled
pipelines. None expose a pure `detect(positions)` function today. The refactoring task is
well-defined: extract the pure classification logic that already exists inside each module as
private helpers, expose it as a top-level `detect(positions)` function, and leave the database-
calling `run_detection()` wrapper in place. The pytest infrastructure is partially built
(pytest 9.0.2 already installed, 20 tests passing), but `conftest.py` only guards
`DATABASE_URL`; it does not guard `AISSTREAM_API_KEY` and does not initialize an in-memory
SQLite fixture. pytest-cov is not installed.

The most important architectural insight: each module's pure logic is already nearly
extractable. `dark_periods.py` and `loitering.py` do their classification fully in Python
(no db inside the enrichment loop); only the fetch and persist calls touch db. `sts_detection.py`
is similar. `spoofing.py` takes pre-fetched pairs from `db.get_consecutive_ais_pairs()` and
runs pure arithmetic. `screening.py/compute_vessel_score()` is the hardest: it calls db for
every indicator and has no existing separation between data fetch and classification.

**Primary recommendation:** Introduce a `detect(positions: list[dict]) -> list[dict]` function
in each module that accepts a flat list of position dicts and returns result dicts with no db
calls. Tests import the module directly and call `detect()` with synthetic fixtures. No mocking
needed for the four AIS detection modules; `screening.py` needs targeted `unittest.mock.patch`
for the 8-10 db calls in `compute_vessel_score()`.

---

## Current State of Each Detection Module

### dark_periods.py

**Public API today:** `run_detection(mmsi, min_hours) -> list[dict]`

**DB calls inside `run_detection()`:**
- `db.find_ais_gaps(mmsi, min_hours)` — fetches raw gap rows (input data)
- `db.search_sanctions_by_mmsi(mmsi_val)` — inside per-gap loop
- `db.search_sanctions_by_imo(imo_val)` — inside per-gap loop
- `db.upsert_dark_periods(enriched)` — persist at the end

**Pure logic that already exists (no db):**
- `_classify_zone(lat, lon)` — already a clean pure function
- `_haversine(lat1, lon1, lat2, lon2)` — already a clean pure function
- Risk-level logic inside the loop (lines 71-88) — inline, extractable as ~5 lines

**Does `detect(positions)` exist?** No.

**What `detect(positions)` needs to accept:**
```python
# Each position dict is a "gap" row matching what db.find_ais_gaps() returns:
{
    "mmsi": "123456789",
    "imo_number": "1234567",       # optional
    "vessel_name": "VESSEL A",     # optional
    "gap_start": "2024-01-01T00:00:00",
    "gap_end":   "2024-01-01T06:00:00",
    "gap_hours": 6.0,
    "last_lat":  22.5,
    "last_lon":  57.0,
    "reappear_lat": 22.8,
    "reappear_lon": 57.3,
}
```

**What `detect(positions)` returns:** enriched dicts with `risk_level`, `risk_zone`,
`distance_km`, `sanctions_hit` (always False — sanctions lookup is a db call the pure
function cannot do).

**Note on sanctions:** The pure `detect()` must omit sanctions cross-reference (db call).
The `run_detection()` wrapper retains the full pipeline including sanctions. Tests verify
pure classification; they do not test sanctions enrichment.

---

### sts_detection.py

**Public API today:** `run_detection(hours_back, max_distance_km, max_sog) -> list[dict]`

**DB calls inside `run_detection()`:**
- `db.find_sts_candidates(hours_back, max_sog)` — fetches raw candidate pairs (input data)
- `db.search_sanctions_by_mmsi(mmsi1)` — per-candidate
- `db.search_sanctions_by_mmsi(mmsi2)` — per-candidate
- `db.upsert_sts_events(events)` — persist at end

**Pure logic that already exists (no db):**
- `_haversine(lat1, lon1, lat2, lon2)` — clean pure function
- `_classify_zone(lat, lon)` — clean pure function
- `_risk_level(distance_km, sanctions_hit, risk_zone, sog1, sog2)` — clean pure function
- `_deduplicate(events)` — clean pure function
- `_ts_to_epoch(ts)` — clean pure function
- The Haversine/slow-vessel filter loop (lines 148-204) — extractable

**Does `detect(positions)` exist?** No.

**What `detect(positions)` needs to accept:**
```python
# Each dict is an STS candidate pair matching find_sts_candidates() output:
{
    "mmsi1": "123456789",
    "mmsi2": "987654321",
    "vessel_name1": "VESSEL A",   # optional
    "vessel_name2": "VESSEL B",   # optional
    "lat1": 22.5,
    "lon1": 57.0,
    "lat2": 22.501,
    "lon2": 57.001,
    "sog1": 0.5,
    "sog2": 2.8,
    "ts": "2024-01-01T12:00:00",
}
```

**Note on STS:** `sanctions_hit` will always be `False` in the pure function since sanctions
lookup requires db. The `_risk_level()` function accepts `sanctions_hit` as a parameter, so
a pure detect passes `sanctions_hit=False` for all candidates.

---

### loitering.py

**Public API today:** `detect_loitering_episodes(mmsi, sog_threshold_kt, min_hours, hours_back, limit) -> list[dict]`
and `run_loitering_detection(...)` which wraps it and calls `db.upsert_loitering_events()`.

**DB calls:**
- `_get_low_speed_positions()` inside `detect_loitering_episodes()` — this is the only db call
- `db.upsert_loitering_events(episodes)` inside `run_loitering_detection()`

**Key insight:** `_group_episodes(rows, sog_threshold, min_hours)` is ALREADY a pure function
that takes a list of dicts and returns episodes. `detect_loitering_episodes()` is nearly
pure — it only calls `_get_low_speed_positions()` to fetch its input data.

**Does `detect(positions)` exist?** Not named that, but `_group_episodes()` is essentially it.
The `detect()` function for loitering will be a thin public wrapper over `_group_episodes()`.

**What `detect(positions)` needs to accept:**
```python
# AIS position rows — each dict has:
{
    "mmsi":        "123456789",
    "imo_number":  "1234567",        # optional
    "vessel_name": "VESSEL A",       # optional
    "lat":         22.5,
    "lon":         57.0,
    "sog":         1.5,              # knots
    "position_ts": "2024-01-01T00:00:00",
}
```
Rows should be sorted ascending by `position_ts` per vessel. The factory function must
pre-sort by MMSI+timestamp to mirror `_get_low_speed_positions()` output.

**IMPORTANT:** `loitering.py` imports `from dark_periods import HIGH_RISK_ZONES`. This import
will work in tests because `dark_periods.py` has no db call at import time — it only imports
`db` and `schemas` at module level, which is fine with `DATABASE_URL=""`.

---

### spoofing.py

**Public API today:** `detect_speed_anomalies(mmsi, threshold_kt, hours_back, limit) -> list[dict]`

**DB calls:**
- `db.get_consecutive_ais_pairs(mmsi, hours_back, limit)` — fetches input data

**Pure logic:**
- `_haversine(lat1, lon1, lat2, lon2)` — clean
- The speed calculation loop (lines 65-103) — extractable

**Does `detect(positions)` exist?** No.

**What `detect(positions)` needs to accept:**
```python
# Consecutive AIS position pairs matching get_consecutive_ais_pairs() output:
{
    "mmsi":           "123456789",
    "imo_number":     "1234567",       # optional
    "vessel_name":    "VESSEL A",      # optional
    "lat":            22.5,
    "lon":            57.0,
    "next_lat":       22.6,
    "next_lon":       58.5,            # ~157 km away
    "next_ts":        "2024-01-01T01:00:00",
    "time_delta_min": 60.0,
}
```

**Note:** `spoofing.py` imports `risk_config` at module level. `SPEED_ANOMALY_THRESHOLD_KT = 50.0`
is the default. The pure `detect()` should accept `threshold_kt` as a parameter and default to
`risk_config.SPEED_ANOMALY_THRESHOLD_KT` — same as `detect_speed_anomalies()` does today.

---

### screening.py — `compute_vessel_score()`

**This is the complex case.** `compute_vessel_score()` is NOT a detection module in the same
sense as the others — it is an aggregation/scoring function that reads from multiple db tables,
not from a live AIS stream. The Phase 3 goal specifies a `detect(positions)` pattern, but for
`screening.py`, this means something different: the planner should test `compute_vessel_score()`
via mock injection, not by extracting a pure function from live AIS positions.

**DB calls inside `compute_vessel_score(imo)`:**
```
db.get_vessel(imo_clean)                    — vessel lookup
db.get_ais_vessel_by_imo(imo_clean)         — AIS vessel fallback
db.search_sanctions_by_imo(imo_clean)       — sanctions check
db.get_vessel_flag_history(imo_clean)       — flag hopping (IND15)
db.get_vessel_indicator_summary(mmsi)       — AIS signals (IND1/7/8/9/10/29)
db.get_vessel_ownership(canonical_id)       — ownership chain (IND21)
db.search_sanctions_by_name(entity_name)    — ownership sanctions
db.get_psc_detentions(imo_clean)            — PSC record (IND31)
db.get_ais_vessel_by_imo(imo_clean)         — IND16 name discrepancy
```

**Other functions in screening.py:**
- `screen(query)` — pure query classification + db calls for sanctions lookup
- `score_is_stale(score_row, minutes)` — ALREADY a pure function; tests already exist in test_scores.py
- `_detect_query_type(query)` — pure string classification
- `_annotate_hit(hit, query_type)` — pure dict mutation
- `_clean_imo(raw)`, `_clean_mmsi(raw)` — pure string cleaning
- `screen_vessel_detail(imo)` — calls `compute_vessel_score()` + many db calls

**What does `detect()` mean for `screening.py`?**

The roadmap specifies: "Extract detect(positions) from screening.py." The most
sensible interpretation given the module's actual structure:

1. The pure logic already extracted: `_detect_query_type`, `_annotate_hit`, `_clean_imo`,
   `_clean_mmsi`, `score_is_stale` — all already pure and testable without db.
2. `compute_vessel_score()` should be tested with `unittest.mock.patch` for each db call.
3. A `detect(indicator_inputs: dict) -> dict` function can be extracted from
   `compute_vessel_score()` that accepts pre-fetched data as a dict and returns the score
   dict with no db calls.

**Mock patch targets for `compute_vessel_score()` tests:**
All db calls in `compute_vessel_score()` go through the `db` module re-export surface.
Patch targets use the module where the name is *used*, not where it is defined:

```python
"screening.db.get_vessel"
"screening.db.get_ais_vessel_by_imo"
"screening.db.search_sanctions_by_imo"
"screening.db.get_vessel_flag_history"
"screening.db.get_vessel_indicator_summary"
"screening.db.get_vessel_ownership"
"screening.db.search_sanctions_by_name"
"screening.db.get_psc_detentions"
```

---

## Threshold Constants — Complete Reference

| Module | Constant | Value | Meaning |
|--------|----------|-------|---------|
| dark_periods | `DARK_THRESHOLD_HOURS` | 2.0 h | minimum gap to record (MEDIUM) |
| dark_periods | `HIGH_RISK_HOURS` | 6.0 h | elevated risk (HIGH) |
| dark_periods | `CRITICAL_HOURS` | 24.0 h | critical / shadow fleet pattern |
| sts_detection | `STS_DISTANCE_KM` | 0.926 km | 0.5 nautical miles |
| sts_detection | `STS_TIME_WINDOW_MIN` | 30 min | max time gap for pair matching |
| sts_detection | `MAX_SOG` | 3.0 kt | at least one vessel must be <= this |
| sts_detection | `DEDUP_HOURS` | 2.0 h | same pair within this = same event |
| loitering | `SOG_THRESHOLD_KT` | 2.0 kt | below this = "loitering" |
| loitering | `MIN_LOITER_HOURS` | 12.0 h | minimum episode duration |
| loitering | (inline) | 48.0 h | CRITICAL threshold |
| loitering | (inline) | 24.0 h | HIGH threshold (or 12h in risk zone) |
| loitering | (inline) | 6.0 h | gap breaks episode continuity |
| spoofing | `SPEED_ANOMALY_THRESHOLD_KT` (risk_config) | 50.0 kt | triggers anomaly |
| screening | `SCORE_STALENESS_MINUTES` (db.scores) | 30 min | score recompute trigger |
| risk_config | `IND23_AGE_THRESHOLD` | 15 years | vessel age no-contribution floor |
| risk_config | `IND23_PTS_PER_YEAR` | 3 pts/yr | age scoring rate |
| risk_config | `IND23_CAP` | 15 pts | IND23 maximum |
| risk_config | `IND21_OWNER_SANCTION` | 20 pts | per sanctioned owner entity |
| risk_config | `IND31_PER_DETENTION` | 10 pts | per PSC detention |
| risk_config | `IND31_CAP` | 20 pts | IND31 maximum |

---

## AIS Position Data Shape

### Standard AIS position row (from `ais_positions` table / `db.get_ais_positions()`)
```python
{
    "mmsi":        "123456789",    # 9-digit string
    "imo_number":  "1234567",      # 7-digit string or None
    "vessel_name": "VESSEL A",     # str or None
    "lat":         22.5,           # float -90..90
    "lon":         57.0,           # float -180..180
    "sog":         0.5,            # float, knots, or None
    "cog":         180.0,          # float degrees, or None
    "heading":     180,            # int degrees, or None
    "nav_status":  1,              # int, or None
    "source":      "aisstream",    # str
    "position_ts": "2024-01-01T12:00:00",  # ISO8601 string or datetime
}
```

### AIS gap row (from `db.find_ais_gaps()`) — used by dark_periods
```python
{
    "mmsi":        "123456789",
    "imo_number":  "1234567",
    "vessel_name": "VESSEL A",
    "gap_start":   "2024-01-01T00:00:00",
    "gap_end":     "2024-01-01T06:30:00",
    "gap_hours":   6.5,
    "last_lat":    22.5,
    "last_lon":    57.0,
    "reappear_lat": 22.8,
    "reappear_lon": 57.3,
}
```

### STS candidate pair (from `db.find_sts_candidates()`)
```python
{
    "mmsi1": "123456789",
    "mmsi2": "987654321",
    "vessel_name1": "VESSEL A",
    "vessel_name2": "VESSEL B",
    "lat1": 22.5, "lon1": 57.0,
    "lat2": 22.501, "lon2": 57.001,
    "sog1": 0.5, "sog2": 2.8,
    "ts": "2024-01-01T12:00:00",
}
```

### Consecutive AIS pair (from `db.get_consecutive_ais_pairs()`) — used by spoofing
```python
{
    "mmsi":           "123456789",
    "imo_number":     "1234567",
    "vessel_name":    "VESSEL A",
    "lat":            22.5,  "lon":      57.0,
    "next_lat":       22.6,  "next_lon": 58.5,
    "next_ts":        "2024-01-01T01:00:00",
    "time_delta_min": 60.0,
}
```

---

## Architecture Patterns

### Recommended Test File Structure
```
tests/
├── __init__.py               # exists (empty)
├── conftest.py               # upgrade: add AISSTREAM_API_KEY guard + in-memory SQLite
├── ais_factory.py            # new: synthetic position sequence generators
├── test_db_package.py        # existing (Phase 1)
├── test_inf3_anthropic.py    # existing (Phase 1)
├── test_inf4_startup.py      # existing (Phase 1)
├── test_scores.py            # existing (Phase 2)
├── test_dark_periods.py      # new (Phase 3 — 03-02)
├── test_sts_detection.py     # new (Phase 3 — 03-02)
├── test_loitering.py         # new (Phase 3 — 03-03)
├── test_spoofing.py          # new (Phase 3 — 03-03)
└── test_screening.py         # new (Phase 3 — 03-03)
```

### Pattern 1: conftest.py Upgrade
The existing conftest.py only calls `os.environ.setdefault("DATABASE_URL", "")`.
Phase 3 needs it to also clear `AISSTREAM_API_KEY` and, importantly, must use `os.environ`
force-set (not `setdefault`) to guarantee the variable is empty even if the CI environment
exports it:

```python
# tests/conftest.py — Phase 3 upgrade
import os
import pytest

# Force-clear before any db import in the test session.
# setdefault is NOT sufficient if the CI environment already has these set.
os.environ["DATABASE_URL"] = ""
os.environ.pop("AISSTREAM_API_KEY", None)

@pytest.fixture(scope="session")
def sqlite_db():
    """Initialize a fresh in-memory-equivalent SQLite DB for the test session."""
    import db
    db._init_backend()
    db.init_db()
    return db._sqlite_path()
```

**Why `os.environ["DATABASE_URL"] = ""`** (not `setdefault`): The existing `test_scores.py`
already sets this with `os.environ["DATABASE_URL"] = ""` at module level, which overrides
`setdefault`. The conftest should match this pattern to be consistent.

### Pattern 2: ais_factory.py Position Generators
The factory module lives in `tests/` (not a conftest fixture) so it can be imported directly.
Keep it as plain functions, not pytest fixtures, so they can be called with custom parameters
in each test:

```python
# tests/ais_factory.py
from datetime import datetime, timezone, timedelta

BASE_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)

def make_gap(
    mmsi="123456789",
    gap_hours=3.0,
    last_lat=22.5, last_lon=57.0,
    reappear_lat=None, reappear_lon=None,
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
    lat=22.5, lon=57.0,
    interval_minutes=30,
    imo_number=None,
    vessel_name="TEST VESSEL",
) -> list[dict]:
    """Build a sequence of low-speed AIS position rows for loitering.detect() input."""
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
    mmsi1="123456789", mmsi2="987654321",
    lat1=22.5, lon1=57.0,
    lat2=22.501, lon2=57.001,   # ~130m apart
    sog1=0.5, sog2=2.8,
    ts=None,
) -> dict:
    """Build a single STS candidate pair for sts_detection.detect() input."""
    if ts is None:
        ts = BASE_TS.isoformat()
    return {
        "mmsi1": mmsi1, "mmsi2": mmsi2,
        "vessel_name1": "VESSEL A", "vessel_name2": "VESSEL B",
        "lat1": lat1, "lon1": lon1,
        "lat2": lat2, "lon2": lon2,
        "sog1": sog1, "sog2": sog2,
        "ts": ts,
    }

def make_consecutive_pair(
    mmsi="123456789",
    lat=22.5, lon=57.0,
    next_lat=22.6, next_lon=58.5,   # ~157 km away
    time_delta_min=60.0,
    imo_number=None,
    vessel_name="TEST VESSEL",
) -> dict:
    """Build a consecutive AIS position pair for spoofing.detect() input."""
    ts = BASE_TS + timedelta(minutes=time_delta_min)
    return {
        "mmsi": mmsi,
        "imo_number": imo_number,
        "vessel_name": vessel_name,
        "lat": lat, "lon": lon,
        "next_lat": next_lat, "next_lon": next_lon,
        "next_ts": ts.isoformat(),
        "time_delta_min": time_delta_min,
    }
```

### Pattern 3: Boundary Test Structure
Reference module constants in tests to avoid hardcoding magic numbers:

```python
# tests/test_dark_periods.py
import dark_periods
from ais_factory import make_gap

EPSILON = 0.01  # fractional hours, small enough to be below any threshold

def test_dark_period_medium_not_triggered_below_threshold():
    """Gap at DARK_THRESHOLD_HOURS - epsilon must NOT be detected."""
    gap = make_gap(gap_hours=dark_periods.DARK_THRESHOLD_HOURS - EPSILON)
    result = dark_periods.detect([gap])
    assert result == []

def test_dark_period_medium_triggered_at_threshold():
    """Gap at DARK_THRESHOLD_HOURS must be detected as MEDIUM."""
    gap = make_gap(gap_hours=dark_periods.DARK_THRESHOLD_HOURS + EPSILON)
    result = dark_periods.detect([gap])
    assert len(result) == 1
    assert result[0]["risk_level"] == "MEDIUM"
```

### Pattern 4: Mock Patch Targets for screening.py
All imports in `screening.py` use `import db`, so patches must target `screening.db.*`:

```python
# tests/test_screening.py
from unittest.mock import patch, MagicMock
import screening

def test_compute_vessel_score_sanctioned_returns_100():
    with patch("screening.db.get_vessel", return_value=None), \
         patch("screening.db.get_ais_vessel_by_imo", return_value=None), \
         patch("screening.db.search_sanctions_by_imo", return_value=[
             {"canonical_id": "C1", "entity_name": "VESSEL X", "flag_state": "IR"}
         ]), \
         patch("screening.db.get_vessel_flag_history", return_value=[]), \
         patch("screening.db.get_vessel_indicator_summary", return_value={}), \
         patch("screening.db.get_vessel_ownership", return_value=[]), \
         patch("screening.db.search_sanctions_by_name", return_value=[]), \
         patch("screening.db.get_psc_detentions", return_value=[]):
        result = screening.compute_vessel_score("9876543")
        assert result["composite_score"] == 100
        assert result["is_sanctioned"] is True
```

### Anti-Patterns to Avoid
- **Mocking `db` itself**: Patch `screening.db.fn_name`, not `db.fn_name`. The module under
  test (`screening`) imports `db` into its own namespace; you must patch where it is used.
- **Using `monkeypatch.chdir`**: The existing test_scores.py documents that `db._sqlite_path()`
  is `__file__`-anchored to the project root. Changing cwd does NOT change where SQLite writes.
  Tests that need a fresh DB must use raw SQL cleanup, not cwd tricks.
- **Schema differences between test DB and production**: Always call `db.init_db()` to get the
  real schema. Never create tables manually in tests.
- **Importing screening before os.environ is set**: pydantic is imported via `schemas.py` at
  import time. The two failing tests (`test_score_is_stale_age`, `test_score_is_stale_flag`)
  fail because pydantic is not installed in the test runner environment — this is a separate
  environment concern. The test session conftest must set env vars before any `import screening`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| db mock isolation | custom test db wrapper | `unittest.mock.patch` + `monkeypatch.setenv` | Already used in test_scores.py; consistent |
| coverage reporting | custom coverage script | `pytest-cov` (`--cov=module --cov-report=term-missing`) | Standard plugin; add to requirements.txt |
| test data generation | ad-hoc inline dicts | `ais_factory.py` helper functions | Reusability across 5 test files; readable boundary math |
| haversine computation in tests | recalculating in test assertions | trust the module's output; only assert risk_level/zone | Tests should verify behavior, not re-implement the algorithm |

**Key insight:** The detection modules' private helpers (`_haversine`, `_classify_zone`,
`_risk_level`) are already correct. Tests verify the public interface behavior at boundary
values, not the math internals.

---

## Common Pitfalls

### Pitfall 1: conftest.py setdefault vs force-set
**What goes wrong:** `os.environ.setdefault("DATABASE_URL", "")` does not clear the variable
if CI already has `DATABASE_URL=postgresql://...` exported. The test runner connects to
production.
**Why it happens:** `setdefault` is a no-op when the key exists.
**How to avoid:** Use `os.environ["DATABASE_URL"] = ""` (force-set) in conftest.py.
**Warning signs:** Tests that pass locally but fail in CI, or any test that hangs on a
PostgreSQL connection timeout.

### Pitfall 2: AISSTREAM_API_KEY not guarded
**What goes wrong:** `ais_listener.py` imports with `AISSTREAM_API_KEY` in the environment;
tests that indirectly trigger app imports may attempt a WebSocket connection.
**Why it happens:** Current conftest.py does not clear this key.
**How to avoid:** Add `os.environ.pop("AISSTREAM_API_KEY", None)` to conftest.py before
any app imports.
**Warning signs:** Test session hangs or connection-refused errors on port 443 during test
collection.

### Pitfall 3: loitering.py imports dark_periods at module top
**What goes wrong:** `from dark_periods import HIGH_RISK_ZONES` — if `dark_periods.py` had
a db call at module level this would fail when DATABASE_URL is empty. It does not, but
importing `loitering` will trigger importing `dark_periods`, which imports `db` and `schemas`.
**Why it happens:** Import chain is `loitering` → `dark_periods` → `db` → `db.connection`
→ `_init_backend()` (reads DATABASE_URL from env). With `DATABASE_URL=""` this resolves to
`sqlite`, which is correct.
**How to avoid:** Ensure conftest.py sets env vars before any test module is collected.
The `conftest.py` module-level code runs before test collection; this is safe.
**Warning signs:** None expected given current code structure.

### Pitfall 4: SQLite DB on disk polluted across test runs
**What goes wrong:** `test_scores.py` writes to the project-root `maritime_osint.db`. New
detection tests that call `db.init_db()` will write to the same file. Tests from Phase 2
that clean up by IMO may conflict with Phase 3 tests using the same IMO strings.
**Why it happens:** `db._sqlite_path()` is anchored to the project root, not `tmp_path`.
**How to avoid:** Use unique MMSI/IMO strings that do not overlap with Phase 2 tests
(Phase 2 uses `IMO1234567` through `IMO6666666`; Phase 3 should use `IMO7000001` onward
for db-touching tests). For pure detect() tests there is no db interaction at all.
**Warning signs:** Flaky test counts or assertion failures when tests run in different orders.

### Pitfall 5: pydantic not installed in test environment
**What goes wrong:** `test_scores.py::test_score_is_stale_age` and `test_score_is_stale_flag`
currently fail with `ModuleNotFoundError: No module named 'pydantic'`. This is because these
tests import `screening` which imports `schemas` which imports pydantic.
**Why it happens:** pydantic is in `pyproject.toml` dependencies but not in `requirements.txt`
(the file used for `pip install -r requirements.txt` in CI/dev).
**How to avoid:** Add `pydantic>=2.0.0` to `requirements.txt`. This is a prerequisite for
Phase 3 tests since all five detection modules either import `schemas` directly or are
imported alongside it.
**Warning signs:** The 2 pre-existing failing tests in the current test run.

### Pitfall 6: sanctions_hit always False in pure detect()
**What goes wrong:** Test asserts `sanctions_hit == True` on a result from the pure `detect()`
function.
**Why it happens:** The pure function cannot call db.search_sanctions_by_mmsi().
**How to avoid:** Document clearly in the `detect()` docstring that sanctions enrichment is
omitted. Tests for pure detection functions must NOT assert on `sanctions_hit`.
**Warning signs:** A test that expects `sanctions_hit=True` without any mocking.

---

## Coverage Projections

Based on module structure and lines of logic:

| Module | Total Meaningful Lines | Lines Covered by detect() tests | Projected Coverage |
|--------|----------------------|--------------------------------|-------------------|
| dark_periods.py | ~90 | ~75 (all enrichment logic) | ~83% |
| sts_detection.py | ~110 | ~90 (haversine, zone, risk, dedup) | ~82% |
| loitering.py | ~155 | ~120 (_group_episodes, _maybe_save, _classify_zone, _risk_level) | ~77% |
| spoofing.py | ~75 | ~60 (speed calc loop, haversine) | ~80% |
| screening.py | ~290 | ~200 (with mocked db calls; compute_vessel_score fully covered) | ~69% |

All projected values meet the success criteria thresholds. `screening.py` is the tightest
at ~69% vs the required 70%. The gap is closed by also testing `_detect_query_type`,
`_clean_imo`, `_clean_mmsi`, and `_annotate_hit` which are all trivially pure.

---

## State of the Art

| Old Pattern | Current Pattern | Impact |
|-------------|-----------------|--------|
| `mock.patch('db.fn')` | `mock.patch('screening.db.fn')` | Patches the name in the namespace that uses it; required for correct isolation |
| `os.environ.setdefault()` in conftest | `os.environ["key"] = value` at module level | Force-set guarantees override of CI env vars |
| pytest `tmp_path` fixture for DB | project-root SQLite db | Current pattern; use unique IMO strings to avoid collision |

---

## Open Questions

1. **Should `detect(positions)` for screening.py accept a pre-fetched indicator_inputs dict,
   or should it remain test-via-mock only?**
   - What we know: The 8-10 db calls in `compute_vessel_score()` are deeply interleaved with
     scoring logic; extraction would require significant refactoring.
   - What's unclear: Whether the Phase 4 regression safety net actually needs `compute_vessel_score()`
     to be pure, or whether mock-based tests are sufficient.
   - Recommendation: Use mock-based tests for `compute_vessel_score()`. This meets the
     coverage target without requiring a major refactor of the most complex function. The
     "pure detect(positions)" pattern in the roadmap is explicitly noted as different for
     `screening.py` in the plan text ("verify mock patch targets... with call_count assertions").

2. **Is pytest-cov already installable or does it need to be added to requirements.txt?**
   - What we know: `pip show pytest-cov` returns "not installed" in the current environment.
   - What's unclear: Whether the dev environment installs from `requirements.txt` or `pyproject.toml`.
   - Recommendation: Add `pytest-cov>=4.0` to `requirements.txt` under the `# --- dev / test ---`
     section alongside `pytest>=8.0`. Run `pip install pytest-cov` in Wave 0.

3. **Does loitering's `_get_low_speed_positions()` use `db._BACKEND` and `db._conn()` directly?**
   - What we know: Yes — lines 210-231 of loitering.py call `db._BACKEND`, `db._conn()`, and
     `db._cursor()` directly (the semi-private helpers re-exported from `db/__init__.py`).
   - Impact: The `detect(positions)` function for loitering must be a wrapper over
     `_group_episodes()` only; it must not call `_get_low_speed_positions()`. The pure function
     signature is `detect(positions: list[dict], sog_threshold_kt=2.0, min_hours=12.0)`.
   - Confidence: HIGH (directly read from source).

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INF (detection test coverage) | Each of the 5 detection modules exposes a pure detect(positions) function; pytest suite validates threshold boundary logic with synthetic AIS fixtures; conftest guards DATABASE_URL and AISSTREAM_API_KEY | Confirmed: no pure detect() exists in any module today; threshold constants documented; AIS data shapes documented; mock patch targets identified; factory patterns designed |
</phase_requirements>

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (already installed) |
| Config file | None currently — pyproject.toml has `[tool.ruff]` but no `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_dark_periods.py tests/test_sts_detection.py -x -q` |
| Full suite command | `pytest tests/ -q --cov=dark_periods --cov=sts_detection --cov=loitering --cov=spoofing --cov=screening --cov-report=term-missing` |

### Plan 03-01 Test IDs — Infrastructure Setup
| ID | Behavior | Test Type | Automated Command | File Exists? |
|----|----------|-----------|-------------------|-------------|
| T01 | `os.environ["DATABASE_URL"]` is empty string at session start | unit | `pytest tests/test_conftest_guards.py::test_database_url_cleared -x` | Wave 0 |
| T02 | `AISSTREAM_API_KEY` not in environment at session start | unit | `pytest tests/test_conftest_guards.py::test_aisstream_key_cleared -x` | Wave 0 |
| T03 | `ais_factory.make_gap()` returns dict with required keys | unit | `pytest tests/test_ais_factory.py::test_make_gap_keys -x` | Wave 0 |
| T04 | `ais_factory.make_position_sequence(count=5)` returns 5 dicts | unit | `pytest tests/test_ais_factory.py::test_make_sequence_count -x` | Wave 0 |
| T05 | `ais_factory.make_sts_pair()` returns dict with mmsi1/mmsi2 | unit | `pytest tests/test_ais_factory.py::test_make_sts_pair_keys -x` | Wave 0 |
| T06 | `ais_factory.make_consecutive_pair()` returns time_delta_min | unit | `pytest tests/test_ais_factory.py::test_make_consecutive_pair_keys -x` | Wave 0 |

### Plan 03-02 Test IDs — dark_periods and sts_detection
| ID | Behavior | Test Type | Automated Command | File Exists? |
|----|----------|-----------|-------------------|-------------|
| T07 | `dark_periods.detect([])` returns `[]` | unit | `pytest tests/test_dark_periods.py::test_detect_empty -x` | Wave 0 |
| T08 | Gap at `DARK_THRESHOLD_HOURS - 0.01` not detected | unit | `pytest tests/test_dark_periods.py::test_medium_below_threshold -x` | Wave 0 |
| T09 | Gap at `DARK_THRESHOLD_HOURS + 0.01` detected as MEDIUM | unit | `pytest tests/test_dark_periods.py::test_medium_at_threshold -x` | Wave 0 |
| T10 | Gap at `HIGH_RISK_HOURS + 0.01` detected as HIGH | unit | `pytest tests/test_dark_periods.py::test_high_at_threshold -x` | Wave 0 |
| T11 | Gap at `CRITICAL_HOURS + 0.01` detected as CRITICAL | unit | `pytest tests/test_dark_periods.py::test_critical_at_threshold -x` | Wave 0 |
| T12 | MEDIUM gap with coords inside Gulf of Oman zone upgraded to HIGH | unit | `pytest tests/test_dark_periods.py::test_zone_upgrade_medium_to_high -x` | Wave 0 |
| T13 | `dark_periods.detect()` returns no db calls (sanctions_hit=False) | unit | `pytest tests/test_dark_periods.py::test_detect_no_db -x` | Wave 0 |
| T14 | `sts_detection.detect([])` returns `[]` | unit | `pytest tests/test_sts_detection.py::test_detect_empty -x` | Wave 0 |
| T15 | Pair at `STS_DISTANCE_KM + 0.001` km apart not detected | unit | `pytest tests/test_sts_detection.py::test_distance_below_threshold -x` | Wave 0 |
| T16 | Pair at `STS_DISTANCE_KM - 0.001` km apart detected | unit | `pytest tests/test_sts_detection.py::test_distance_at_threshold -x` | Wave 0 |
| T17 | Both vessels at `MAX_SOG + 0.1` kt are not STS candidates | unit | `pytest tests/test_sts_detection.py::test_both_fast_not_detected -x` | Wave 0 |
| T18 | One vessel at `MAX_SOG - 0.1` kt qualifies as STS | unit | `pytest tests/test_sts_detection.py::test_one_slow_detected -x` | Wave 0 |
| T19 | Same pair within `DEDUP_HOURS` deduplicated to 1 event | unit | `pytest tests/test_sts_detection.py::test_deduplication -x` | Wave 0 |

### Plan 03-03 Test IDs — loitering, spoofing, screening
| ID | Behavior | Test Type | Automated Command | File Exists? |
|----|----------|-----------|-------------------|-------------|
| T20 | `loitering.detect([])` returns `[]` | unit | `pytest tests/test_loitering.py::test_detect_empty -x` | Wave 0 |
| T21 | Episode at `MIN_LOITER_HOURS - 0.1` h not recorded | unit | `pytest tests/test_loitering.py::test_episode_below_threshold -x` | Wave 0 |
| T22 | Episode at `MIN_LOITER_HOURS + 0.1` h recorded as MEDIUM | unit | `pytest tests/test_loitering.py::test_episode_at_threshold -x` | Wave 0 |
| T23 | Episode >= 48 h classified as CRITICAL | unit | `pytest tests/test_loitering.py::test_critical_loiter -x` | Wave 0 |
| T24 | 6h gap in position sequence breaks episode into two | unit | `pytest tests/test_loitering.py::test_gap_breaks_episode -x` | Wave 0 |
| T25 | Episode >= 12 h inside high-risk zone classified as HIGH | unit | `pytest tests/test_loitering.py::test_zone_triggers_high -x` | Wave 0 |
| T26 | `spoofing.detect([])` returns `[]` | unit | `pytest tests/test_spoofing.py::test_detect_empty -x` | Wave 0 |
| T27 | Pair at `SPEED_ANOMALY_THRESHOLD_KT - 1.0` kt not anomaly | unit | `pytest tests/test_spoofing.py::test_below_threshold_not_anomaly -x` | Wave 0 |
| T28 | Pair at `SPEED_ANOMALY_THRESHOLD_KT + 1.0` kt is anomaly | unit | `pytest tests/test_spoofing.py::test_above_threshold_is_anomaly -x` | Wave 0 |
| T29 | Zero time_delta_min not flagged (guard clause) | unit | `pytest tests/test_spoofing.py::test_zero_time_delta_ignored -x` | Wave 0 |
| T30 | `compute_vessel_score()` returns 100 when `search_sanctions_by_imo` is mocked with a hit | unit | `pytest tests/test_screening.py::test_sanctioned_score_is_100 -x` | Wave 0 |
| T31 | `compute_vessel_score()` returns 0 for vessel with no indicators | unit | `pytest tests/test_screening.py::test_no_indicators_score_is_0 -x` | Wave 0 |
| T32 | Flag tier 3 contributes 21 pts to composite score | unit | `pytest tests/test_screening.py::test_flag_tier3_score -x` | Wave 0 |
| T33 | `db.get_vessel_indicator_summary` called exactly once per `compute_vessel_score()` call when MMSI exists | unit | `pytest tests/test_screening.py::test_indicator_summary_call_count -x` | Wave 0 |
| T34 | `_detect_query_type("9876543")` returns "imo" | unit | `pytest tests/test_screening.py::test_query_type_imo -x` | Wave 0 |
| T35 | `_detect_query_type("123456789")` returns "mmsi" | unit | `pytest tests/test_screening.py::test_query_type_mmsi -x` | Wave 0 |
| T36 | All 5 new test files collected with no DATABASE_URL errors | integration | `pytest tests/ --co -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_dark_periods.py tests/test_sts_detection.py -x -q` (tasks 03-02), or equivalent for each task's new file
- **Per wave merge:** `pytest tests/ -q --cov=dark_periods --cov=sts_detection --cov=loitering --cov=spoofing --cov=screening --cov-report=term-missing`
- **Phase gate:** Full suite green with all coverage thresholds met before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/ais_factory.py` — synthetic position/gap/pair generators (plan 03-01)
- [ ] `tests/test_ais_factory.py` — factory self-tests T03-T06 (plan 03-01)
- [ ] `tests/test_conftest_guards.py` — env guard tests T01-T02 (plan 03-01)
- [ ] `tests/test_dark_periods.py` — T07-T13 (plan 03-02)
- [ ] `tests/test_sts_detection.py` — T14-T19 (plan 03-02)
- [ ] `tests/test_loitering.py` — T20-T25 (plan 03-03)
- [ ] `tests/test_spoofing.py` — T26-T29 (plan 03-03)
- [ ] `tests/test_screening.py` — T30-T36 (plan 03-03)
- [ ] Framework install: `pip install pytest-cov pydantic` — pydantic missing in current env
- [ ] dark_periods.detect() function — does not exist yet (plan 03-02 creates it)
- [ ] sts_detection.detect() function — does not exist yet (plan 03-02 creates it)
- [ ] loitering.detect() function — does not exist yet (plan 03-03 creates it)
- [ ] spoofing.detect() function — does not exist yet (plan 03-03 creates it)

---

## Sources

### Primary (HIGH confidence)
- Direct source code read of `dark_periods.py`, `sts_detection.py`, `loitering.py`, `spoofing.py`, `screening.py`, `risk_config.py`, `schemas.py`, `db/__init__.py`, `db/connection.py`, `db/findings.py`, `db/scores.py`
- Direct read of all existing test files: `tests/conftest.py`, `tests/test_scores.py`, `tests/test_db_package.py`, `tests/test_inf3_anthropic.py`, `tests/test_inf4_startup.py`
- `pyproject.toml` and `requirements.txt` for dependency versions
- `pytest --version` output: 9.0.2 confirmed installed
- `pytest --co -q tests/` output: 20 tests collected, collection confirmed working
- `pytest tests/ -q` run: 18 pass, 2 fail (pydantic not installed)
- `pip show pytest-cov`: not installed

### Secondary (MEDIUM confidence)
- pytest documentation patterns for `monkeypatch.setenv` and `unittest.mock.patch` — standard Python testing knowledge, HIGH confidence
- `mock.patch` target naming convention (patch where used, not where defined) — standard Python testing knowledge, HIGH confidence

---

## Metadata

**Confidence breakdown:**
- Threshold constants: HIGH — read directly from source code
- AIS position shapes: HIGH — read directly from source code and db schema
- Mock patch targets: HIGH — import graph traced by reading screening.py line-by-line
- Coverage projections: MEDIUM — estimated from line counts; actual coverage depends on branch coverage in pytest-cov
- Factory design: HIGH — derived from actual data shapes consumed by each module

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (stable codebase; source code is the ground truth)
