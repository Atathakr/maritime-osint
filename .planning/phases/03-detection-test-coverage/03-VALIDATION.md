# Phase 3: Detection Test Coverage — Validation Strategy

**Phase:** 03-detection-test-coverage
**Created:** 2026-03-05
**Nyquist Rule:** Every automated test has a named ID; every plan task has a verify command.

---

## Test ID Registry

All 36 test IDs for this phase. Each maps to a specific file, function, and plan.

### Plan 03-01 — Infrastructure (T01-T06)

| ID | Test Function | File | What It Proves |
|----|---------------|------|----------------|
| T01 | `test_database_url_cleared` | `tests/test_conftest_guards.py` | `DATABASE_URL=""` in env at session start — CI env override is prevented |
| T02 | `test_aisstream_key_cleared` | `tests/test_conftest_guards.py` | `AISSTREAM_API_KEY` absent from env — no live WebSocket connection risk |
| T03 | `test_make_gap_keys` | `tests/test_ais_factory.py` | `make_gap()` returns all required dark_periods input keys |
| T04 | `test_make_sequence_count` | `tests/test_ais_factory.py` | `make_position_sequence(count=5)` returns exactly 5 correctly-shaped dicts |
| T05 | `test_make_sts_pair_keys` | `tests/test_ais_factory.py` | `make_sts_pair()` returns all required STS candidate pair keys |
| T06 | `test_make_consecutive_pair_keys` | `tests/test_ais_factory.py` | `make_consecutive_pair()` returns `time_delta_min` and `next_lat`/`next_lon` |

**Run command:**
```bash
pytest tests/test_conftest_guards.py tests/test_ais_factory.py -x -q
```

**Expected:** 6 passed, 0 failed.

---

### Plan 03-02 — dark_periods + sts_detection (T07-T19)

| ID | Test Function | File | Threshold Tested | Direction |
|----|---------------|------|------------------|-----------|
| T07 | `test_detect_empty` | `tests/test_dark_periods.py` | — | Empty input returns [] |
| T08 | `test_medium_below_threshold` | `tests/test_dark_periods.py` | `DARK_THRESHOLD_HOURS - 0.01` | Below → NOT detected |
| T09 | `test_medium_at_threshold` | `tests/test_dark_periods.py` | `DARK_THRESHOLD_HOURS + 0.01` | Above → MEDIUM |
| T10 | `test_high_at_threshold` | `tests/test_dark_periods.py` | `HIGH_RISK_HOURS + 0.01` | Above → HIGH |
| T11 | `test_critical_at_threshold` | `tests/test_dark_periods.py` | `CRITICAL_HOURS + 0.01` | Above → CRITICAL |
| T12 | `test_zone_upgrade_medium_to_high` | `tests/test_dark_periods.py` | 3.0h + Gulf of Oman coords | Zone upgrade MEDIUM → HIGH |
| T13 | `test_detect_no_db` | `tests/test_dark_periods.py` | — | `sanctions_hit=False` always |
| T14 | `test_detect_empty` | `tests/test_sts_detection.py` | — | Empty input returns [] |
| T15 | `test_distance_above_threshold_not_detected` | `tests/test_sts_detection.py` | `STS_DISTANCE_KM + delta` | Too far → NOT detected |
| T16 | `test_distance_within_threshold_detected` | `tests/test_sts_detection.py` | `STS_DISTANCE_KM - delta` | Close enough → detected |
| T17 | `test_both_fast_not_detected` | `tests/test_sts_detection.py` | Both `> MAX_SOG` | Both fast → NOT detected |
| T18 | `test_one_slow_detected` | `tests/test_sts_detection.py` | One `<= MAX_SOG` | One slow → detected |
| T19 | `test_deduplication` | `tests/test_sts_detection.py` | Same pair within `DEDUP_HOURS` | Deduplicated to 1 event |

**Run command:**
```bash
pytest tests/test_dark_periods.py tests/test_sts_detection.py -x -q
```

**Expected:** 13 passed, 0 failed.

**Coverage gate (run after task completion):**
```bash
pytest tests/ -q --cov=dark_periods --cov=sts_detection --cov-report=term-missing
```
- dark_periods: >= 80%
- sts_detection: >= 80%

---

### Plan 03-03 — loitering + spoofing + screening (T20-T36)

