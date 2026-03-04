---
phase: 2
slug: pre-computed-risk-scores
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | none — discovered via `tests/` directory convention |
| **Quick run command** | `pytest tests/test_scores.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds (quick), ~15 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_scores.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | DB-1 | unit | `pytest tests/test_scores.py::test_init_scores_tables -x` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | DB-1 | unit | `pytest tests/test_scores.py::test_upsert_vessel_score -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 1 | DB-1 | unit | `pytest tests/test_scores.py::test_get_vessel_score -x` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 1 | DB-2 | unit | `pytest tests/test_scores.py::test_append_score_history -x` | ❌ W0 | ⬜ pending |
| 2-01-05 | 01 | 1 | DB-2 | unit | `pytest tests/test_scores.py::test_prune_score_history -x` | ❌ W0 | ⬜ pending |
| 2-01-06 | 01 | 1 | DB-4 | unit | `pytest tests/test_scores.py::test_score_is_stale_age -x` | ❌ W0 | ⬜ pending |
| 2-01-07 | 01 | 1 | DB-4 | unit | `pytest tests/test_scores.py::test_score_is_stale_flag -x` | ❌ W0 | ⬜ pending |
| 2-01-08 | 01 | 1 | DB-5 | unit | `pytest tests/test_scores.py::test_mark_risk_scores_stale -x` | ❌ W0 | ⬜ pending |
| 2-01-09 | 01 | 1 | DB-5 | unit | `pytest tests/test_scores.py::test_upsert_clears_stale -x` | ❌ W0 | ⬜ pending |
| 2-01-10 | 01 | 1 | INF-1 | unit | `pytest tests/test_scores.py::test_get_all_vessel_scores -x` | ❌ W0 | ⬜ pending |
| 2-01-11 | 01 | 1 | INF-2 | unit | `pytest tests/test_scores.py::test_archive_old_ais_positions -x` | ❌ W0 | ⬜ pending |
| 2-01-12 | 01 | 1 | DB-1 | unit | `pytest tests/test_db_package.py::test_all_public_functions_exported -x` | ✅ exists | ⬜ pending |
| 2-02-01 | 02 | 2 | DB-1 | manual | App starts; scheduler jobs appear in logs within 15 min | N/A | ⬜ pending |
| 2-03-01 | 03 | 3 | DB-4 | unit | `pytest tests/test_scores.py -x -q` (staleness fallback path) | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 3 | DB-5 | unit | `pytest tests/test_scores.py::test_mark_risk_scores_stale -x` | ❌ W0 | ⬜ pending |
| 2-04-01 | 04 | 4 | INF-1 | unit | `pytest tests/test_scores.py::test_get_all_vessel_scores -x` | ❌ W0 | ⬜ pending |
| 2-04-02 | 04 | 4 | INF-1 | manual | `/api/vessels/ranking` responds in <500ms with 100+ vessels | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_scores.py` — stubs for all DB-1, DB-2, DB-4, DB-5, INF-1, INF-2 test IDs above; uses `tmp_path` fixture + `monkeypatch.setenv("DATABASE_URL", "")` for SQLite isolation
- [ ] `tests/test_db_package.py` — existing file; `PUBLIC_FUNCTIONS` list updated to include 8 new scores function exports (after Plan 02-01 fills db/scores.py)

*Existing `tests/conftest.py` already sets `DATABASE_URL=''` — no conftest changes needed.*
*pytest is already installed (`pytest>=8.0` in requirements.txt).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| APScheduler starts and fires score refresh job | DB-1 | Background thread; no HTTP endpoint to query | Deploy to Railway; check logs for `[scheduler] score refresh complete` within 15 min |
| Dashboard endpoint responds in <500ms for full fleet | INF-1 | Requires real data; performance regression hard to unit-test | Hit `/api/vessels/ranking` with curl, observe response time |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
