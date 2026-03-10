---
phase: 6
slug: score-history-infrastructure
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-10
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (existing, no `[tool.pytest]` section) |
| **Quick run command** | `pytest tests/test_hist.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_hist.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 6-00-01 | 00 | 0 | HIST-01, HIST-02 | stub | `pytest tests/test_hist.py -q` | ❌ Wave 0 | ⬜ pending |
| 6-01-01 | 01 | 1 | HIST-01 | integration | `pytest tests/test_hist.py::test_history_row_written -x -q` | ❌ Wave 0 | ⬜ pending |
| 6-01-02 | 01 | 1 | HIST-01 | integration | `pytest tests/test_hist.py::test_no_spurious_row -x -q` | ❌ Wave 0 | ⬜ pending |
| 6-01-03 | 01 | 1 | HIST-02 | integration | `pytest tests/test_hist.py::test_history_endpoint -x -q` | ❌ Wave 0 | ⬜ pending |
| 6-01-04 | 01 | 1 | HIST-02 | integration | `pytest tests/test_hist.py::test_history_endpoint_404 -x -q` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_hist.py` — 4 stubs covering HIST-01 and HIST-02
- [ ] No new conftest needed — existing `conftest.py` provides `app_client` and DB setup

*Wave 0 creates `tests/test_hist.py` with `pytest.fail()` stubs before any implementation begins.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| History row created during live APScheduler run | HIST-01 | Requires real scheduler tick | Restart app, wait 15 min, query vessel_score_history table |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** 2026-03-10