| ID | Test Function | File | Threshold Tested | Direction |
|----|---------------|------|------------------|-----------|
| T20 | `test_detect_empty` | `tests/test_loitering.py` | — | Empty input returns [] |
| T21 | `test_episode_below_threshold` | `tests/test_loitering.py` | 11.0h < `MIN_LOITER_HOURS` | Below → NOT recorded |
| T22 | `test_episode_at_threshold` | `tests/test_loitering.py` | 13.0h > `MIN_LOITER_HOURS` | Above → MEDIUM |
| T23 | `test_critical_loiter` | `tests/test_loitering.py` | >= 48h | 48h+ → CRITICAL |
| T24 | `test_gap_breaks_episode` | `tests/test_loitering.py` | >6h gap between positions | Gap → 2 separate episodes |
| T25 | `test_zone_triggers_high` | `tests/test_loitering.py` | `MIN_LOITER_HOURS` + Gulf of Oman | Zone → HIGH |
| T26 | `test_detect_empty` | `tests/test_spoofing.py` | — | Empty input returns [] |
| T27 | `test_below_threshold_not_anomaly` | `tests/test_spoofing.py` | ~9 kt < `SPEED_ANOMALY_THRESHOLD_KT` | Below → NOT anomaly |
| T28 | `test_above_threshold_is_anomaly` | `tests/test_spoofing.py` | ~157 kt > `SPEED_ANOMALY_THRESHOLD_KT` | Above → anomaly |
| T29 | `test_zero_time_delta_ignored` | `tests/test_spoofing.py` | `time_delta_min=0` | Zero time → skipped |
| T30 | `test_sanctioned_score_is_100` | `tests/test_screening.py` | `search_sanctions_by_imo` returns hit | Sanctions → score=100, is_sanctioned=True |
| T31 | `test_no_indicators_score_low` | `tests/test_screening.py` | All db mocks return empty | No indicators → score <= 15 |
| T32 | `test_flag_tier3_score` | `tests/test_screening.py` | `flag_state="IR"` (tier 3) | Flag tier 3 → points > 0 |
| T33 | `test_indicator_summary_call_count` | `tests/test_screening.py` | — | `get_vessel_indicator_summary` called <= 2 times |
| T34 | `test_query_type_imo` | `tests/test_screening.py` | `"9876543"` (7 digits) | → "imo" |
| T35 | `test_query_type_mmsi` | `tests/test_screening.py` | `"123456789"` (9 digits) | → "mmsi" |
| T36 | `test_all_test_files_collected` | `tests/test_screening.py` | — | All 5 test files collected, no import errors |

**Run command:**
```bash
pytest tests/test_loitering.py tests/test_spoofing.py tests/test_screening.py -x -q
```

**Expected:** 17 passed, 0 failed.

---

## Coverage Gates

Final phase gate command (runs after all 3 plans complete):

```bash
pytest tests/ -q \
  --cov=dark_periods \
  --cov=sts_detection \
  --cov=loitering \
  --cov=spoofing \
  --cov=screening \
  --cov-report=term-missing
```

| Module | Required | Projected | Margin |
|--------|----------|-----------|--------|
| dark_periods.py | >= 80% | ~83% | +3% |
| sts_detection.py | >= 80% | ~82% | +2% |
| loitering.py | >= 75% | ~77% | +2% |
| spoofing.py | >= 75% | ~80% | +5% |
| screening.py | >= 70% | ~69-72% | tight |

**Screening.py is the tightest.** If coverage falls below 70%, add tests for the trivially pure helpers:
- `screening._clean_imo(raw)` — strips "IMO" prefix and whitespace
- `screening._clean_mmsi(raw)` — strips whitespace
- `screening._annotate_hit(hit, query_type)` — pure dict mutation

These are all single-line functions; each adds ~0.3% coverage.

---

## Sampling Strategy

### Per-task verification (within each plan)

Each task runs its own file's tests immediately after implementation:

| Plan | Task | Verify Command |
|------|------|----------------|
| 03-01 | Task 2 | `pytest tests/test_conftest_guards.py tests/test_ais_factory.py -x -q` |
| 03-02 | Task 1 | `pytest tests/test_dark_periods.py -x -q` |
| 03-02 | Task 2 | `pytest tests/test_dark_periods.py tests/test_sts_detection.py -x -q` |
| 03-03 | Task 1 | `pytest tests/test_loitering.py tests/test_spoofing.py -x -q` |
| 03-03 | Task 2 | `pytest tests/ -q --cov=... --cov-report=term-missing` (full coverage gate) |

### Per-wave verification (after all tasks in a plan complete)

