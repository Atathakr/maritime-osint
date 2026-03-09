"""
tests/test_security.py — Security hardening test suite (Phase 4)

Wave 0: All tests are failing stubs. Wave 2 implementation makes them pass.
Test IDs T01-T12 map to 04-VALIDATION.md.
T11 is manual-only (browser CSP check) — not represented here.
"""
import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _login_post(client, with_csrf=False, ip="127.0.0.1"):
    """POST /login with optional csrf_token field."""
    data = {"password": "testpass"}
    if with_csrf:
        # csrf_token value does not matter when WTF_CSRF_ENABLED=False
        data["csrf_token"] = "stub"
    return client.post(
        "/login",
        data=data,
        environ_base={"REMOTE_ADDR": ip},
    )


# ── SEC-1: Rate Limiting ──────────────────────────────────────────────────────

def test_login_rate_limit_allows_first_request(app_client):
    """T01 — first POST /login must not be rate-limited (200 or 302, not 429)."""
    pytest.fail("STUB — security.py not yet implemented (T01)")


def test_login_rate_limit_blocks_11th_request(app_client):
    """T02 — 11th POST /login within 1 minute must return 429."""
    pytest.fail("STUB — security.py not yet implemented (T02)")


def test_proxyfix_sets_remote_addr(app_client):
    """T03 — X-Forwarded-For header must populate request.remote_addr via ProxyFix."""
    pytest.fail("STUB — ProxyFix not yet applied in app.py (T03)")


# ── SEC-2: CSRF ───────────────────────────────────────────────────────────────

def test_login_requires_csrf_token(app_client):
    """T04 — POST /login without csrf_token must return 400 when CSRF is active."""
    pytest.fail("STUB — CSRFProtect not yet initialized (T04)")


def test_api_screen_csrf_exempt(app_client):
    """T05 — POST /api/screen without csrf_token must not return 400 (API is exempt)."""
    pytest.fail("STUB — @csrf.exempt not yet applied to api_screen (T05)")


def test_all_api_routes_csrf_exempt(app_client):
    """T06 — All 13 /api/* POST view functions must carry csrf.exempt attribute."""
    pytest.fail("STUB — @csrf.exempt not yet applied to /api/* routes (T06)")


# ── SEC-3: Security Headers ───────────────────────────────────────────────────

def test_security_headers_xframe(app_client):
    """T07 — Every response must include X-Frame-Options: DENY."""
    pytest.fail("STUB — Flask-Talisman not yet initialized (T07)")


def test_security_headers_xcto(app_client):
    """T08 — Every response must include X-Content-Type-Options: nosniff."""
    pytest.fail("STUB — Flask-Talisman not yet initialized (T08)")


def test_security_headers_hsts(app_client):
    """T09 — Every response must include Strict-Transport-Security with max-age."""
    pytest.fail("STUB — Flask-Talisman not yet initialized (T09)")


def test_csp_header_present(app_client):
    """T10 — Every response must include CSP or CSP-Report-Only header."""
    pytest.fail("STUB — Flask-Talisman not yet initialized (T10)")


# ── SEC-4: Template Audit ─────────────────────────────────────────────────────

def test_login_template_has_csrf_token(app_client):
    """T12 — templates/login.html must contain csrf_token hidden input."""
    pytest.fail("STUB — csrf_token not yet added to login.html (T12)")
