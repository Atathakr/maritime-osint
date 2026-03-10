# Phase 7: Alert Generation and In-App Panel - Research

**Researched:** 2026-03-10
**Domain:** Flask alert system — PostgreSQL alerts table, APScheduler hook, in-page JS notification badge and panel
**Confidence:** HIGH

---

## Summary

Phase 7 adds automated alert generation inside the existing APScheduler job and surfaces those alerts to the analyst via a header badge and slide-in panel, all without a new page load. The backend work is a new `alerts` table (SQLite + PostgreSQL dual DDL, consistent with every prior table in the project), five new db functions in `db/alerts.py`, and a hook inserted into `_do_score_refresh()` after history is written. The frontend work is three new API routes and a small JS module that polls one endpoint every 30 seconds to keep the badge fresh.

The score history infrastructure from Phase 6 is the prerequisite: each alert condition compares the current `fresh` score dict against the most-recent `prior` history snapshot already computed by `_do_score_refresh()`. No extra queries are needed — the data is already in hand at the point where alert generation must run.

The project's CSP enforcement constraint (Phase 4, no inline `<script>` blocks) means all JS must live in a new `static/alerts.js` file. The existing pattern of embedding data via `<script type="application/json">` is not needed here because alert data is fetched dynamically on page load and on a 30-second poll.

**Primary recommendation:** Add `db/alerts.py`, wire `generate_alerts_for_vessel()` into `_do_score_refresh()`, add three API routes, write `static/alerts.js`, inject badge HTML into `dashboard.html` header, add alert panel HTML to the dashboard, and add CSRF exemption to the two state-changing alert routes.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ALRT-01 | Dashboard header notification badge with unread count; hidden when zero | Covered by `GET /api/alerts/unread-count` + `alerts.js` polling; badge hidden via CSS `display:none` when count is 0 |
| ALRT-02 | Alert panel list: vessel name, alert type, score at trigger, time since triggered | Covered by `GET /api/alerts` returning `vessel_name`, `alert_type`, `score_at_trigger`, `triggered_at`; rendered by `alerts.js` |
| ALRT-03 | Alert detail view: before/after score, before/after risk level, newly fired indicators, View Vessel link | Covered by alert record storing `before_score`, `after_score`, `before_risk_level`, `after_risk_level`, `new_indicators_json`; detail expansion in-panel |
| ALRT-04 | Alert on risk level crossing (LOW/MEDIUM/HIGH/CRITICAL) in either direction | `generate_alerts_for_vessel()` compares `prior[0]["risk_level"]` vs derived fresh risk level |
| ALRT-05 | Alert when vessel enters top 50 | `_do_score_refresh()` collects top-50 IMO set before the loop; per-vessel check compares membership |
| ALRT-06 | Alert when `is_sanctioned` flips false→true | Direct comparison of `prior[0]["is_sanctioned"]` vs `fresh["is_sanctioned"]` |
| ALRT-07 | Alert when composite_score changes by 15+ points in single run | `abs(fresh_score - prior_score) >= 15` |
| ALRT-08 | Mark alert as read; badge decrements; read alerts visible in "read" section | `POST /api/alerts/<id>/read`; JS re-fetches count and re-renders panel |
</phase_requirements>

---

## Standard Stack

### Core (all already in requirements.txt — no new packages needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | existing | API routes for alert CRUD | Already in use |
| psycopg2-binary | existing | PostgreSQL connection | Already in use |
| APScheduler 3.x | existing | Hook into `_do_score_refresh()` | Already in use |
| SQLite (stdlib) | stdlib | Local dev backend | Already in use |

No new pip packages are required for this phase.

### Supporting JS (no new CDN additions needed)

| Asset | Source | Purpose |
|-------|--------|---------|
| `static/alerts.js` | New file in static/ | Badge + panel logic |

The existing `style.css` will receive new rules for badge, panel, and read/unread sections.

---

## Architecture Patterns

### alerts Table DDL