| Plan | Wave verify command |
|------|---------------------|
| 03-01 | `pytest tests/ -q` (full suite, no regressions) |
| 03-02 | `pytest tests/ -q --cov=dark_periods --cov=sts_detection --cov-report=term-missing` |
| 03-03 | `pytest tests/ -q --cov=dark_periods --cov=sts_detection --cov=loitering --cov=spoofing --cov=screening --cov-report=term-missing` |

### Phase gate (before `/gsd:verify-work 3`)

Full suite green, all 5 coverage thresholds met, no DATABASE_URL errors in any run.

---

## Mock Patch Targets — Screening (Critical Reference)

All `compute_vessel_score()` test patches MUST use `screening.db.*` — NOT `db.*`.

```python
# CORRECT: patches the name as used in screening.py's namespace
patch("screening.db.get_vessel", ...)
patch("screening.db.search_sanctions_by_imo", ...)

# WRONG: patches the db module directly — screening.py's local reference is NOT affected
patch("db.get_vessel", ...)           # will NOT isolate screening.py
patch("db.search_sanctions_by_imo", ...)  # will NOT isolate screening.py
```

This is standard Python mock.patch behavior: patch where the name is **used**, not where it is **defined**.

---

## What to Verify Per Plan

### Plan 03-01 checklist

- [ ] `requirements.txt` contains `pydantic>=2.0.0` and `pytest-cov>=4.0`
- [ ] `python -c "import pydantic; import pytest_cov"` prints no errors
- [ ] `tests/conftest.py` uses `os.environ["DATABASE_URL"] = ""` (not `setdefault`)
- [ ] `tests/conftest.py` calls `os.environ.pop("AISSTREAM_API_KEY", None)`
- [ ] `tests/ais_factory.py` exists with all 4 factory functions
- [ ] Previously failing `test_score_is_stale_age` and `test_score_is_stale_flag` now pass
- [ ] T01-T06 pass (6 tests)

### Plan 03-02 checklist

- [ ] `dark_periods.detect` callable: `python -c "import dark_periods; dark_periods.detect([])"`
- [ ] `dark_periods.DARK_THRESHOLD_HOURS`, `HIGH_RISK_HOURS`, `CRITICAL_HOURS` accessible at module level
- [ ] `dark_periods.run_detection` still present (not removed)
- [ ] `sts_detection.detect` callable: `python -c "import sts_detection; sts_detection.detect([])"`
- [ ] `sts_detection.STS_DISTANCE_KM`, `MAX_SOG`, `DEDUP_HOURS` accessible at module level
- [ ] `sts_detection.run_detection` still present (not removed)
- [ ] T07-T19 pass (13 tests)
- [ ] dark_periods coverage >= 80%, sts_detection coverage >= 80%

### Plan 03-03 checklist

- [ ] `loitering.detect` callable: `python -c "import loitering; loitering.detect([])"`
- [ ] `loitering.SOG_THRESHOLD_KT`, `MIN_LOITER_HOURS` accessible at module level
- [ ] `loitering.run_loitering_detection` still present (not removed)
- [ ] `spoofing.detect` callable: `python -c "import spoofing; spoofing.detect([])"`
- [ ] `spoofing.detect` accepts optional `threshold_kt` parameter
- [ ] `spoofing.detect_speed_anomalies` still present (not removed)
- [ ] `tests/test_screening.py` uses `screening.db.*` patch targets throughout
- [ ] T20-T36 pass (17 tests)
- [ ] Full coverage gate: dark_periods >= 80%, sts_detection >= 80%, loitering >= 75%, spoofing >= 75%, screening >= 70%
- [ ] `pytest tests/ -q` → 0 failures (36 new tests + all prior 20+ tests)

---

## Known Pitfalls (From Research)

| Pitfall | Guard |
|---------|-------|
| `setdefault` in conftest doesn't override CI env | Use `os.environ["DATABASE_URL"] = ""` (force-set) |
| Mock patching `db.*` instead of `screening.db.*` | Always target `screening.db.FUNCTION_NAME` |
| `sanctions_hit=True` asserted in pure detect() tests | Never assert `sanctions_hit=True` — pure functions always return False |
| SQLite DB collision with Phase 2 test data | Phase 3 db-touching tests use IMO7000001+ (Phase 2 used up to IMO6666666) |
| pydantic not installed causes import failures | Fixed in plan 03-01 Task 1 |
| `loitering.detect()` calling `_get_low_speed_positions()` | detect() MUST call `_group_episodes()` only — not `_get_low_speed_positions()` |
| `time_delta_min=0` causing division by zero in spoofing | Guard clause required in `detect()` |
