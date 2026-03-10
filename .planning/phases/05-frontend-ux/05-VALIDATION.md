---
phase: 5
slug: frontend-ux
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-09
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (no `[tool.pytest]` section — uses defaults) |
| **Quick run command** | `pytest tests/test_fe.py -x -q` |
| **Full suite command** | `pytest tests/ --cov=. --cov-report=term-missing` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_fe.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | FE-5 | integration | `pytest tests/test_fe.py::test_vessel_permalink -x` | ❌ Wave 0 | ⬜ pending |
| 5-01-02 | 01 | 1 | FE-3 | integration | `pytest tests/test_fe.py::test_stale_flag -x` | ❌ Wave 0 | ⬜ pending |
| 5-02-01 | 02 | 1 | FE-1 | integration | `pytest tests/test_fe.py::test_ranking_sort -x` | ❌ Wave 0 | ⬜ pending |
| 5-02-02 | 02 | 1 | FE-2 | unit | `pytest tests/test_fe.py::test_map_data_score -x` | ❌ Wave 0 | ⬜ pending |
| 5-03-01 | 03 | 2 | FE-4 | integration | `pytest tests/test_fe.py::test_indicator_json -x` | ❌ Wave 0 | ⬜ pending |
| 5-03-02 | 03 | 2 | FE-6 | integration | `pytest tests/test_fe.py::test_csv_export -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_fe.py` — covers FE-1 through FE-6; uses existing `conftest.py` fixtures (`app_client`)
- [ ] No new conftest needed — existing `conftest.py` already provides `app_client` and DB setup

*Wave 0 must create `tests/test_fe.py` with all 6 test stubs before any other plan executes.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Ranking table renders correctly in browser | FE-1 | Requires visual inspection of HTML table layout | Open dashboard, verify columns, click headers to sort |
| Numeric score visible in map popup | FE-2 | Requires Leaflet map render + click | Click vessel on map, verify score line in popup |
| Stale badge renders in amber | FE-3 | CSS rendering | Force `is_stale=True` on a vessel, load profile |
| Indicator breakdown shows fired/not-fired | FE-4 | Visual layout verification | Open vessel profile, verify 31 rows, check highlights |
| CSV downloads with correct columns | FE-6 | Browser download behavior | Click Export CSV, open file, verify column headers |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-09
