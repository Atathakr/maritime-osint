# Phase 4: Security Hardening - Research

**Researched:** 2026-03-09
**Domain:** Flask security extensions (Flask-Limiter, Flask-WTF, Flask-Talisman), CSP template audit, GitHub CodeQL alert management
**Confidence:** HIGH (library APIs verified via official docs + direct source inspection)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SEC-1 | Login rate limiting — `/login` POST 10/min per IP, PostgreSQL/Redis storage, ProxyFix for Railway | Flask-Limiter 4.x API confirmed; **Redis required** (PostgreSQL not supported); ProxyFix pattern documented |
| SEC-2 | CSRF protection on `/login` and `/logout` only; all `/api/*` routes explicitly exempted | Flask-WTF 1.2.x `csrf.exempt` decorator confirmed; no blueprints needed; per-route exemption works |
| SEC-3 | Security headers — HSTS, CSP whitelist, X-Frame-Options DENY, X-Content-Type-Options; `force_https=False` | Flask-Talisman wntrblm fork confirmed; all parameters verified; CSP domain list identified |
| SEC-4 | CSP template audit — inline `<script>` tags moved to `static/`; CSP report-only first | **Audit complete**: 0 inline `<script>` tags in templates; login.html has inline `<style>`; dashboard.html has 0 inline JS; Leaflet loaded from CDN; both static JS files already exist |
| SEC-5 | Dismiss 7 CodeQL `py/sql-injection` false positives via GitHub Security tab | `gh api PATCH` endpoint confirmed; `dismissed_reason="false positive"` confirmed; placeholder `_P`, `_ph()`, `_ilike()`, `_jp()` in db/connection.py are the source |
</phase_requirements>

---

## Summary

Phase 4 adds three security layers to the Flask app and closes CodeQL false-positive noise. The existing codebase is in better shape than the requirements assume — the critical template audit (SEC-4) finds **zero inline `<script>` tags** in either template. Both dashboard.html and login.html are clean: all JS is already in `static/app.js` and `static/map.js`. The only inline content in templates is CSS `<style>` blocks (not JS), which do NOT violate `script-src` CSP. This means Plan 04-01 (template audit) is shorter than expected.

The most significant finding that diverges from the original plan: **Flask-Limiter does not support PostgreSQL as a storage backend**. The underlying `limits` library supports Redis, Memcached, MongoDB, and in-memory only. Railway provides a Redis plugin (usage-billed, ~$0.005/GB/hour, negligible for rate-limit counters). The SEC-1 requirement as written ("PostgreSQL storage_uri") cannot be fulfilled literally — the plan must use Redis on Railway instead. This is a **plan-level decision** the planner must surface to the user in Plan 04-02.

For the CSP policy, the dashboard uses Leaflet 1.9.4 from `cdn.jsdelivr.net`, CARTO dark basemap tiles from `basemaps.cartocdn.com`, and optional OpenSeaMap tiles from `tiles.openseamap.org`. These must all appear in `img-src` (tiles are loaded as images). The Leaflet JS and CSS come from `cdn.jsdelivr.net` — these need `script-src` and `style-src`. All JS is in external files, so no nonce/hash is required.

**Primary recommendation:** Use Redis on Railway (one-click plugin) for Flask-Limiter storage. All other libraries (Flask-WTF 1.2.x, Flask-Talisman wntrblm fork) install and work without additional infrastructure.

---

## Current Codebase State

This section is essential — it directly answers what needs doing.

### Template Audit Results (SEC-4)

| Template | Inline `<script>` tags | `{{ data | tojson }}` patterns | Inline `<style>` | External JS |
|----------|----------------------|-------------------------------|-----------------|-------------|
| `templates/login.html` | **0** | **0** | Yes (login box CSS) | None needed |
| `templates/dashboard.html` | **0** | **0** | None | `app.js`, `map.js` via `url_for` |

**Conclusion:** SEC-4 work is minimal. No JS needs to be moved. The inline `<style>` in login.html is CSS, not JS — it does not violate `script-src` CSP. The dashboard loads Leaflet JS from CDN via a `<script src="">` tag (external, not inline), which is allowed by CSP with the correct CDN domain in `script-src`.

