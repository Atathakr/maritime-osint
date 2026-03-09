"""
tests/test_security.py — Security hardening test suite (Phase 4)

Wave 2: All stubs replaced with real assertions. Tests pass once security.py,
app.py decorators, and login.html csrf_token are implemented.
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
    from security import limiter
    limiter.reset()
    resp = _login_post(app_client)
    assert resp.status_code in (200, 302), (
        f"Expected 200 or 302 on first /login POST, got {resp.status_code}"
    )


def test_login_rate_limit_blocks_11th_request(app_client):
    """T02 — 11th POST /login within 1 minute must return 429."""
    from security import limiter
    limiter.reset()
    for i in range(10):
        app_client.post("/login", data={"password": "testpass"})
    resp = app_client.post("/login", data={"password": "testpass"})
    assert resp.status_code == 429, (
        f"Expected 429 on 11th /login POST (rate limited), got {resp.status_code}"
    )


def test_proxyfix_sets_remote_addr(app_client):
    """T03 — X-Forwarded-For header must populate request.remote_addr via ProxyFix."""
    from app import app as flask_app
    from flask import request as flask_request

    # Use test_request_context to simulate a request going through the full
    # WSGI middleware stack (including ProxyFix) without registering a hook.
    # ProxyFix rewrites REMOTE_ADDR based on HTTP_X_FORWARDED_FOR before
    # Flask processes the request, so the environ is modified at WSGI level.
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/health",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "5000",
        "wsgi.url_scheme": "http",
        "HTTP_X_FORWARDED_FOR": "1.2.3.4",
        "REMOTE_ADDR": "10.0.0.1",
    }
    # Apply ProxyFix manually to the environ to test that it transforms correctly
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    builder = EnvironBuilder(
        path="/health",
        environ_overrides={
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
            "REMOTE_ADDR": "10.0.0.1",
        },
    )
    test_environ = builder.get_environ()

    # ProxyFix modifies the environ in place when a request is processed.
    # We simulate this by building a minimal WSGI app that captures REMOTE_ADDR.
    recorded = {}

    def capture_app(environ, start_response):
        recorded["remote_addr"] = environ.get("REMOTE_ADDR")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    proxy_fixed = ProxyFix(capture_app, x_for=1, x_proto=1, x_host=1)

    responses = []

    def start_response(status, headers):
        responses.append(status)

    list(proxy_fixed(test_environ, start_response))

    assert recorded.get("remote_addr") == "1.2.3.4", (
        f"Expected remote_addr '1.2.3.4' via ProxyFix, got {recorded.get('remote_addr')}"
    )

    # Also verify app.wsgi_app is a ProxyFix instance (structural check)
    assert isinstance(flask_app.wsgi_app, ProxyFix), (
        "app.wsgi_app is not a ProxyFix instance — ProxyFix not applied in app.py"
    )


# ── SEC-2: CSRF ───────────────────────────────────────────────────────────────

def test_login_requires_csrf_token(app_client):
    """T04 — POST /login without csrf_token must return 400 when CSRF is active."""
    from app import app as flask_app
    flask_app.config["WTF_CSRF_ENABLED"] = True
    try:
        resp = app_client.post("/login", data={"password": "testpass"})
        assert resp.status_code == 400, (
            f"Expected 400 (CSRF missing) on POST /login without csrf_token, "
            f"got {resp.status_code}"
        )
    finally:
        flask_app.config["WTF_CSRF_ENABLED"] = False  # always restore


def test_api_screen_csrf_exempt(app_client):
    """T05 — POST /api/screen without csrf_token must not return 400 (API is exempt)."""
    resp = app_client.post(
        "/api/screen",
        json={"query": "test"},
        content_type="application/json",
    )
    # 401/302 (not authenticated), 200 (success), or 400 (bad request body) are
    # all acceptable — but NOT 400 from CSRF rejection. CSRF 400 returns plain text
    # "The CSRF token is missing." whereas auth redirect is 302 and body validation
    # 400 returns JSON. We check it is not a CSRF-specific 400.
    assert resp.status_code != 400 or b"CSRF" not in resp.data, (
        f"POST /api/screen returned CSRF-rejection 400 — @csrf.exempt not applied"
    )


def test_all_api_routes_csrf_exempt(app_client):
    """T06 — All 13 /api/* POST view functions must be registered in csrf._exempt_views.

    Flask-WTF 1.2.x csrf.exempt() adds view to CSRFProtect._exempt_views set
    (keyed by "module.qualname") rather than setting a _csrf_exempt attribute.
    We check each view is in that set.
    """
    import app as app_module
    from security import csrf as csrf_instance

    api_post_views = [
        app_module.api_screen,
        app_module.api_ingest_ofac,
        app_module.api_ingest_opensanctions,
        app_module.api_ingest_psc,
        app_module.api_ais_start,
        app_module.api_ais_stop,
        app_module.api_dark_periods_detect,
        app_module.api_ingest_noaa,
        app_module.api_sts_detect,
        app_module.api_detect_loitering,
        app_module.api_detect_port_calls,
        app_module.api_detect_anomalies,
        app_module.api_reconcile,
    ]
    for view in api_post_views:
        # Flask-WTF stores exempt views as "module.qualname" strings
        view_location = f"{view.__module__}.{view.__qualname__}"
        assert view_location in csrf_instance._exempt_views, (
            f"{view.__name__} (location: {view_location}) is not in csrf._exempt_views — "
            f"@csrf.exempt not applied. Registered: {csrf_instance._exempt_views}"
        )


# ── SEC-3: Security Headers ───────────────────────────────────────────────────

def test_security_headers_xframe(app_client):
    """T07 — Every response must include X-Frame-Options: DENY."""
    resp = app_client.get("/health")
    assert "X-Frame-Options" in resp.headers, "X-Frame-Options header missing"
    assert resp.headers["X-Frame-Options"] == "DENY", (
        f"Expected X-Frame-Options: DENY, got {resp.headers.get('X-Frame-Options')}"
    )


def test_security_headers_xcto(app_client):
    """T08 — Every response must include X-Content-Type-Options: nosniff."""
    resp = app_client.get("/health")
    assert "X-Content-Type-Options" in resp.headers, "X-Content-Type-Options header missing"
    assert resp.headers["X-Content-Type-Options"] == "nosniff", (
        f"Expected nosniff, got {resp.headers.get('X-Content-Type-Options')}"
    )


def test_security_headers_hsts(app_client):
    """T09 — HTTPS responses must include Strict-Transport-Security with max-age.

    HSTS is only sent when request.is_secure or X-Forwarded-Proto == 'https'
    (per RFC 6797 and Talisman's _set_hsts_headers logic). We simulate a
    Railway-proxied HTTPS request by setting X-Forwarded-Proto: https.
    """
    resp = app_client.get(
        "/health",
        headers={"X-Forwarded-Proto": "https"},
    )
    assert "Strict-Transport-Security" in resp.headers, (
        "Strict-Transport-Security header missing — Talisman requires "
        "request.is_secure or X-Forwarded-Proto=https to add HSTS"
    )
    assert "max-age" in resp.headers["Strict-Transport-Security"], (
        f"max-age missing from HSTS header: {resp.headers.get('Strict-Transport-Security')}"
    )


def test_csp_header_present(app_client):
    """T10 — Every response must include CSP or CSP-Report-Only header."""
    resp = app_client.get("/health")
    has_csp = (
        "Content-Security-Policy" in resp.headers
        or "Content-Security-Policy-Report-Only" in resp.headers
    )
    assert has_csp, (
        "Neither Content-Security-Policy nor Content-Security-Policy-Report-Only "
        "header is present on GET /health response"
    )


# ── SEC-4: Template Audit ─────────────────────────────────────────────────────

def test_login_template_has_csrf_token(app_client):
    """T12 — templates/login.html must contain csrf_token hidden input."""
    with open("templates/login.html", encoding="utf-8") as fh:
        content = fh.read()
    assert "csrf_token" in content, (
        "templates/login.html does not contain 'csrf_token' — "
        "hidden CSRF input not added to login form"
    )
