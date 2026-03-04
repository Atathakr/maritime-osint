---
phase: 1
slug: database-decomposition
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (not yet installed — Wave 0 installs) |
| **Config file** | none — Wave 0 creates `tests/` from scratch |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds (startup subprocess tests dominate) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-W0-01 | 01 | 0 | DB-3 | smoke | `python -m pytest tests/test_db_package.py::test_import_and_init -x` | ❌ W0 | ⬜ pending |
| 1-W0-02 | 01 | 0 | DB-3 | unit | `python -m pytest tests/test_db_package.py::test_all_public_functions_exported -x` | ❌ W0 | ⬜ pending |
| 1-W0-03 | 01 | 0 | DB-3 | unit | `python -m pytest tests/test_db_package.py::test_private_helpers_exported -x` | ❌ W0 | ⬜ pending |
| 1-W0-04 | 01 | 0 | INF-4 | unit | `python -m pytest tests/test_inf4_startup.py::test_missing_secret_key -x` | ❌ W0 | ⬜ pending |
| 1-W0-05 | 01 | 0 | INF-4 | unit | `python -m pytest tests/test_inf4_startup.py::test_missing_app_password -x` | ❌ W0 | ⬜ pending |
| 1-W0-06 | 01 | 0 | INF-3 | static | `python -m pytest tests/test_inf3_anthropic.py -x` | ❌ W0 | ⬜ pending |
| TBD-db3a | TBD | TBD | DB-3 | smoke | `python -m pytest tests/test_db_package.py::test_import_and_init -x` | ❌ W0 | ⬜ pending |
| TBD-db3b | TBD | TBD | DB-3 | unit | `python -m pytest tests/test_db_package.py::test_all_public_functions_exported -x` | ❌ W0 | ⬜ pending |
| TBD-db3c | TBD | TBD | DB-3 | unit | `python -m pytest tests/test_db_package.py::test_private_helpers_exported -x` | ❌ W0 | ⬜ pending |
| TBD-inf4a | TBD | TBD | INF-4 | unit | `python -m pytest tests/test_inf4_startup.py::test_missing_secret_key -x` | ❌ W0 | ⬜ pending |
| TBD-inf4b | TBD | TBD | INF-4 | unit | `python -m pytest tests/test_inf4_startup.py::test_missing_app_password -x` | ❌ W0 | ⬜ pending |
| TBD-inf3 | TBD | TBD | INF-3 | static | `python -m pytest tests/test_inf3_anthropic.py -x` | ❌ W0 | ⬜ pending |

*Note: `TBD-*` rows have Plan/Wave IDs assigned once PLAN.md is created. Wave 0 rows (`1-W0-*`) are tasks within Plan 01 that create the test stubs before any code changes.*

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/` directory
- [ ] `tests/__init__.py` — empty
- [ ] `tests/conftest.py` — sets `DATABASE_URL=""` before any db import
- [ ] `tests/test_db_package.py` — covers DB-3 (import, re-exports, private helpers)
- [ ] `tests/test_inf4_startup.py` — covers INF-4 (startup enforcement for SECRET_KEY + APP_PASSWORD)
- [ ] `tests/test_inf3_anthropic.py` — covers INF-3 (no anthropic in requirements.txt, pyproject.toml, or source)
- [ ] Framework install: `pip install pytest` (add pytest to `requirements.txt` or `pyproject.toml [dev]`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Railway deploy succeeds after full db/ extraction | DB-3 | Cannot automate CI Railway deploy in pytest; requires live Railway environment | 1. Push branch to GitHub. 2. Trigger Railway deploy. 3. Confirm deployment succeeds (no import errors in build log). 4. Load dashboard URL — verify it renders. 5. Run a vessel search — verify results return. |
| `python app.py` starts clean on local SQLite after each sub-module extraction | DB-3 | Each extraction has a manual smoke step before committing | 1. After each sub-module extraction, run `python app.py` from project root. 2. Load `http://localhost:5000`. 3. Confirm no AttributeError or ImportError in terminal. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
