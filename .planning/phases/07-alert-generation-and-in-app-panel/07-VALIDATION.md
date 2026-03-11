---
phase: 7
slug: alert-generation-and-in-app-panel
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-10
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `pytest tests/test_alerts.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~6 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_alerts.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~6 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 7-00-01 | 00 | 0 | ALRT-01…08 | stub | `pytest tests/test_alerts.py -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-01 | 01 | 1 | ALRT-01 | integration | `pytest tests/test_alerts.py::test_unread_count_endpoint -x -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-02 | 01 | 1 | ALRT-02, ALRT-03 | integration | `pytest tests/test_alerts.py::test_get_alerts_shape tests/test_alerts.py::test_alert_detail_fields -x -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-03 | 01 | 1 | ALRT-04 | unit | `pytest tests/test_alerts.py::test_risk_level_crossing_alert -x -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-04 | 01 | 1 | ALRT-05 | unit | `pytest tests/test_alerts.py::test_top_50_entry_alert -x -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-05 | 01 | 1 | ALRT-06 | unit | `pytest tests/test_alerts.py::test_sanctions_flip_alert -x -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-06 | 01 | 1 | ALRT-07 | unit | `pytest tests/test_alerts.py::test_score_spike_alert -x -q` | ❌ Wave 0 | ⬜ pending |
| 7-01-07 | 01 | 1 | ALRT-08 | integration | `pytest tests/test_alerts.py::test_mark_alert_read -x -q` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_alerts.py` — 8 stubs covering ALRT-01 through ALRT-08
- [ ] IMO range `IMO9000001+` reserved (avoids collision with Phases 2-6)
- [ ] No new conftest needed — existing `conftest.py` provides `app_client`

*Wave 0 creates `tests/test_alerts.py` with `pytest.fail()` stubs before any implementation begins.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Badge appears in dashboard header after alert generation | ALRT-01 | Requires live page render | Load dashboard, verify badge element is visible when alerts exist |
| Alert panel opens on badge click and shows alert list | ALRT-02 | Browser interaction | Click badge, verify panel slides in with vessel names + alert types |
| Alert detail expands on click | ALRT-03 | Browser interaction | Click alert row, verify before/after scores + indicator names appear |
| Alert generation fires on real APScheduler tick | ALRT-04 to ALRT-07 | Requires live scheduler run | Restart app, wait 15 min, query alerts table |
| Read section visible after marking an alert read | ALRT-08 | Browser interaction | Click Mark as Read, verify alert moves to read section |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** 2026-03-10