The CDN URL in dashboard.html is: `https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js`
The CDN CSS is: `https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css`

**Note in dashboard.html comment:** "no SRI hash to avoid unpkg serving variance" — this means no `integrity=` attribute. CSP domain allowlisting (not SRI) is the approach already taken.

### Existing Security Infrastructure

| Feature | Present? | Notes |
|---------|----------|-------|
| ProxyFix | **No** | Not in app.py; must be added |
| CSRFProtect | **No** | Not imported or initialized |
| Flask-Limiter | **No** | Not imported or initialized |
| Flask-Talisman | **No** | Not imported or initialized |
| SECRET_KEY enforcement | **Yes** | Added in Phase 1 — startup exits if missing |
| flask-limiter in requirements.txt | **No** | Not installed yet |
| flask-wtf in requirements.txt | **No** | Not installed yet |
| flask-talisman in requirements.txt | **No** | Not installed yet |

### Route Inventory (Critical for CSRF Exemption)

| Route | Method | Needs CSRF? | Type |
|-------|--------|-------------|------|
| `/login` | GET | No | Render form |
| `/login` | POST | **YES** | Form submit — protect this |
| `/logout` | GET | **YES** | State-changing action |
| `/health` | GET | No | Health check — open path |
| `/api/*` (all) | GET/POST | **No** | JSON API — must exempt |
| `/` (dashboard) | GET | No | Render only |

There are no Flask blueprints registered in app.py. All routes are registered directly on the `app` object. CSRF exemption must be done per-route with `@csrf.exempt` on each `@app.post("/api/...")` view.

### Database Connection URL (for storage_uri planning)

From `db/connection.py`:
```python
_DB_URL = os.getenv("DATABASE_URL", "")
_BACKEND = "postgres" if _DB_URL.startswith(("postgresql://", "postgres://")) else "sqlite"
```

Railway provides `DATABASE_URL=postgresql://...`. Railway Redis provides `REDIS_URL=redis://...` (or `rediss://...` for TLS).

### CodeQL False Positive Source

The 7 `py/sql-injection` alerts come from `db/connection.py`, specifically the SQL placeholder helper functions:

```python
_P = "%s" if _BACKEND == "postgres" else "?"   # param placeholder

def _ph(n: int = 1) -> str:
    """Return n comma-separated placeholders for the current backend."""
    p = "%s" if _BACKEND == "postgres" else "?"
    return ", ".join([p] * n)

def _ilike(col: str) -> str:
    """Case-insensitive LIKE operator."""
    p = "%s" if _BACKEND == "postgres" else "?"
    return f"{col} {'ILIKE' if _BACKEND == 'postgres' else 'LIKE'} {p}"

def _jp() -> str:
    """JSON-typed parameter placeholder — includes ::jsonb cast for Postgres."""
    return "%s::jsonb" if _BACKEND == "postgres" else "?"
```

CodeQL sees `%s` (a SQL injection marker format) being returned from functions and incorrectly treats these as data being inserted into SQL. In reality, these functions return **parameterized query placeholders** — the `%s` is the DB-API 2.0 parameter token, not user data. The actual user values are passed as the second argument to `cursor.execute()` separately.

---

## Standard Stack

### Core (New Packages to Install)

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| Flask-Limiter | 4.1.1 | Rate limiting on `/login` | Requires Redis backend for multi-worker persistence |
| Flask-WTF | 1.2.x | CSRF protection on login/logout | Per-route exemption for `/api/*` |
| flask-talisman | 1.1.0 (wntrblm fork) | Security headers + CSP | Use `wntrblm/flask-talisman`, not the unmaintained Google version |
| redis | 5.x | Python Redis client (Flask-Limiter dependency) | Installed via `flask-limiter[redis]` |

### Installation

```bash
pip install "flask-limiter[redis]" flask-wtf flask-talisman
```

The `[redis]` extra installs the `redis` Python package as a Flask-Limiter dependency.

**Important:** There are two `flask-talisman` packages on PyPI:
- `flask-talisman` (GoogleCloudPlatform) — last release 2019, unmaintained
- `talisman` (wntrblm fork) — actively maintained