The table follows the exact dual-backend pattern used in `db/scores.py` (Postgres section uses `BIGSERIAL`, `TIMESTAMPTZ`, `JSONB`; SQLite section uses `INTEGER AUTOINCREMENT`, `TEXT`, `TEXT`).

**Postgres columns:**
```sql
CREATE TABLE IF NOT EXISTS alerts (
    id                  BIGSERIAL    PRIMARY KEY,
    imo_number          VARCHAR(20)  NOT NULL,
    vessel_name         TEXT,
    alert_type          TEXT         NOT NULL,
    before_score        INTEGER,
    after_score         INTEGER,
    before_risk_level   TEXT,
    after_risk_level    TEXT,
    score_at_trigger    INTEGER,
    new_indicators_json JSONB        DEFAULT '[]',
    is_read             SMALLINT     NOT NULL DEFAULT 0,
    triggered_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
```

**SQLite columns (identical logic, different types):**
```sql
CREATE TABLE IF NOT EXISTS alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    imo_number          TEXT    NOT NULL,
    vessel_name         TEXT,
    alert_type          TEXT    NOT NULL,
    before_score        INTEGER,
    after_score         INTEGER,
    before_risk_level   TEXT,
    after_risk_level    TEXT,
    score_at_trigger    INTEGER,
    new_indicators_json TEXT    DEFAULT '[]',
    is_read             INTEGER NOT NULL DEFAULT 0,
    triggered_at        TEXT    NOT NULL DEFAULT (datetime('now'))
)
```

**Indexes:**
- `idx_alerts_imo` on `imo_number`
- `idx_alerts_is_read` on `is_read`
- `idx_alerts_triggered_at` on `triggered_at DESC`

**alert_type values (TEXT enum):**
- `"risk_level_crossing"` — ALRT-04
- `"top_50_entry"` — ALRT-05
- `"sanctions_match"` — ALRT-06
- `"score_spike"` — ALRT-07

### DDL Integration Point

`init_scores_tables()` in `db/scores.py` already calls into `db/schema.py` via `init_db()`. The new `init_alerts_table()` function in `db/alerts.py` must be called from `db/schema.py`'s `init_db()` function, following the same local-import pattern already used:

```python
# In db/schema.py init_db(), after init_scores_tables():
from .alerts import init_alerts_table  # noqa: WPS433
init_alerts_table()
```

### Project Structure Addition

```
db/
├── __init__.py       # add alerts re-exports here
├── alerts.py         # NEW: init_alerts_table, insert_alert, get_alerts,
│                     #      get_unread_count, mark_alert_read
├── scores.py         # unchanged
├── schema.py         # add init_alerts_table() call
static/
├── alerts.js         # NEW: badge poll, panel render, mark-read
templates/
└── dashboard.html    # add badge HTML, alert panel HTML, alerts.js <script> tag
```

### db/alerts.py Function Signatures

```python
def init_alerts_table() -> None:
    """Create alerts table (idempotent, dual-backend)."""

def insert_alert(
    imo: str,
    vessel_name: str | None,
    alert_type: str,
    before_score: int | None,
    after_score: int | None,
    before_risk_level: str | None,
    after_risk_level: str | None,
    score_at_trigger: int,
    new_indicators: list[str],
) -> None:
    """Insert one alert row."""

def get_alerts(is_read: int | None = None, limit: int = 200) -> list[dict]:
    """
    Return alerts ordered by triggered_at DESC.
    is_read=None returns all; is_read=0 returns unread; is_read=1 returns read.
    new_indicators_json returned as list.
    """

def get_unread_count() -> int:
    """Return count of rows where is_read=0."""

def mark_alert_read(alert_id: int) -> bool:
    """Set is_read=1 for the given id. Returns True if row existed."""
```

### Alert Generation Hook in `_do_score_refresh()`

The hook runs **after** `append_score_history()` and **before** the `except` clause. The `prior` variable is already in scope. Vessel name comes from the `row` dict returned by `get_all_vessel_scores()` (which already JOINs `vessels_canonical.entity_name`).

