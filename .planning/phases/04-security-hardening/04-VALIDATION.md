---
phase: 4
slug: security-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | None detected — runs via `pytest tests/` |
| **Quick run command** | `pytest tests/test_security.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_security.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | SEC-4 | template scan | `pytest tests/test_security.py::test_login_template_has_csrf_token -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | SEC-4 | static analysis | `pytest tests/test_security.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | SEC-1 | unit | `pytest tests/test_security.py::test_login_rate_limit_allows_first_request tests/test_security.py::test_login_rate_limit_blocks_11th_request -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | SEC-2 | unit | `pytest tests/test_security.py::test_login_requires_csrf_token tests/test_security.py::test_api_screen_csrf_exempt -x` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 2 | SEC-3 | unit | `pytest tests/test_security.py::test_security_headers_xframe tests/test_security.py::test_security_headers_xcto tests/test_security.py::test_csp_header_present -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 3 | SEC-3 | unit | `pytest tests/test_security.py::test_security_headers_hsts -x` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 3 | SEC-4 | manual | Browser DevTools — no CSP violations in console | Manual | ⬜ pending |
| 04-03-03 | 03 | 3 | SEC-5 | manual | GitHub Security tab — 7 alerts show "Dismissed" | Manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_security.py` — T01-T10, T12 test stubs (new file, does not exist)
- [ ] `app_client` fixture in `tests/conftest.py` — Flask test client with security extensions initialized

*Existing pytest + conftest infrastructure is sufficient. Only a new test file and one new conftest fixture are needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboard renders without CSP violations | SEC-4 | Requires real browser making CDN/tile requests | Open DevTools Console after Railway deploy; filter for CSP errors |
| 7 CodeQL alerts show "Dismissed" | SEC-5 | GitHub Security tab UI action | Navigate to Security → Code scanning → verify each alert is dismissed |

---

## Test IDs Reference

| Test ID | Test Name | Requirement |
|---------|-----------|-------------|
| T01 | test_login_rate_limit_allows_first_request | SEC-1 |
| T02 | test_login_rate_limit_blocks_11th_request | SEC-1 |
| T03 | test_proxyfix_sets_remote_addr | SEC-1 |
| T04 | test_login_requires_csrf_token | SEC-2 |
| T05 | test_api_screen_csrf_exempt | SEC-2 |
| T06 | test_all_api_routes_csrf_exempt | SEC-2 |
| T07 | test_security_headers_xframe | SEC-3 |
| T08 | test_security_headers_xcto | SEC-3 |
| T09 | test_security_headers_hsts | SEC-3 |
| T10 | test_csp_header_present | SEC-3/SEC-4 |
| T11 | (manual) CSP no violations in browser | SEC-4 |
| T12 | test_login_template_has_csrf_token | SEC-2/SEC-4 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