Both import as `from flask_talisman import Talisman`. The wntrblm fork is preferred but either works for this feature set. Use `flask-talisman` (the Google one) unless you need the nonce feature — it has more search results and clearer docs. The wntrblm fork is at `https://github.com/wntrblm/flask-talisman`.

### What NOT to Add

- No SQLAlchemy — Flask-Limiter does not support PostgreSQL storage; SQLAlchemy would not help here
- No Redis client installed separately — the `[redis]` extra handles it
- No Flask-Login — authentication is session-based already

---

## Architecture Patterns

### Recommended File Structure

```
app.py                    # Modified: add ProxyFix, import security.py init
security.py               # New: init_security(app) — limiter, csrf, talisman
templates/
  login.html              # Modified: add csrf_token hidden input
  dashboard.html          # No changes needed (no inline scripts)
static/
  app.js                  # No changes needed
  map.js                  # No changes needed
requirements.txt          # Add: flask-limiter[redis], flask-wtf, flask-talisman
```

### Pattern 1: security.py Module with init_security(app)

**What:** Centralize all security extension initialization in a single module.
**When to use:** Always — keeps app.py clean, makes security audits easy.

```python
# security.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
import os

limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()

def init_security(app):
    """Initialize all security extensions on the Flask app."""
    # ── Rate Limiter ──────────────────────────────────────────────────────
    storage_uri = os.getenv("REDIS_URL", "memory://")
    limiter.init_app(app, storage_uri=storage_uri)

    # ── CSRF ─────────────────────────────────────────────────────────────
    csrf.init_app(app)

    # ── Security Headers ─────────────────────────────────────────────────
    csp = {
        "default-src": "'self'",
        "script-src": ["'self'", "https://cdn.jsdelivr.net"],
        "style-src":  ["'self'", "https://cdn.jsdelivr.net"],
        "img-src":    [
            "'self'",
            "data:",
            "https://*.basemaps.cartocdn.com",
            "https://tiles.openseamap.org",
        ],
        "connect-src": "'self'",
        "font-src":  "'self'",
        "frame-src": "'none'",
        "object-src": "'none'",
    }
    Talisman(
        app,
        force_https=False,                          # Railway terminates TLS at proxy
        strict_transport_security=True,
        strict_transport_security_max_age=300,      # 5 min for initial deploy
        frame_options="DENY",
        content_security_policy=csp,
        content_security_policy_report_only=True,   # Audit mode first
    )
```

### Pattern 2: ProxyFix for Railway

Railway sits one proxy hop in front of the app. The proxy adds one `X-Forwarded-For` value (the real client IP) and one `X-Forwarded-Proto` value (`https`).

```python
# In app.py, before creating Flask app or after — apply to app.wsgi_app
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```