```python
def _do_score_refresh() -> None:
    rows = db.get_all_vessel_scores()
    # ALRT-05: capture top-50 IMOs BEFORE the loop starts
    top_50_before = {r["imo_number"] for r in rows[:50]}
    refreshed = 0
    for row in rows:
        imo = row.get("imo_number")
        if not imo:
            continue
        try:
            fresh = screening.compute_vessel_score(imo)
            db.upsert_vessel_score(imo, fresh)

            prior = db.get_score_history(imo, limit=1)
            if not prior or _score_changed(prior[0], fresh):
                db.append_score_history(imo, fresh)

            # ALRT-04 through ALRT-07: generate alerts if prior exists
            if prior:
                _generate_alerts(
                    imo=imo,
                    vessel_name=row.get("entity_name"),
                    prior=prior[0],
                    fresh=fresh,
                    was_in_top_50=(imo in top_50_before),
                )

            refreshed += 1
        except Exception:
            log.exception("[scheduler] failed to refresh score for IMO %s", imo)
    log.info("[scheduler] score refresh complete: %d vessels refreshed", refreshed)
```

**Important:** `top_50_before` is derived from `rows` which is sorted by `composite_score DESC`. Slice `[:50]` gives the top-50 set from the previous run's scores (still in vessel_scores at the start of the loop, before this run's upserts). This is the correct "was in top 50 before" comparison.

### `_generate_alerts()` Logic

```python
def _generate_alerts(
    imo: str,
    vessel_name: str | None,
    prior: dict,
    fresh: dict,
    was_in_top_50: bool,
) -> None:
    """Evaluate all alert conditions and insert rows for any that fire."""
    import json as _json

    prior_score = int(prior.get("composite_score", 0))
    fresh_score  = int(fresh.get("composite_score", 0))
    prior_sanctioned = bool(prior.get("is_sanctioned"))
    fresh_sanctioned = bool(fresh.get("is_sanctioned"))

    # Derive risk levels (same thresholds as append_score_history)
    def _risk(score, sanctioned):
        if sanctioned: return "CRITICAL"
        if score >= 70: return "HIGH"
        if score >= 40: return "MEDIUM"
        return "LOW"

    prior_risk = prior.get("risk_level") or _risk(prior_score, prior_sanctioned)
    fresh_risk = _risk(fresh_score, fresh_sanctioned)

    # Compute newly fired indicators (in fresh but not in prior)
    prior_ind = prior.get("indicator_json") or {}
    fresh_ind  = fresh.get("indicator_json") or {}
    if isinstance(prior_ind, str):
        try: prior_ind = _json.loads(prior_ind)
        except Exception: prior_ind = {}
    if isinstance(fresh_ind, str):
        try: fresh_ind = _json.loads(fresh_ind)
        except Exception: fresh_ind = {}
    new_indicators = [k for k in fresh_ind if k not in prior_ind]

    common_args = dict(
        imo=imo, vessel_name=vessel_name,
        before_score=prior_score, after_score=fresh_score,
        before_risk_level=prior_risk, after_risk_level=fresh_risk,
        score_at_trigger=fresh_score, new_indicators=new_indicators,
    )

    # ALRT-04: risk level crossing
    if prior_risk != fresh_risk:
        db.insert_alert(alert_type="risk_level_crossing", **common_args)

    # ALRT-05: top-50 entry (vessel was NOT in top-50 before; need to check current position)
    # NOTE: current position in top-50 is checked by the caller passing was_in_top_50=False
    # and fresh_score being high enough. The planner must decide: compare was_in_top_50
    # vs a post-loop top-50. Simpler approach: alert if not was_in_top_50 and fresh_score
    # would have ranked in top-50. We don't re-sort here; instead the scheduler captures
    # fresh top-50 after the loop and fires alerts in a second pass. See Pitfall 2.

    # ALRT-06: sanctions flip false→true
    if not prior_sanctioned and fresh_sanctioned:
        db.insert_alert(alert_type="sanctions_match", **common_args)

    # ALRT-07: score spike ≥ 15 pts
    if abs(fresh_score - prior_score) >= 15:
        db.insert_alert(alert_type="score_spike", **common_args)
```

