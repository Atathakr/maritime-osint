---
phase: 8
slug: vessel-profile-enrichments
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (auto-discovers `tests/` directory) |
| **Config file** | none — pytest auto-discovers `tests/` directory |
| **Quick run command** | `pytest tests/test_profile_enrichments.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_profile_enrichments.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 8-00-01 | 00 | 0 | PROF-01 | smoke | `pytest tests/test_profile_enrichments.py::test_profile_has_history_card -x` | ❌ W0 | ⬜ pending |
| 8-00-02 | 00 | 0 | PROF-01 | unit (API) | `pytest tests/test_profile_enrichments.py::test_history_single_snapshot -x` | ❌ W0 | ⬜ pending |
| 8-00-03 | 00 | 0 | PROF-02 | unit (logic) | `pytest tests/test_profile_enrichments.py::test_change_log_diff -x` | ❌ W0 | ⬜ pending |
| 8-00-04 | 00 | 0 | PROF-02 | unit (logic) | `pytest tests/test_profile_enrichments.py::test_change_log_identical_snapshots -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_profile_enrichments.py` — 4 failing stubs covering PROF-01 (HTML structure + single-snapshot API) and PROF-02 (change log diff logic + identical-snapshot case)
- [ ] No new fixtures or conftest changes needed — `app_client` from `tests/conftest.py` covers HTTP tests; pure-logic tests need no fixtures

*No framework install gap — pytest already in use with 151+ passing tests.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chart.js renders correct trend line with risk-colored points | PROF-01 | Browser-side JS; pytest cannot execute Chart.js | Load `/vessel/<imo>` with ≥2 history rows; verify chart appears, y-axis 0-100, points colored by risk level |
| Hover tooltip shows score + risk level + relative timestamp | PROF-01 | Browser interaction required | Hover over chart data point; verify tooltip format |
| Change log direction arrow correct (▲ / ▼) | PROF-02 | DOM rendering check | Load profile with score increase; verify ▲. Load with decrease; verify ▼ |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
