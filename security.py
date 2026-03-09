"""
security.py — Flask security extensions for Maritime OSINT Platform.

Exports:
    limiter    — Flask-Limiter instance (rate limiting)
    csrf       — Flask-WTF CSRFProtect instance
    init_security(app) — initialize all extensions on the Flask app

Usage in app.py:
    from security import limiter, csrf, init_security
    init_security(app)  # call after db.init_db() and after app.secret_key is set
"""

import logging
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect

log = logging.getLogger(__name__)

# Module-level objects — app is bound later via init_security().
# storage_uri is set in init_security() by re-creating limiter with the correct
# backend, or alternatively passed via the app config key RATELIMIT_STORAGE_URI.
# We use the app config approach so the module-level instance is a valid singleton.
limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()

_CSP = {
    "default-src": "'self'",
    "script-src":  ["'self'", "https://cdn.jsdelivr.net"],
    "style-src":   ["'self'", "https://cdn.jsdelivr.net"],
    "img-src":     [
        "'self'",
        "data:",
        "https://*.basemaps.cartocdn.com",
        "https://tiles.openseamap.org",
    ],
    "connect-src": "'self'",
    "font-src":    "'self'",
    "frame-src":   "'none'",
    "object-src":  "'none'",
}


def init_security(app):
    """Initialize Flask-Limiter, Flask-WTF CSRFProtect, and Flask-Talisman on app.

    Must be called AFTER:
      - app.secret_key is set (Phase 1 enforces this)
      - db.init_db() has run
      - ProxyFix has been applied to app.wsgi_app

    Rate limiter storage:
      - Uses REDIS_URL if set (required for multi-worker production on Railway)
      - Falls back to memory:// for local dev (SQLite mode, single process)
    """
    # ── Rate Limiter ──────────────────────────────────────────────────────────
    # Flask-Limiter 4.x: storage_uri is passed via app.config["RATELIMIT_STORAGE_URI"]
    # before calling limiter.init_app(app). The init_app() method picks up the config key.
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        app.config["RATELIMIT_STORAGE_URI"] = redis_url
    else:
        app.config["RATELIMIT_STORAGE_URI"] = "memory://"
        log.warning(
            "[security] REDIS_URL not set — using in-memory rate limit storage. "
            "Not suitable for multi-worker production (each Gunicorn worker gets "
            "its own counter, effectively doubling the per-IP limit)."
        )
    limiter.init_app(app)

    # ── CSRF ─────────────────────────────────────────────────────────────────
    csrf.init_app(app)

    # ── Security Headers (Talisman) ───────────────────────────────────────────
    # force_https=False: Railway terminates TLS at its edge proxy and forwards
    # plain HTTP internally. Setting force_https=True causes infinite redirects.
    # strict_transport_security=True + max_age=300: tells browsers to use HTTPS
    # directly (5 min initially; increase to 31536000 after confirming stability).
    # content_security_policy_report_only=True: Plan 02 audit mode — CSP
    # violations are reported to browser console but NOT blocked. The wntrblm
    # fork of flask-talisman requires content_security_policy_report_uri when
    # report_only=True, so we point it at /csp-report (a no-op POST endpoint).
    # Flip content_security_policy_report_only to False in Plan 04-03 to enforce.
    Talisman(
        app,
        force_https=False,
        strict_transport_security=True,
        strict_transport_security_max_age=300,
        frame_options="DENY",
        content_security_policy=_CSP,
        content_security_policy_report_only=True,
        content_security_policy_report_uri="/csp-report",
    )