### ALRT-05 Top-50 Entry: Correct Pattern

This is the tricky condition. During the refresh loop each vessel's score is being updated in `vessel_scores`. At the start of the loop `rows` reflects last run's scores. At the end of the loop all scores are updated.

**Correct approach:** two-pass.
- Before the loop: capture `top_50_before = {r["imo_number"] for r in rows[:50]}` (last run's top-50).
- After the loop: re-query `db.get_all_vessel_scores()` to get `top_50_after = {r["imo_number"] for r in new_rows[:50]}`.
- Fire ALRT-05 for any IMO in `top_50_after - top_50_before`.

This keeps the alert generation clean and avoids trying to reason about per-vessel ranking mid-loop. The second `get_all_vessel_scores()` call is one extra query per scheduler run (not per vessel) — negligible cost.

```python
# After the loop:
new_rows = db.get_all_vessel_scores()
top_50_after = {r["imo_number"] for r in new_rows[:50]}
newly_entered = top_50_after - top_50_before
for r in new_rows:
    if r["imo_number"] in newly_entered:
        prior_hist = db.get_score_history(r["imo_number"], limit=1)
        prior_score = prior_hist[0].get("composite_score", 0) if prior_hist else 0
        prior_risk = prior_hist[0].get("risk_level", "LOW") if prior_hist else "LOW"
        db.insert_alert(
            imo=r["imo_number"],
            vessel_name=r.get("entity_name"),
            alert_type="top_50_entry",
            before_score=prior_score,
            after_score=r.get("composite_score"),
            before_risk_level=prior_risk,
            after_risk_level=r.get("risk_level") or "LOW",
            score_at_trigger=r.get("composite_score"),
            new_indicators=[],
        )
```

### API Routes

Three new routes in `app.py`:

```python
@app.get("/api/alerts/unread-count")
@login_required
def api_alerts_unread_count():
    """ALRT-01: returns {"count": N}"""
    return jsonify({"count": db.get_unread_count()})


@app.get("/api/alerts")
@login_required
def api_alerts():
    """ALRT-02/ALRT-03: returns {"unread": [...], "read": [...]}"""
    unread = db.get_alerts(is_read=0, limit=100)
    read   = db.get_alerts(is_read=1, limit=50)
    return jsonify({"unread": unread, "read": read})


@app.post("/api/alerts/<int:alert_id>/read")
@csrf.exempt
@login_required
def api_alert_mark_read(alert_id):
    """ALRT-08: mark one alert as read"""
    found = db.mark_alert_read(alert_id)
    if not found:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify({"ok": True, "count": db.get_unread_count()})
```

**Route ordering note:** `/api/alerts/unread-count` must be registered BEFORE `/api/alerts/<int:alert_id>/read` to avoid any shadowing (Flask matches in registration order for ambiguous patterns; these are not ambiguous but placing specific routes first is project convention per Phase 6 decision).

**CSRF exemption:** The `POST /api/alerts/<id>/read` route is a state-changing API endpoint. All `/api/*` POST endpoints in the project are `@csrf.exempt` (per Phase 4 decision: "All /api/* POST endpoints continue to accept requests without CSRF tokens"). Follow the same pattern.

### db/__init__.py Re-Exports

Add to `db/__init__.py` following the existing section comment pattern:

```python
# ── Alerts (Phase 7) ──────────────────────────────────────────────────────────
from .alerts import (  # noqa: F401
    init_alerts_table, insert_alert, get_alerts,
    get_unread_count, mark_alert_read,
)
```

### Frontend: Badge HTML in dashboard.html Header

Insert after the existing `<a href="/logout">Logout</a>` in the `header-right` div:

```html
<button id="alert-badge-btn" class="alert-badge-btn hidden" onclick="toggleAlertPanel()">
  <span id="alert-badge-count">0</span>
</button>
```

The `hidden` class is set by default; JS removes it when count > 0.

### Frontend: Alert Panel HTML in dashboard.html

Insert as a direct child of `<body>` (after `<main>`) so the panel can overlay the full page without being clipped:

```html
<div id="alert-panel" class="alert-panel hidden" role="dialog" aria-label="Alerts">
  <div class="alert-panel-header">
    <span class="alert-panel-title">Alerts</span>
    <button class="alert-panel-close" onclick="toggleAlertPanel()">✕</button>
  </div>
  <div id="alert-panel-body">
    <div class="empty-state">Loading…</div>
  </div>
</div>
<div id="alert-overlay" class="alert-overlay hidden" onclick="toggleAlertPanel()"></div>
```

### Frontend: alerts.js Module

The file lives at `static/alerts.js` and is loaded via:
```html
<script src="{{ url_for('static', filename='alerts.js') }}"></script>
```
(Added at the bottom of `dashboard.html` after the existing three `<script>` tags.)

Key functions:
- `initAlerts()` — called from `DOMContentLoaded` in `app.js` (or `alerts.js` self-registers its own listener)
- `pollUnreadCount()` — fetches `/api/alerts/unread-count` every 30 s; updates badge
- `toggleAlertPanel()` — shows/hides panel; on show, fetches `/api/alerts` and renders
- `renderAlertPanel(data)` — builds unread and read sections from `data.unread` / `data.read`
- `renderAlertDetail(alert)` — expands a list item to show before/after scores, newly fired indicators, View Vessel link
- `markRead(alertId)` — POSTs `/api/alerts/<id>/read`, decrements badge, re-renders

**CSP compliance:** No inline `onclick` attributes allowed in HTML injected by JS. Use `addEventListener` in `alerts.js` for dynamically-created elements. The static HTML `onclick` attributes in the dashboard template are already the established project pattern (existing code uses `onclick=` in HTML extensively for buttons). This is consistent with Phase 4 CSP decisions — inline event handlers on static HTML elements are not blocked by CSP (only inline `<script>` blocks are blocked).

**Polling approach:** Load on `DOMContentLoaded` + poll every 30 seconds. Do NOT use WebSockets (out of scope per requirements).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization of indicator lists | Custom string encoding | `json.dumps(list)` / `_jp()` pattern | Already used by every other JSONB column |
| DB dual-backend abstraction | New connection logic | Existing `_BACKEND`, `_conn()`, `_ph()`, `_jp()` from `db/connection.py` | Phase 1 established this as the single pattern |
| Risk level derivation | A new helper | The same `if sanctioned: CRITICAL / >=70: HIGH / >=40: MEDIUM / else: LOW` logic used in `append_score_history()` | Must be identical to history so alert risk levels match history risk levels |
| Top-50 ranking | Custom sort | Use `get_all_vessel_scores()` which already orders by `composite_score DESC` | The function returns them pre-sorted |
| Panel dismiss on outside-click | Custom event detection | `<div id="alert-overlay">` click handler | Simple overlay is the established dashboard pattern |

---

## Common Pitfalls

### Pitfall 1: Alert Duplication Per Run
**What goes wrong:** If `_generate_alerts()` runs on a vessel that fires ALRT-07 (score spike) AND has a risk level crossing, two separate alert rows are inserted. This is intentional and correct — one alert per triggered condition per run (per Phase 7 success criteria). Do NOT deduplicate across different `alert_type` values.

However, if the scheduler job somehow runs twice for the same vessel (e.g., advisory lock failure), duplicate alerts fire. Mitigation: trust the existing `pg_try_advisory_xact_lock` pattern.

**How to avoid:** The alert generation path is inside the same advisory-lock-protected block as score refresh. No additional deduplication needed.

### Pitfall 2: ALRT-05 Mid-Loop Ranking Problem
**What goes wrong:** If you try to determine top-50 membership inside the vessel loop, you're comparing the vessel's fresh score against stale scores for other vessels (not yet refreshed in this loop iteration). This produces incorrect results.

**How to avoid:** Two-pass approach described above: capture `top_50_before` before the loop from the pre-refresh `rows` list; capture `top_50_after` with a second `get_all_vessel_scores()` call after the loop completes.

### Pitfall 3: Alert Fire on First History Row
**What goes wrong:** When `prior` is empty (no history yet for vessel), `_generate_alerts()` should NOT fire — there's no "before" state to compare against. The current `_do_score_refresh()` code already checks `if prior:` before calling alert generation. If this check is omitted, a newly scored vessel will trigger ALRT-07 (score change from 0 to anything ≥ 15).

**How to avoid:** Guard: `if prior:` before calling `_generate_alerts()`.

### Pitfall 4: CSP Violation from dynamically-created onclick
**What goes wrong:** When `alerts.js` builds HTML strings with `onclick="markRead(123)"` injected via `innerHTML`, the browser's CSP blocks inline event handlers on dynamically created content because they count as eval-equivalent under strict-dynamic CSP.

**How to avoid:** Build DOM nodes with `document.createElement()` and attach handlers with `addEventListener()`. Do not use `innerHTML` for any interactive elements. For read-only content (vessel names, score labels) `innerHTML` or `textContent` is fine.

### Pitfall 5: Route Shadowing — `/api/alerts/unread-count` vs `/api/alerts/<id>/read`
**What goes wrong:** Flask's routing is fine here since `unread-count` is a literal path and `<int:alert_id>` requires an integer. But if the route for `unread-count` is registered after `<int:alert_id>/read`, Flask won't shadow them (integers don't match the string "unread-count"). Still, register specific routes before parameterized ones as a project convention.

### Pitfall 6: indicator_json Comparison Direction
**What goes wrong:** Computing "newly fired indicators" as `[k for k in fresh_ind if k not in prior_ind]` assumes `indicator_json` only stores FIRED indicators (absent = not fired). This is the Phase 5 decision: "indicator_json only stores FIRED indicators (keys = indicator IDs, absent = not fired)". Computing in the wrong direction (prior not in fresh) gives "cleared" indicators, not "new" ones.

**How to avoid:** New indicators = keys in `fresh_ind` that are absent in `prior_ind`.

### Pitfall 7: SQLite `DEFAULT (datetime('now'))` vs Postgres `DEFAULT NOW()`
**What goes wrong:** The `triggered_at` column defaults differ by backend. Using `datetime('now')` in INSERT-time code works on SQLite but not Postgres (which uses `NOW()`). The correct approach is to not specify a default at insert-time in Python code — let the database `DEFAULT` expression fire.

**How to avoid:** `insert_alert()` should omit `triggered_at` from the INSERT column list (let it default). If an explicit timestamp is needed, pass `datetime.now(timezone.utc).isoformat()` as a parameter.

---

## Code Examples

### Verified Pattern: dual-backend INSERT with JSONB/TEXT list column

Based on confirmed pattern from `db/scores.py` `append_score_history()`:

```python
# Source: db/scores.py lines 279-294 (Phase 6 implementation)
if _BACKEND == "postgres":
    sql = f"""
        INSERT INTO alerts
            (imo_number, vessel_name, alert_type,
             before_score, after_score,
             before_risk_level, after_risk_level,
             score_at_trigger, new_indicators_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {_jp()})
    """
else:
    sql = f"""
        INSERT INTO alerts
            (imo_number, vessel_name, alert_type,
             before_score, after_score,
             before_risk_level, after_risk_level,
             score_at_trigger, new_indicators_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, {_jp()})
    """

import json as _json
with _conn() as conn:
    c = conn.cursor()
    c.execute(sql, (
        imo, vessel_name, alert_type,
        before_score, after_score,
        before_risk_level, after_risk_level,
        score_at_trigger,
        _json.dumps(new_indicators),
    ))
```

`_jp()` returns `%s` for Postgres (JSONB accepts a JSON string from psycopg2) and `?` for SQLite.

### Verified Pattern: advisory-lock guard in scheduler job

```python
# Source: app.py lines 120-133 (_refresh_all_scores_job)
if db._BACKEND == "postgres":
    with db._conn() as conn:
        c = conn.cursor()
        c.execute("SELECT pg_try_advisory_xact_lock(%s)", (_SCHEDULER_ADVISORY_LOCK_ID,))
        if not c.fetchone()[0]:
            return  # another worker is running this job
        _do_score_refresh()
```

### Verified Pattern: existing test fixture (IMO range convention)

```python
# Source: tests/test_scores.py + conftest.py
# IMO ranges used by prior phases:
#   IMO1234567 - IMO6666666  → Phase 2/scores tests
#   IMO7000001+              → Phase 3/detection tests
#   IMO8000001+              → Phase 6/history tests (per STATE.md)
# Phase 7 tests should use IMO9000001+ to avoid collision
```

### Verified Pattern: CSRF-exempt API POST

```python
# Source: app.py pattern established in Phase 4 (e.g., /api/screen)
@app.post("/api/alerts/<int:alert_id>/read")
@csrf.exempt
@login_required
def api_alert_mark_read(alert_id):
    ...
```

### Verified Pattern: `<script type="application/json">` alternative — dynamic fetch

The project uses `<script type="application/json">` for data that must be server-side rendered (Phase 5: ranking table score data). For alert data, a dynamic fetch on panel open is cleaner and avoids embedding potentially large alert arrays in the HTML. Use:

```javascript
// Source pattern: static/ranking.js (fetch-on-load pattern)
async function fetchAlerts() {
  const resp = await fetch('/api/alerts');
  if (!resp.ok) throw new Error('Failed to fetch alerts');
  return resp.json();
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline `<script>` blocks | All JS in `static/*.js` files | Phase 4 (CSP enforcement) | alerts.js must be a separate file |
| Single db.py | `db/` package with per-domain modules | Phase 1 | alerts.py goes in db/ as `db/alerts.py` |
| No score history | `vessel_score_history` table with Phase 6 | Phase 6 | Alert generation has prior snapshot data |
| Manually-discovered alerts | Scheduler-generated, server-side alerts | Phase 7 (new) | Zero analyst action needed to discover events |

---

## Open Questions

1. **Top-50 after vs. top-50 before conflict on small fleets**
   - What we know: if fewer than 50 vessels are tracked, every vessel is always "in top 50" and ALRT-05 never fires.
   - What's unclear: is this edge case worth documenting in tests or just let it naturally not fire?
   - Recommendation: Accept this behaviour. ALRT-05 is only meaningful when vessel count exceeds 50. Add a comment in `_do_score_refresh()`.

2. **Alert volume growth over time**
   - What we know: alerts table is append-only; no prune job exists yet.
   - What's unclear: how many alerts accumulate per 15-min cycle at steady state?
   - Recommendation: Add a note in db/alerts.py doc comment that a prune job (e.g., delete alerts older than 30 days) can be added later. Not required for Phase 7 per requirements.

3. **vessel_name currency**
   - What we know: `get_all_vessel_scores()` JOINs `vessels_canonical.entity_name`, which is used as `vessel_name` in alert rows.
   - What's unclear: if an alert is inserted and later the canonical name changes, the stored `vessel_name` in the alert row becomes stale.
   - Recommendation: Store `vessel_name` at insert time (snapshot approach, consistent with how `vessel_score_history` stores data). Acceptable for v1.1; denormalization is deliberate.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, 155 tests green after Phase 6) |
| Config file | None — pytest discovers by convention |
| Quick run command | `pytest tests/test_alerts.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ALRT-01 | Badge count endpoint returns integer count | unit | `pytest tests/test_alerts.py::test_unread_count_endpoint -x -q` | Wave 0 |
| ALRT-02 | Alert panel API returns vessel_name, alert_type, score_at_trigger, triggered_at | unit | `pytest tests/test_alerts.py::test_get_alerts_shape -x -q` | Wave 0 |
| ALRT-03 | Alert row has before/after scores and risk levels and new_indicators_json | unit | `pytest tests/test_alerts.py::test_alert_detail_fields -x -q` | Wave 0 |
| ALRT-04 | Risk level crossing generates alert_type="risk_level_crossing" | unit | `pytest tests/test_alerts.py::test_risk_level_crossing_alert -x -q` | Wave 0 |
| ALRT-05 | Top-50 entry generates alert_type="top_50_entry" | unit | `pytest tests/test_alerts.py::test_top_50_entry_alert -x -q` | Wave 0 |
| ALRT-06 | is_sanctioned flip false→true generates alert_type="sanctions_match" | unit | `pytest tests/test_alerts.py::test_sanctions_flip_alert -x -q` | Wave 0 |
| ALRT-07 | Score change ≥ 15 pts generates alert_type="score_spike" | unit | `pytest tests/test_alerts.py::test_score_spike_alert -x -q` | Wave 0 |
| ALRT-08 | mark_alert_read() sets is_read=1; get_unread_count() decrements | unit | `pytest tests/test_alerts.py::test_mark_alert_read -x -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_alerts.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_alerts.py` — 8 stubs covering ALRT-01 through ALRT-08
- [ ] IMO range `IMO9000001+` reserved for Phase 7 tests (avoid collision with Phases 2-6)

*(No framework install needed — pytest already present and 155 tests passing)*

**Fixture pattern for test_alerts.py:**

```python
# Based on test_scores.py _setup_db() pattern
import os
os.environ["DATABASE_URL"] = ""  # force SQLite before any db import
import db

def _setup_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    db._init_backend()
    db.init_db()
    # init_db() calls init_alerts_table() (via schema.py)
    return db._sqlite_path()

def _insert_canonical(db_path, imo, name):
    """Insert a vessels_canonical row needed for get_all_vessel_scores() JOIN."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO vessels_canonical "
        "(canonical_id, entity_name, imo_number) VALUES (?, ?, ?)",
        (f"CAN_{imo}", name, imo),
    )
    conn.commit()
    conn.close()
```

---

## Sources

### Primary (HIGH confidence)
- Direct codebase read: `app.py` lines 105-239 — `_do_score_refresh()`, `_score_changed()`, scheduler wiring
- Direct codebase read: `db/scores.py` lines 1-374 — full DDL, CRUD, `get_score_history()` signature confirmed
- Direct codebase read: `db/__init__.py` — re-export pattern confirmed
- Direct codebase read: `db/schema.py` — dual-backend DDL pattern confirmed; `init_alerts_table()` integration point identified
- Direct codebase read: `templates/dashboard.html` — header structure, existing JS files, alert badge insertion point confirmed
- Direct codebase read: `tests/conftest.py` + `tests/test_scores.py` — fixture pattern confirmed; `_setup_db()` helper pattern; IMO range conventions
- Direct codebase read: `.planning/STATE.md` — confirmed decisions: CSP enforcement, no new Railway services, server-side alert read/unread state in PostgreSQL, `<script type="application/json">` CSP-safe pattern

### Secondary (MEDIUM confidence)
- REQUIREMENTS.md ALRT-01 through ALRT-08 — exact requirement text confirmed; traceability table confirmed Phase 7 scope
- ROADMAP.md Phase 7 section — success criteria confirmed; dependency on Phase 6 confirmed

### Tertiary (LOW confidence — no external verification needed; all architecture is internal)
- None required. All design decisions derive from existing codebase patterns with HIGH confidence.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all patterns directly observed in codebase
- Architecture: HIGH — all patterns (DDL, CRUD, route registration, CSRF exemption, scheduler hook) observed directly from working Phase 6 implementation
- Pitfalls: HIGH — pitfalls derived from actual existing code constraints (CSP active, advisory lock live, indicator_json sparse format confirmed)

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable internal codebase; no external dependency changes)