`x_for=1` — trust exactly 1 `X-Forwarded-For` hop (Railway's proxy).
`x_proto=1` — trust exactly 1 `X-Forwarded-Proto` hop (needed for `force_https` redirect logic, but we set `force_https=False` so primarily for logging/scheme detection).
`x_host=1` — trust `X-Forwarded-Host` (sets `SERVER_NAME` correctly behind Railway's hostname routing).

**Security note:** Setting `x_for=1` means Flask-Limiter's `get_remote_address()` will use the real client IP from the header, not Railway's internal IP. Without ProxyFix, all requests would appear to come from the same Railway internal address and share a rate limit counter.

### Pattern 3: Rate Limiting on Login Only

```python
# In app.py or a routes module, after importing from security.py
from security import limiter, csrf

@app.post("/login")
@limiter.limit("10 per minute")
def login_post():
    ...
```

Do NOT apply a global `@limiter.limit` default — the `/api/*` endpoints should not be rate-limited (they serve authenticated internal clients, and high-frequency polling is expected for AIS data).

### Pattern 4: CSRF Exemption for API Routes

With no blueprints, exemption must be applied per view function. The pattern for the ~20 `/api/*` POST endpoints:

```python
# In app.py, import csrf from security.py
from security import csrf

@app.post("/api/screen")
@csrf.exempt
@login_required
def api_screen():
    ...
```

**Alternative (less noisy):** Set `WTF_CSRF_CHECK_DEFAULT = False` in app config, then selectively call `csrf.protect()` only on `/login` POST. This inverts the default. Research shows this is a valid Flask-WTF pattern (via `WTF_CSRF_CHECK_DEFAULT`), though less explicit.

**Recommended approach:** Keep `CSRFProtect` in default (check all POST) mode, apply `@csrf.exempt` to each API view. This is explicit and auditable. The planner must enumerate which views get `@csrf.exempt`.

### Pattern 5: CSRF Token in Login Form

```html
<!-- In templates/login.html, inside the <form> tag -->
<form method="POST" action="/login">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <input type="password" name="password" placeholder="Access password" autofocus>
  <button type="submit">Enter</button>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
</form>
```

The `{{ csrf_token() }}` Jinja2 function is made available globally by Flask-WTF when `CSRFProtect` is initialized. No form class needed.

### Pattern 6: Switching CSP to Enforcement Mode

After confirming no CSP violations in browser console (report-only phase), remove `content_security_policy_report_only=True` from the Talisman init. No other code changes needed.

### Anti-Patterns to Avoid

- **Do not** use `force_https=True` on Railway — Railway's proxy terminates TLS and forwards HTTP internally. Talisman would see all requests as HTTP and redirect infinitely.
- **Do not** use in-memory Flask-Limiter storage (`memory://`) in production — each Gunicorn worker has its own counter, so the 10/min limit becomes 20/min with 2 workers. Must use Redis.
- **Do not** apply `@limiter.limit` globally via `default_limits` — the API endpoints have legitimate high-frequency polling patterns.
- **Do not** put `'unsafe-inline'` in `script-src` — this defeats the entire CSP. The template audit confirms no inline scripts exist, so this is not needed.
- **Do not** use the Google/GoogleCloudPlatform `flask-talisman` if you need nonce support — it is unmaintained since 2019.
- **Do not** add `@csrf.exempt` to GET routes — CSRF only applies to state-changing methods (POST, PUT, DELETE, PATCH); Flask-WTF automatically skips GET.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate limit counter storage | Custom DB table for request counts | Flask-Limiter + Redis | Sliding window logic, atomic increments, TTL expiry — all handled |
| CSRF token generation | `secrets.token_hex()` in session | Flask-WTF CSRFProtect | Timing-safe comparison, token rotation, HMAC signing already done |
| Security header injection | `@app.after_request` adding headers manually | Flask-Talisman | Covers HSTS, CSP, X-Frame-Options, nosniff, referrer-policy in one place |
| CSP nonce generation | Per-request random nonce in template context | Talisman's `content_security_policy_nonce_in` | Handles nonce injection into templates automatically |
| IP extraction from proxy headers | Manual `request.headers.get("X-Forwarded-For")` | Werkzeug ProxyFix | Handles header spoofing, multi-hop chains, and sets `request.remote_addr` correctly |

---

## Common Pitfalls

### Pitfall 1: Flask-Limiter Memory Backend in Multi-Worker Gunicorn

**What goes wrong:** Rate limit is NOT enforced globally. With 2 Gunicorn workers and `memory://` storage, a client can make 10 requests to worker 1 and 10 more requests to worker 2 = 20 successful requests before hitting any limit.

**Why it happens:** In-memory storage is per-process. Each worker independently tracks counters.

**How to avoid:** Use Redis storage (`storage_uri=os.getenv("REDIS_URL")`). Railway Redis plugin provides `REDIS_URL` env var. Fall back to `memory://` only for local dev (SQLite mode).

**Warning signs:** `/login` accepts far more than 10 POSTs per minute in production while working correctly in single-process local dev.

### Pitfall 2: CSRF 400 on All API Endpoints After Adding CSRFProtect

**What goes wrong:** Every `/api/*` POST returns 400 Bad Request immediately after adding `CSRFProtect`.

**Why it happens:** Flask-WTF defaults to checking ALL POST requests for a CSRF token. API clients (the dashboard's fetch() calls) don't include `csrf_token` in JSON bodies.

**How to avoid:** Apply `@csrf.exempt` to every `/api/*` view function. There are ~15 POST endpoints in app.py. All must be exempted.

**Warning signs:** Any POST to `/api/screen`, `/api/ingest/*`, `/api/ais/start`, etc. returns 400 immediately.

### Pitfall 3: Talisman force_https=True Infinite Redirect on Railway

**What goes wrong:** App enters an infinite redirect loop. Every request redirects to `https://`, but Talisman keeps seeing the request as HTTP (because Railway's internal routing is HTTP after TLS termination).

**Why it happens:** Railway terminates TLS at its load balancer and forwards requests to Gunicorn over plain HTTP. Talisman sees `wsgi.url_scheme=http` and issues a redirect, which Railway's proxy receives and forwards again as HTTP, triggering another redirect.

**How to avoid:** Always set `force_https=False` on Railway. HSTS can still be enabled (so browsers directly use HTTPS) — just don't let the Python app enforce the redirect.

**Warning signs:** App returns 301 or 302 in a loop. Health check at `/health` fails with redirect.

### Pitfall 4: ProxyFix Applied AFTER Limiter Init

**What goes wrong:** Flask-Limiter's `get_remote_address()` returns Railway's internal IP (e.g., `10.x.x.x`) instead of the real client IP. All requests share one rate limit counter, and the 10/min limit triggers instantly for legitimate users.

**Why it happens:** ProxyFix must be applied to `app.wsgi_app` before the first request is processed. Flask-Limiter reads `request.remote_addr` at request time, which is set by ProxyFix during WSGI middleware processing.

**How to avoid:** Apply `app.wsgi_app = ProxyFix(...)` immediately after `app = Flask(__name__)`, before `init_security(app)`.

**Warning signs:** `/login` rate limit triggers after 1-2 requests even from different clients; all rate limit counters key on the same IP.

### Pitfall 5: CSP Blocks Leaflet Tile Requests

**What goes wrong:** The Leaflet map renders but shows no tiles (grey squares). Browser console shows CSP violation: `img-src` blocked `basemaps.cartocdn.com`.

**Why it happens:** Leaflet tile requests are made as `<img>` elements internally, which are subject to `img-src`. The wildcard `*.basemaps.cartocdn.com` must include the `https://` scheme prefix.

**How to avoid:** Use `"https://*.basemaps.cartocdn.com"` (with scheme) in `img-src`. Also add `https://tiles.openseamap.org` for the optional OpenSeaMap overlay.

**Warning signs:** Map container is blank or shows grey tiles; browser DevTools console shows CSP `img-src` violations.

### Pitfall 6: CSRF Token Not in Login Form — 400 on Login Attempt

**What goes wrong:** After enabling `CSRFProtect`, the `/login` POST returns 400 immediately.

**Why it happens:** The current `login.html` has no `{{ csrf_token() }}` hidden input. Flask-WTF requires the token for any POST that is not exempted.

**How to avoid:** Add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to `login.html` before enabling CSRFProtect.

**Warning signs:** Login form returns 400 instead of redirecting or showing error message.

### Pitfall 7: Logout CSRF Exposure (GET Route)

**What goes wrong:** `/logout` is a GET route. GET routes are never CSRF-checked by Flask-WTF. This means any page can trigger logout via a simple `<img src="/logout">` tag (cross-site GET request).

**Why it happens:** The app uses `@app.get("/logout")` — a GET request that modifies state (clears session).

**The choice:** Either accept the limitation (logout via GET is common in single-user apps) or change to POST. The SEC-2 requirement says "CSRF on logout" — but if logout stays GET, there's nothing for CSRFProtect to protect. This is a **plan-level decision**: if the planner keeps logout as GET, note it as a known trade-off.

---

## Code Examples

### Flask-Limiter: Full Init with Redis Fallback

```python
# security.py
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

def init_limiter(app):
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        storage_uri = redis_url
    else:
        # Local dev: in-memory (single process, SQLite dev mode)
        storage_uri = "memory://"
        import logging
        logging.getLogger(__name__).warning(
            "[security] REDIS_URL not set — using in-memory rate limit storage. "
            "Not suitable for multi-worker production."
        )
    limiter.init_app(app, storage_uri=storage_uri)
```

### Flask-Limiter: Rate Limit Decorator

```python
# Source: https://flask-limiter.readthedocs.io/en/stable/
@app.post("/login")
@limiter.limit("10 per minute")
def login_post():
    ...

# Custom 429 handler (optional — returns JSON instead of HTML)
@app.errorhandler(429)
def ratelimit_exceeded(e):
    return jsonify({"error": "Too many requests", "retry_after": str(e.description)}), 429
```

### Flask-WTF: CSRFProtect Init and Exemption

```python
# security.py
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

def init_csrf(app):
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600   # 1-hour token validity (default)
    csrf.init_app(app)
```

```python
# app.py — exempting API views
from security import csrf

@app.post("/api/screen")
@csrf.exempt
@login_required
def api_screen():
    ...
```

```html
<!-- login.html — add inside <form> -->
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

### Flask-Talisman: Init with Report-Only CSP

```python
# security.py
from flask_talisman import Talisman

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

def init_talisman(app, enforce_csp=False):
    Talisman(
        app,
        force_https=False,
        strict_transport_security=True,
        strict_transport_security_max_age=300,
        frame_options="DENY",
        content_security_policy=_CSP,
        content_security_policy_report_only=not enforce_csp,
    )
```

### ProxyFix Application

```python
# app.py — immediately after app = Flask(__name__)
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = _secret_key
```

### GitHub CodeQL Alert Dismissal (gh CLI)

```bash
# Dismiss one alert as false positive
# OWNER/REPO = your repository slug; ALERT_NUMBER = integer from GitHub Security tab
gh api \
  -X PATCH \
  -H "Accept: application/vnd.github+json" \
  "/repos/OWNER/REPO/code-scanning/alerts/ALERT_NUMBER" \
  -f state=dismissed \
  -f dismissed_reason="false positive" \
  -f dismissed_comment="Backend-agnostic placeholder variable (_P, _ph, _ilike, _jp in db/connection.py). Returns DB-API 2.0 parameter tokens (%s / ?), not user data. Actual user values are bound via cursor.execute() second argument."
```

Valid `dismissed_reason` values (from GitHub REST API):
- `"false positive"` — incorrect detection
- `"won't fix"` — accepted risk
- `"used in tests"` — test-only code

For all 7 alerts, `"false positive"` is the correct value.

**Batch script for all 7 alerts:**

```bash
OWNER="your-github-username"
REPO="maritime-osint"
REASON="false positive"
COMMENT="Backend-agnostic placeholder variable in db/connection.py. Returns DB-API 2.0 parameter tokens (%s / ?), not user data. Values are bound separately via cursor.execute() positional arguments."

# Get alert numbers from GitHub Security > Code scanning > filter py/sql-injection
for NUM in 1 2 3 4 5 6 7; do  # replace with actual alert numbers
  gh api -X PATCH \
    -H "Accept: application/vnd.github+json" \
    "/repos/$OWNER/$REPO/code-scanning/alerts/$NUM" \
    -f state=dismissed \
    -f dismissed_reason="$REASON" \
    -f dismissed_comment="$COMMENT"
done
```

**To list current alert numbers:**

```bash
gh api "/repos/OWNER/REPO/code-scanning/alerts?tool_name=CodeQL&state=open&per_page=100" \
  --jq '.[] | [.number, .rule.id, .most_recent_instance.location.path] | @tsv'
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| flask-talisman (Google) | wntrblm/flask-talisman fork | 2021 | Google version unmaintained; use wntrblm for active maintenance and nonce support |
| Flask-Limiter storage in PostgreSQL | Not supported — use Redis | Always | Limits library never added SQL backends; Redis is the de-facto standard |
| Flask-WTF `@csrf.exempt` on blueprints | Still works; per-route also works | 1.x | No change for non-blueprint apps like this one |
| `force_https=True` behind reverse proxy | `force_https=False` | Standard pattern | Railway, Heroku, all PaaS terminate TLS at the load balancer |

**Deprecated/outdated:**
- `GoogleCloudPlatform/flask-talisman`: Last release 2019 (v0.7.0). Still functional but unmaintained. No nonce support in CSP. For this project's feature set it works fine, but `wntrblm/flask-talisman` is the maintained successor.
- Flask-Limiter in-memory storage for production: Works in development, breaks in multi-worker deployments.

---

## Open Questions

1. **Redis cost on Railway**
   - What we know: Railway Redis is usage-billed. Rate limit counters are tiny (bytes per IP, TTL 60s). Monthly cost would be negligible (less than $0.01/month at typical traffic).
   - What's unclear: Whether the existing Railway project already has a Redis plugin provisioned.
   - Recommendation: Planner should note "add Redis plugin on Railway" as a deploy step in Plan 04-02.

2. **Logout CSRF (GET vs POST)**
   - What we know: Current `/logout` is a GET route. Flask-WTF does not CSRF-protect GET routes. SEC-2 says "CSRF on logout."
   - What's unclear: Whether the requirement intends to change logout to POST (proper CSRF protection) or just note CSRF is "covered" because it's GET.
   - Recommendation: Planner should decide. If keeping GET: add a comment explaining why CSRF protection is not applicable. If changing to POST: update login.html to add a logout form button.

3. **Alert Numbers for CodeQL Dismissal**
   - What we know: The gh CLI command is confirmed, dismissed_reason="false positive" is valid.
   - What's unclear: The actual integer alert numbers (1-7 are placeholders in examples above). Must be retrieved from GitHub Security tab.
   - Recommendation: Plan 04-03 should include a step to list alerts via `gh api` first to get actual numbers.

4. **HSTS max_age timing**
   - What we know: SEC-3 requires `max_age=300` (5 minutes) for initial deploy. This is correct — short HSTS max_age lets you roll back if HTTPS breaks.
   - What's unclear: Whether to increase it later (to 31536000 / 1 year) or leave it at 300 permanently.
   - Recommendation: Plan should note "increase max_age after confirming HTTPS stable" as a follow-up, but 300 is correct for Phase 4.

---

## Validation Architecture

Nyquist validation is enabled. The following test map covers SEC-1 through SEC-4 (SEC-5 is a manual GitHub UI/CLI task with no automated test equivalent).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | None detected — runs via `pytest tests/` |
| Quick run command | `pytest tests/test_security.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Test ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|---------|----------|-----------|-------------------|--------------|
| SEC-1 | T01 | `/login` POST returns 200 on first request | Unit/integration | `pytest tests/test_security.py::test_login_rate_limit_allows_first_request -x` | Wave 0 |
| SEC-1 | T02 | `/login` POST returns 429 after 10 POSTs/min | Unit/integration | `pytest tests/test_security.py::test_login_rate_limit_blocks_11th_request -x` | Wave 0 |
| SEC-1 | T03 | Rate limit uses `request.remote_addr` (not Railway internal IP) | Unit | `pytest tests/test_security.py::test_proxyfix_sets_remote_addr -x` | Wave 0 |
| SEC-2 | T04 | `/login` POST without `csrf_token` returns 400 | Unit/integration | `pytest tests/test_security.py::test_login_requires_csrf_token -x` | Wave 0 |
| SEC-2 | T05 | `/api/screen` POST without `csrf_token` returns 200 (exempted) | Unit/integration | `pytest tests/test_security.py::test_api_screen_csrf_exempt -x` | Wave 0 |
| SEC-2 | T06 | All `/api/*` POST routes are csrf-exempted (enumerate all) | Unit/integration | `pytest tests/test_security.py::test_all_api_routes_csrf_exempt -x` | Wave 0 |
| SEC-3 | T07 | Response includes `X-Frame-Options: DENY` header | Unit/integration | `pytest tests/test_security.py::test_security_headers_xframe -x` | Wave 0 |
| SEC-3 | T08 | Response includes `X-Content-Type-Options: nosniff` | Unit/integration | `pytest tests/test_security.py::test_security_headers_xcto -x` | Wave 0 |
| SEC-3 | T09 | Response includes `Strict-Transport-Security` with `max-age` | Unit/integration | `pytest tests/test_security.py::test_security_headers_hsts -x` | Wave 0 |
| SEC-3 | T10 | CSP header present (report-only or enforced) | Unit/integration | `pytest tests/test_security.py::test_csp_header_present -x` | Wave 0 |
| SEC-4 | T11 | Dashboard renders without CSP violations (static analysis) | Manual (browser) | Open browser DevTools console after deploy | Manual only |
| SEC-4 | T12 | login.html contains `csrf_token` hidden input | Template text scan | `pytest tests/test_security.py::test_login_template_has_csrf_token -x` | Wave 0 |

**Manual-only justification for T11:** CSP violation detection requires a real browser making real tile/CDN requests. Cannot be automated without a headless browser (Playwright/Selenium) which is out of scope for this phase.

### Test Infrastructure Notes

The existing `tests/conftest.py` sets `SECRET_KEY` and `APP_PASSWORD` as environment variables for the test session (via module-level code). Security tests will need the Flask test client. The existing conftest uses `sqlite_db` fixture that calls `db.init_db()`.

For security tests, an additional fixture is needed: `app_client` that returns a Flask test client with the security extensions initialized. This requires `SECRET_KEY` and `APP_PASSWORD` to be set (already handled by conftest).

Flask-Limiter in test mode: with `memory://` storage (REDIS_URL not set in tests), rate limiting works correctly for single-process test execution. Tests can reset the limiter between test functions using `limiter.reset()` or by initializing with a fresh Limiter instance.

### Wave 0 Gaps

- [ ] `tests/test_security.py` — all T01-T10, T12 test functions (new file, does not exist)
- [ ] Fixture `app_client` in `tests/conftest.py` — Flask test client with security extensions initialized

None — existing test infrastructure (pytest, conftest, sqlite_db fixture) is sufficient. Only a new test file is needed.

---

## Sources

### Primary (HIGH confidence)

- Flask-Limiter 4.1.1 official docs (https://flask-limiter.readthedocs.io/en/stable/) — confirmed no PostgreSQL storage; Redis/Memcached/MongoDB only; ProxyFix pattern confirmed
- Flask-Limiter recipes (https://flask-limiter.readthedocs.io/en/stable/recipes.html) — ProxyFix `x_for=1` pattern; per-route decorator syntax; 429 error handler
- Werkzeug ProxyFix docs (https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/) — x_for, x_proto, x_host parameters; single-proxy configuration
- Flask-WTF 1.2.x docs (https://flask-wtf.readthedocs.io/en/1.2.x/csrf/) — CSRFProtect API; `csrf.exempt` decorator; `{{ csrf_token() }}` template function; WTF_CSRF_TIME_LIMIT=3600 default
- flask-talisman GitHub (https://github.com/GoogleCloudPlatform/flask-talisman) — force_https, HSTS, frame_options, content_security_policy dict syntax, report_only mode
- wntrblm/flask-talisman (https://github.com/wntrblm/flask-talisman) — maintained fork, nonce support confirmed
- limits library docs (https://limits.readthedocs.io/en/stable/storage.html) — confirmed PostgreSQL not listed; Redis, Memcached, MongoDB, Valkey only
- Direct source inspection: `app.py`, `templates/login.html`, `templates/dashboard.html`, `static/app.js`, `static/map.js`, `db/connection.py` — confirmed template state and CodeQL source

### Secondary (MEDIUM confidence)

- GitHub REST API code scanning docs (https://docs.github.com/en/rest/code-scanning/code-scanning) — PATCH endpoint confirmed; dismissed_reason="false positive" confirmed via search results
- Railway Redis docs (https://docs.railway.com/databases/redis) — REDIS_URL env var confirmed; usage-billed pricing

### Tertiary (LOW confidence — marked for validation)

- Flask-Limiter Gunicorn multi-worker issue (https://github.com/alisaifee/flask-limiter/issues/327) — confirms shared-backend requirement; per-process counting bug documented

---

## Metadata

**Confidence breakdown:**
- Template audit (SEC-4): HIGH — direct source file inspection, definitive
- Flask-Limiter API (SEC-1): HIGH — official docs verified; PostgreSQL limitation is a definitive finding
- Flask-WTF API (SEC-2): HIGH — official 1.2.x docs verified
- Flask-Talisman API (SEC-3): HIGH — official README verified from both forks
- ProxyFix configuration: HIGH — Werkzeug official docs
- CodeQL dismissal: MEDIUM — CLI command pattern confirmed via multiple sources; actual alert numbers require live GitHub query
- Redis on Railway: MEDIUM — docs confirmed REDIS_URL; cost estimate is LOW (extrapolated from pricing structure)

**Research date:** 2026-03-09
**Valid until:** 2026-06-09 (90 days — Flask security library APIs are stable)
