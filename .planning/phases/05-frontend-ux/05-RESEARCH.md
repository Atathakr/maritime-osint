# Phase 5: Frontend UX - Research

**Researched:** 2026-03-09
**Domain:** Flask/Jinja2 templating, vanilla JS, CSS design system extension, CSV generation
**Confidence:** HIGH — all findings based on direct codebase inspection; no speculative claims

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Ranking Table (FE-1, FE-2)**
- 8 columns: `#` | `Score` | `Vessel Name` | `IMO` | `Flag` | `Evidence` | `Last Seen` | `Risk`
- Score is integer 0–100
- Evidence is `X/31` count of fired indicators
- Last Seen is relative time from `computed_at` (not raw AIS timestamp)
- Risk badge is colored pill: CRITICAL `#dc2626`, HIGH `#ea580c`, MEDIUM `#d97706`, LOW `#16a34a`
- Row click navigates to `/vessel/<imo>` permalink
- Pagination: 50/100/250 rows; default 50
- All numeric columns and Last Seen sortable; default sort Score desc
- Risk badge sortable by tier: CRITICAL > HIGH > MEDIUM > LOW
- Client-side text filter bar: filters by vessel name OR IMO in real time
- Filter resets on page load; no URL persistence required
- API: uses existing `/api/vessels/ranking` endpoint
- Evidence count computed client-side: `Object.values(indicator_json).filter(i => i.fired).length`

**Vessel Profile Page (FE-4, FE-5, FE-3)**
- URL: `/vessel/<imo>` — e.g. `/vessel/IMO9811943`
- Template: `templates/vessel.html` (new file)
- API: existing `/api/vessels/<imo>` endpoint
- Layout top-to-bottom: back link → header row → score hero → indicator breakdown table
- Score hero: large numeric score + risk badge pill + freshness stamp beneath
- Freshness stamp: relative time `Computed 2h ago`; if `is_stale=True` append ` · Stale` in amber
- If `computed_at` is NULL: show `Score not computed`
- Same freshness treatment on dashboard table's Last Seen column

**Indicator Breakdown Table (FE-4)**
- 31 rows always shown (all indicators, fired or not)
- Columns: Category | Indicator | Points | Status | Last Fired
- Fired indicators float to top globally (not per-category)
- Fired row: `#fef2f2` background, Status badge = colored pill matching indicator pts weight
- Not-fired row: normal background, Status = `—` (em dash, grey)
- Category column uses subtle section divider
- Indicator metadata (name, category, max pts) embedded in frontend JS/Jinja — no DB table

**Map Popup Enhancement (FE-2)**
- Add numeric score (`Score: 87`) beneath risk level in existing popup
- Add `"View Profile →"` link to `/vessel/<imo>`
- If `composite_score` is NULL: omit score line, keep qualitative risk
- Implementation: follow whichever pattern is used — map_data.py builder OR map.js
- Do not change the qualitative CRITICAL/HIGH risk display

**CSV Export (FE-6)**
- Full fleet always (all vessels with computed scores, regardless of table filter)
- Single "Export CSV" button in dashboard top-right beside pagination controls
- Columns: `vessel_name, imo, mmsi, flag, composite_score, risk_level, evidence_count, computed_at, is_stale`
- `evidence_count` computed server-side
- `computed_at` in ISO 8601 UTC
- `is_stale` as boolean string (`true`/`false`)
- New Flask route: `GET /export/vessels.csv`
- Returns `text/csv` with `Content-Disposition: attachment; filename="maritime-osint-vessels.csv"`
- Same login requirement as all other routes

### Claude's Discretion
None specified.

### Deferred Ideas (OUT OF SCOPE)
- Voyage history timeline on vessel profile
- AIS position map embed on vessel profile
- Per-category score breakdown (radar chart)
- Analyst notes / annotation system
- Dark mode
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FE-1 | Vessel ranking table — sortable, paginated 50/100/250, <500ms, all columns sortable | `get_all_vessel_scores()` returns pre-computed scores via single batch JOIN; `/api/vessels/ranking` exists; client-side sort+filter pattern established in existing `app.js` |
| FE-2 | Numeric score (0-99) displayed alongside risk label everywhere — table, vessel profile, map popup, search | Score stored in `vessel_scores.composite_score`; map popup currently lacks score; `map_data.py` needs JOIN with `vessel_scores` to surface `composite_score` |
| FE-3 | Data freshness stamps — "AIS last seen: Xh ago", "Sanctions screened: X days ago", "Risk score: computed X min ago"; stale scores flagged visually | `vessel_scores.computed_at` + `is_stale` already stored; relative-time formatting is pure client-side JS; staleness threshold is 2h (visual flag) |
| FE-4 | Indicator point-contribution breakdown — per-indicator table with pts, detection timestamp; not-fired indicators greyed out; total shown | `indicator_json` JSONB in `vessel_scores` stores all 31 indicators; `risk_config.py` has indicator metadata; indicator key constants must be embedded in template |
| FE-5 | Vessel profile permalink — stable `GET /vessel/<imo>` route | New Flask route + `templates/vessel.html`; route must be registered before the `/api/vessels/<path:imo>` catch-all (existing precedent in Phase 2) |
| FE-6 | CSV export — from vessel ranking table, exports current filtered view as CSV | New `GET /export/vessels.csv` route; Python `csv` stdlib; evidence_count computed server-side from `indicator_json`; login-required decorator |
</phase_requirements>

---

## Summary

Phase 5 is a pure frontend and routing phase — no schema changes, no new background jobs. All the data infrastructure was built in Phase 2: `vessel_scores` table with `composite_score`, `indicator_json`, `computed_at`, and `is_stale` is live. The API endpoints (`/api/vessels/ranking`, `/api/vessels/<imo>`) are already registered. This phase wires those data sources to visible UI.

The primary technical work is: (1) adding a new `vessel.html` template with the indicator breakdown table, (2) injecting a risk ranking panel into `dashboard.html` backed by the existing ranking API, (3) enhancing the map popup in `map.js` to show numeric score — which requires `map_data.py` to JOIN with `vessel_scores`, and (4) a CSV export route using Python's `csv` stdlib.

The CSS design system (`static/css/`) is mature — variables, badges, tables, pagination, and filter bars all have established patterns. New CSS should extend `static/css/vessels.css` or a new `static/css/ranking.css` rather than modifying existing component styles. The CSP enforcement (Phase 4) means all new JavaScript must live in `static/*.js` files — no inline `<script>` blocks in templates.

**Primary recommendation:** Follow existing patterns precisely. The codebase has consistent conventions for table rendering, badge classes, pagination state, relative time display, and client-side filter bars — all in `static/app.js`. New features should be additive slices of that file (or a dedicated `static/ranking.js`), not framework additions.

---

## Standard Stack

### Core (already installed — no new packages needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | >=3.1.0 | Route registration, `render_template`, CSV response | Already in use |
| Jinja2 | (Flask dep) | `vessel.html` template rendering | Already in use |
| Python `csv` stdlib | 3.11 | Server-side CSV generation | No extra dep; sufficient for this use case |
| Vanilla JS (ES2020) | Browser | Client-side sort, filter, pagination, fetch | Existing pattern throughout `app.js` |

### No New Dependencies Required
All libraries needed for Phase 5 are already installed. The `csv` module is Python stdlib. No npm, no new CDN includes beyond what is already in `dashboard.html`.

**Installation:** none needed.

---

## Architecture Patterns

### Recommended File Structure for Phase 5

```
templates/
  vessel.html              ← NEW: vessel profile page
static/
  ranking.js               ← NEW (or extend app.js): ranking table + filter + pagination
  css/
    ranking.css            ← NEW (or extend vessels.css): ranking table styles
app.py                     ← add /vessel/<imo> + /export/vessels.csv routes
map_data.py                ← extend get_map_vessels_raw() to LEFT JOIN vessel_scores
```

### Pattern 1: Server-Rendered Vessel Profile Page

**What:** Flask route renders a full Jinja2 template, passing vessel data from existing API data as context.

**When to use:** FE-5 (`/vessel/<imo>`) — stable bookmarkable URL that needs to survive browser refresh, link sharing, and bookmarking.

**Key insight:** The existing `openVesselProfile(imo)` function in `app.js` (line 250) currently renders a profile inside `#screen-result` on the dashboard. This must NOT be replaced — it remains for the screening widget. The new `/vessel/<imo>` route is a separate full-page view in `vessel.html`.

**Example route:**
```python
# app.py — register BEFORE /api/vessels/<path:imo> catch-all (Phase 2 precedent)
@app.get("/vessel/<path:imo>")
@login_required
def vessel_profile(imo):
    score_row = db.get_vessel_score(imo)
    vessel = db.get_vessel(imo)
    if not vessel and not score_row:
        return render_template("vessel.html", imo=imo, vessel=None, score=None), 404
    return render_template("vessel.html", imo=imo, vessel=vessel, score=score_row)
```

**CRITICAL:** Register this route BEFORE `/api/vessels/<path:imo>`. Existing comment in `app.py` at line 312 confirms this pattern: "Ranking route registered before /api/vessels/<path:imo> catch-all — prevents Flask consuming 'ranking' as an IMO value."

### Pattern 2: Client-Side Ranking Table

**What:** Fetch all vessels from `/api/vessels/ranking`, render into a `<tbody>`, implement sort and filter in JS.

**When to use:** FE-1 (ranking table) — data already batched server-side; client handles presentation.

**Established pattern in app.js:**
```javascript
// Existing pagination pattern (see sanctions table, lines ~6-8 of app.js)
const PAGE_SIZE = 100;
let sanctionsOffset = 0;

// For ranking table, page-size is user-selectable: default 50
let _rankingData = [];         // all fetched vessels
let _rankingFiltered = [];     // after text filter
let _rankingSortKey = 'composite_score';
let _rankingSortAsc = false;   // default: desc
let _rankingPage = 0;
let _rankingPageSize = 50;     // default

async function loadRankingTable() {
  const data = await apiFetch('/api/vessels/ranking?limit=500');
  _rankingData = data.vessels || [];
  applyRankingFilter();
}

function applyRankingFilter() {
  const q = document.getElementById('ranking-filter').value.trim().toLowerCase();
  _rankingFiltered = q
    ? _rankingData.filter(v =>
        (v.entity_name || '').toLowerCase().includes(q) ||
        (v.imo_number  || '').toLowerCase().includes(q))
    : [..._rankingData];
  sortAndRenderRanking();
}
```

**Note:** The `/api/vessels/ranking` endpoint caps at 500 rows (`limit=min(int(request.args.get("limit", 100)), 500)`). For the ranking table, request `limit=500` to get all scored vessels.

### Pattern 3: Relative Time Formatting

**What:** Pure JS function converting ISO 8601 UTC timestamp to human-readable relative time.

**When to use:** FE-3 (freshness stamps), FE-1 (Last Seen column).

**Implementation (no library needed):**
```javascript
// Source: established JS pattern, no library required
function relativeTime(isoStr) {
  if (!isoStr) return '—';
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 2)   return 'just now';
  if (diffMin < 60)  return `${diffMin}m ago`;
  const h = Math.floor(diffMin / 60);
  if (h < 24)        return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}
```

**Stale detection (FE-3):** `is_stale` is a boolean already on every `vessel_scores` row. The ranking API returns it. No client-side staleness calculation needed.

### Pattern 4: Map Popup Enhancement (map_data.py approach)

**What:** `map_data.py` builds vessel dicts server-side. Add `composite_score` to each dict by LEFT JOINing `vessel_scores` inside `get_map_vessels_raw()`.

**Why map_data.py (not map.js):** The popup HTML is constructed in `map.js`'s `popupHtml(v)` function (line 97). But the data dict `v` is built in `map_data.py`. Adding `composite_score` to the data dict in `map_data.py` is the clean approach — `map.js` then just reads `v.composite_score`.

**Change to `db/vessels.py` — `get_map_vessels_raw()`:**
```python
# Add to SELECT in get_map_vessels_raw():
# vs.composite_score AS composite_score,
# vs.risk_level AS vs_risk_level
# Add to FROM/JOIN:
# LEFT JOIN vessel_scores vs ON av.imo_number = vs.imo_number
```

**Change to `map_data.py` — `get_map_vessels()`:**
```python
results.append({
    ...existing fields...,
    "composite_score": r.get("composite_score"),   # None if no score yet
})
```

**Change to `map.js` — `popupHtml(v)`:**
```javascript
// After the existing risk level badge line:
const scoreLine = (v.composite_score != null)
  ? `<tr><td>Score</td><td><strong>${v.composite_score}</strong></td></tr>`
  : '';
const profileLink = v.imo_number
  ? `<a href="/vessel/${escAttr(v.imo_number)}" style="...">View Profile →</a>`
  : '';
```

### Pattern 5: CSV Export Route

**What:** Flask route that queries `vessel_scores JOIN vessels_canonical`, computes `evidence_count` server-side, and streams CSV response.

**Python csv stdlib pattern:**
```python
import csv
import io
from flask import make_response

@app.get("/export/vessels.csv")
@login_required
def export_vessels_csv():
    rows = db.get_all_vessel_scores()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "vessel_name", "imo", "mmsi", "flag",
        "composite_score", "risk_level", "evidence_count",
        "computed_at", "is_stale",
    ])
    for r in rows:
        ind = r.get("indicator_json") or {}
        evidence_count = sum(1 for v in ind.values() if v.get("fired"))
        writer.writerow([
            r.get("entity_name") or "",
            r.get("imo_number") or "",
            r.get("mmsi") or "",
            r.get("flag_normalized") or "",
            r.get("composite_score") or 0,
            r.get("risk_level") or "",
            evidence_count,
            r.get("computed_at") or "",
            "true" if r.get("is_stale") else "false",
        ])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        'attachment; filename="maritime-osint-vessels.csv"'
    )
    return response
```

**Note:** `get_all_vessel_scores()` already JOINs `vessels_canonical` (for `entity_name`, `flag_normalized`) and `ais_vessels` (for `mmsi`). The returned dicts have all needed fields.

### Pattern 6: Indicator Metadata Embedding

**What:** The 31 indicator names/categories/max_pts are not in a DB table. They must be embedded in the template or in a JS constant.

**CONFIRMED from `screening.py`:** `compute_vessel_score()` only stores indicators that FIRE. Not-fired indicators have no key in `indicator_json`. The dict contains between 0 and 12 keys maximum (only 12 indicators are implemented). The "31 rows always shown" requirement means the UI must iterate a hardcoded `INDICATOR_META` list of 31 indicators and look up each ID in `indicator_json` — absent = not fired.

**Confirmed indicator_json key strings** (from `screening.py`):
```
"IND1"   — AIS Dark Period (dp-based, max 40 pts)
"IND7"   — STS Transfer Event (max 45 pts)
"IND8"   — STS in Risk Zone (max 10 pts)
"IND9"   — Open-water Loitering (max 15 pts)
"IND10"  — Speed Anomaly / AIS Spoofing (max 24 pts)
"IND15"  — Flag Hopping (max 16 pts)
"IND16"  — Name Discrepancy (0 pts — detection only)
"IND17"  — Flag Risk Tier (max 21 pts)
"IND21"  — Ownership-chain Sanctions Match (max 40 pts)
"IND23"  — Vessel Age (max 15 pts)
"IND29"  — Sanctioned Port Call (max 40 pts)
"IND31"  — PSC Detention Record (max 20 pts)
```
Note: Only 12 of the Shadow Fleet Framework's 31 indicators are currently implemented. The remaining 19 are placeholders in `INDICATOR_META` — always shown as not-fired.

**Recommended approach:** Pass `INDICATOR_META` as a Python module-level constant in `app.py` or a `indicators.py` module, then pass it to `vessel.html` via `render_template`. Example:

```python
# module-level constant (app.py or indicators.py)
INDICATOR_META = [
    {"id": "IND1",  "name": "AIS Dark Period",           "category": "Behavior",    "max_pts": 40},
    {"id": "IND7",  "name": "STS Transfer",               "category": "Behavior",    "max_pts": 45},
    {"id": "IND8",  "name": "STS in Risk Zone",           "category": "Behavior",    "max_pts": 10},
    {"id": "IND9",  "name": "Open-water Loitering",       "category": "Behavior",    "max_pts": 15},
    {"id": "IND10", "name": "Speed Anomaly (Spoofing)",   "category": "Behavior",    "max_pts": 24},
    {"id": "IND15", "name": "Flag Hopping",               "category": "Registry",    "max_pts": 16},
    {"id": "IND16", "name": "Name Discrepancy",           "category": "Identity",    "max_pts": 0},
    {"id": "IND17", "name": "Flag Risk Tier",             "category": "Registry",    "max_pts": 21},
    {"id": "IND21", "name": "Ownership-chain Sanctions",  "category": "Ownership",   "max_pts": 40},
    {"id": "IND23", "name": "Vessel Age",                 "category": "Identity",    "max_pts": 15},
    {"id": "IND29", "name": "Sanctioned Port Call",       "category": "Behavior",    "max_pts": 40},
    {"id": "IND31", "name": "PSC Detention Record",       "category": "Compliance",  "max_pts": 20},
    # IND2–IND6, IND11–IND14, IND18–IND20, IND22, IND24–IND28, IND30 — not yet implemented
    # Add placeholder rows for each so the breakdown table always shows 31 rows
]

# In vessel_profile() route:
return render_template("vessel.html", ..., indicator_meta=INDICATOR_META)
```

**Evidence count (for "X/31" column):** Since `indicator_json` only contains fired indicators:
```javascript
// Client-side — all keys in indicator_json are fired indicators
const evidence_count = Object.keys(vessel.indicator_json || {}).length;
// The denominator is always 31 (total framework indicators)
const evidenceStr = `${evidence_count}/31`;
```
This is consistent with CONTEXT.md: `Object.values(indicator_json).filter(i => i.fired).length` — since all stored entries have `fired: true`, counting keys = counting fired.

### Anti-Patterns to Avoid

- **Inline `<script>` blocks in templates:** CSP enforcement mode (`content_security_policy_report_only=False`) in `security.py` blocks inline scripts. All new JS must go in `static/*.js` files.
- **Modifying existing vessel screening widget:** The `openVesselProfile(imo)` function and `renderVesselProfileHtml()` in `app.js` serve the screening panel on the dashboard. Do not touch them — the new permalink is a separate full-page template.
- **Adding per-vessel DB queries in the ranking endpoint:** The existing `get_all_vessel_scores()` is a single batch JOIN query (INF-1 compliant). Do not add per-row enrichment.
- **Putting the `/vessel/<path:imo>` route after `/api/vessels/<path:imo>`:** Flask will consume the vessel IMO as the API path. Must register `/vessel/<path:imo>` before the API catch-all — exactly as the ranking route was registered before `/api/vessels/<path:imo>` in Phase 2.
- **Using `window.location.href` redirect for "View Profile":** The map popup `screenBtn` already uses `openVesselProfile()` (a JS function call). Phase 5 replaces this with a direct `<a href="/vessel/...">` link inside the popup, not a `window.location` call. This preserves right-click/open-in-new-tab behavior.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSV generation | Custom string concatenation | Python `csv` stdlib | Handles quoting, newlines, Unicode edge cases |
| Relative time display | Date arithmetic library | Simple inline JS function (see Pattern 3) | No library needed for "Xh ago / Xd ago" granularity |
| Client-side sort/filter | DataTables, ag-Grid | Vanilla JS sort + filter (established project pattern) | No CDN dependency; keeps CSP simple; pattern already in `app.js` |
| Risk badge classes | Inline style strings | Existing `.risk-badge-critical/high/medium/low` CSS classes | Already defined in `vessels.css`; consistent with existing profile badges |

---

## Common Pitfalls

### Pitfall 1: Flask Route Order — `/vessel/<imo>` vs `/api/vessels/<path:imo>`

**What goes wrong:** If `/vessel/<path:imo>` is registered after `/api/vessels/<path:imo>`, Flask routes `/vessel/IMO1234567` to the API handler, returning JSON instead of the template.

**Why it happens:** Flask uses a catch-all `<path:imo>` on the API route. Any route with matching prefix registered after it gets shadowed.

**How to avoid:** Register `@app.get("/vessel/<path:imo>")` before the existing `@app.get("/api/vessels/<path:imo>")` definition in `app.py`. The existing code at line 315 demonstrates this exact precedent for the ranking route.

**Warning signs:** The `/vessel/IMO1234567` URL returns a JSON object instead of HTML.

### Pitfall 2: indicator_json Key Format Mismatch

**What goes wrong:** If the hardcoded `INDICATOR_META` list uses different key IDs than what `compute_vessel_score()` actually writes into `indicator_json`, the breakdown table shows all indicators as "not fired" even when they should be fired.

**Why it happens:** The indicator JSON keys are defined in `screening.py`/compute logic, not in `risk_config.py`. If you assume key format without reading the compute code, you get silent mismatches.

**How to avoid:** Before hardcoding indicator metadata, grep the actual keys written by `compute_vessel_score()` in `screening.py`. Confirm the exact string keys (`"IND01"`, `"dark_period"`, etc.) before embedding in the template.

**Warning signs:** The indicator breakdown shows zero fired indicators for vessels that clearly have high scores.

### Pitfall 3: CSP Violation — Inline Scripts in `vessel.html`

**What goes wrong:** Adding `<script>` with inline JavaScript to `vessel.html` causes CSP violations (blocked by `script-src: 'self'`). The page renders but JS is silently disabled.

**Why it happens:** Phase 4 set `content_security_policy_report_only=False` — CSP is now enforced, not just reported. Any inline script is blocked.

**How to avoid:** All JS for `vessel.html` must be in a separate static file (e.g. `static/vessel.js`) loaded via `<script src="{{ url_for('static', filename='vessel.js') }}">`.

**Warning signs:** Browser console shows `Content Security Policy: The page's settings blocked the loading of a resource at inline`.

### Pitfall 4: Map Popup Score Field Missing When No Score Computed

**What goes wrong:** Rendering `v.composite_score` without a null guard causes the string `"null"` or `"NaN"` to appear in the popup for vessels without a score row.

**Why it happens:** Not all vessels tracked by the map have entries in `vessel_scores`. Only vessels that have been explicitly scored (via `compute_vessel_score()`) have rows.

**How to avoid:** Always guard: `if (v.composite_score != null)` before rendering the score line. The CONTEXT.md spec is explicit: "If `composite_score` is NULL (no score computed yet): omit score line, keep qualitative risk level."

### Pitfall 5: Pagination State Reset on Filter

**What goes wrong:** When the user types in the filter box, the ranking table shows page 2 of filtered results (from the previous unfiltered state), rendering seemingly empty pages.

**Why it happens:** Not resetting `_rankingPage = 0` when the filter text changes.

**How to avoid:** Always reset page to 0 when filter input changes, before re-rendering. Pattern from existing sanctions table: `sanctionsOffset = 0` on filter change.

### Pitfall 6: `get_all_vessel_scores()` Returns `indicator_json` as dict (Not String)

**What goes wrong:** Calling `JSON.parse()` on a value that is already a parsed dict from Python `json.loads()` raises an error or produces a nested string.

**Why it happens:** `db/scores.py` normalizes `indicator_json` from SQLite TEXT to dict on read (line 172). When the ranking API returns JSON to the browser, `indicator_json` is already a JS object.

**How to avoid:** On the client side, treat `row.indicator_json` as a plain JS object — do not `JSON.parse()` it. The API response already deserializes it.

---

## Code Examples

### Relative Time + Stale Flag (client-side)

```javascript
// For use in ranking table Last Seen column and vessel profile freshness stamp
function relativeTime(isoStr) {
  if (!isoStr) return '—';
  const diffMs  = Date.now() - new Date(isoStr).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 2)  return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const h = Math.floor(diffMin / 60);
  if (h < 24)       return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

// Usage in ranking table row:
const lastSeen = relativeTime(vessel.computed_at);
const staleTag = vessel.is_stale
  ? '<span class="text-warn" title="Score has not been refreshed — AIS data may be outdated"> · Stale</span>'
  : '';
// Render: `${lastSeen}${staleTag}`
```

### Risk Badge HTML (matching existing CSS classes)

```javascript
// Uses existing .risk-badge CSS classes from vessels.css
// CONTEXT.md colors: CRITICAL #dc2626, HIGH #ea580c, MEDIUM #d97706, LOW #16a34a
// Note: existing CSS uses --danger/#ef4444 (close to #dc2626) and --accent/#f97316
// Use the existing CSS class names, not inline hex colors, for consistency
function riskBadgeHtml(level) {
  const cls = {
    CRITICAL: 'risk-badge-critical',
    HIGH:     'risk-badge-high',
    MEDIUM:   'risk-badge-medium',
    LOW:      'risk-badge-low',
  }[level] || 'badge-muted';
  return `<span class="risk-badge ${cls}">${escHtml(level || 'UNKNOWN')}</span>`;
}
```

**Note on CONTEXT.md colors vs existing CSS:** The CONTEXT.md specifies exact hex colors for risk badges. The existing `vessels.css` already has `.risk-badge-critical/high/medium/low` classes with similar but not identical colors (uses CSS variables `--danger`, `--accent`, `--warn`, `--success`). Use the existing CSS classes — do not add inline styles. If the exact CONTEXT.md colors are required, update the CSS variable values or add new classes. Plan 05-01 implementer should make the final call.

### Indicator Breakdown Table Row

```javascript
// Template for a fired indicator row
function indicatorRowHtml(meta, indData) {
  const fired     = indData && indData.fired;
  const pts       = (indData && indData.pts) || 0;
  const firedAt   = (indData && indData.fired_at) ? relativeTime(indData.fired_at) : '—';
  const rowStyle  = fired ? 'background:#fef2f2;' : '';   // light red for fired
  const statusBadge = fired
    ? `<span class="badge badge-red">Fired</span>`
    : `<span style="color:var(--muted);">—</span>`;
  return `<tr style="${rowStyle}">
    <td class="text-muted">${escHtml(meta.category)}</td>
    <td>${escHtml(meta.name)}</td>
    <td>${pts > 0 ? pts : '—'}</td>
    <td>${statusBadge}</td>
    <td>${firedAt}</td>
  </tr>`;
}
```

### CSV Export Route (minimal complete example)

```python
import csv
import io

@app.get("/export/vessels.csv")
@login_required
def export_vessels_csv():
    rows = db.get_all_vessel_scores()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["vessel_name","imo","mmsi","flag",
                "composite_score","risk_level","evidence_count",
                "computed_at","is_stale"])
    for r in rows:
        ind = r.get("indicator_json") or {}
        ev  = sum(1 for v in ind.values() if isinstance(v, dict) and v.get("fired"))
        w.writerow([
            r.get("entity_name",""),
            r.get("imo_number",""),
            r.get("mmsi",""),
            r.get("flag_normalized",""),
            r.get("composite_score",0),
            r.get("risk_level",""),
            ev,
            r.get("computed_at",""),
            "true" if r.get("is_stale") else "false",
        ])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="maritime-osint-vessels.csv"'
    return resp
```

### Map Data Enhancement (map_data.py)

```python
# In get_map_vessels(), after building results:
# Pull composite_scores for all vessels in one query, not per-vessel
# get_map_vessels_raw() must be extended to LEFT JOIN vessel_scores

# In get_map_vessels_raw() SQL (in db/vessels.py):
"""
LEFT JOIN vessel_scores vs ON av.imo_number = vs.imo_number
"""
# Add to SELECT:
"""
vs.composite_score AS composite_score,
"""

# In map_data.get_map_vessels() results.append():
"composite_score": r.get("composite_score"),   # None if no score
```

---

## Key Codebase Facts for Planner

### Existing API Data Shape (from `get_all_vessel_scores()`)
Each returned dict contains:
```
imo_number, composite_score, is_sanctioned, indicator_json (dict),
computed_at, is_stale,
entity_name (from vessels_canonical JOIN),
flag_normalized (from vessels_canonical JOIN),
vessel_type (from vessels_canonical JOIN),
mmsi (from ais_vessels LEFT JOIN — may be None),
last_lat, last_lon, last_seen (from ais_vessels LEFT JOIN — may be None)
```
Note: `risk_level` is NOT returned by `get_all_vessel_scores()`. It must be derived client-side from `composite_score` (or the API must be extended to compute it). Check if Phase 2 added a `risk_level` column to `vessel_scores` — the schema in `db/scores.py` does NOT include it (only `composite_score`, `is_sanctioned`, `indicator_json`, `computed_at`, `is_stale`).

**IMPORTANT:** The `risk_level` field is absent from `vessel_scores` schema. Client-side derivation from `composite_score`:
```javascript
function scoreToRiskLevel(score) {
  if (score === null || score === undefined) return 'UNKNOWN';
  if (score >= 100) return 'CRITICAL';
  if (score >= 70)  return 'HIGH';
  if (score >= 40)  return 'MEDIUM';
  return 'LOW';
}
```
This matches the existing `renderVesselProfileHtml()` thresholds in `app.js` (lines 376-379). These thresholds are confirmed — `compute_vessel_score()` in `screening.py` does not store `risk_level`, so client-side derivation is the authoritative approach.

### CSP Configuration (from `security.py`)
```python
_CSP = {
    "script-src": ["'self'", "https://cdn.jsdelivr.net"],
    "style-src":  ["'self'", "https://cdn.jsdelivr.net"],
    ...
}
```
- `vessel.html` can load `<script src="{{ url_for('static', filename='vessel.js') }}">` — allowed
- No inline scripts, no eval, no `javascript:` href
- No new CDN additions needed

### Existing `openVesselProfile()` Function
Located at `static/app.js` line 250. Currently renders profile into `#screen-result` div on dashboard. This is the existing screening widget behavior. The new `/vessel/<imo>` permalink is a separate server-rendered page. Do not replace `openVesselProfile()`.

The map popup `screenBtn` (lines 120-128 in `map.js`) currently calls `openVesselProfile()`. Phase 5 replaces the screenBtn with a direct `<a href="/vessel/${imo}">View Profile →</a>` link.

### Static CSS Architecture
- `static/style.css` — entry point, `@import`s four files
- `static/css/base.css` — variables, resets, utilities
- `static/css/components.css` — buttons, tables, filter bars, pagination
- `static/css/map.css` — map + Leaflet overrides
- `static/css/vessels.css` — vessel profiles, risk badges, sections

New styles for the ranking table should go in a new `static/css/ranking.css` imported by `style.css`, or appended to `vessels.css` if minimal.

### `get_vessel()` vs `get_vessel_score()` for Vessel Profile Route
- `db.get_vessel(imo)` — queries `vessels_canonical` — returns name, flag, type, aliases, memberships etc.
- `db.get_vessel_score(imo)` — queries `vessel_scores` — returns score data + indicator_json
- Both are needed for the `/vessel/<imo>` route. The profile template needs name (from vessel) and score (from score row).
- `db.search_sanctions_by_imo(imo)` — returns sanctions hits (for sanctions section on profile)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` (no `[tool.pytest]` section — uses defaults) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ --cov=. --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FE-1 | Ranking endpoint returns vessels sorted by score desc | integration | `pytest tests/test_fe.py::test_ranking_sort -x` | ❌ Wave 0 |
| FE-2 | Map data includes composite_score field | unit | `pytest tests/test_fe.py::test_map_data_score -x` | ❌ Wave 0 |
| FE-3 | is_stale flag propagates to ranking API response | integration | `pytest tests/test_fe.py::test_stale_flag -x` | ❌ Wave 0 |
| FE-4 | indicator_json present in /api/vessels/ranking response | integration | `pytest tests/test_fe.py::test_indicator_json -x` | ❌ Wave 0 |
| FE-5 | /vessel/<imo> returns 200 with vessel data | integration | `pytest tests/test_fe.py::test_vessel_permalink -x` | ❌ Wave 0 |
| FE-6 | /export/vessels.csv returns text/csv with correct columns | integration | `pytest tests/test_fe.py::test_csv_export -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_fe.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_fe.py` — covers FE-1 through FE-6; uses existing `conftest.py` fixtures
- [ ] No new conftest needed — existing `conftest.py` already provides `app_client` and DB setup

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `db.py` | `db/` package with sub-modules | Phase 1 | Stable import surface: `import db; db.fn()` |
| No pre-computed scores | `vessel_scores` table + APScheduler | Phase 2 | Dashboard can now be <500ms; no on-demand recompute for UI |
| In-memory CSP / no security headers | flask-talisman, enforce mode | Phase 4 | All JS must be in `static/*.js` files |
| Qualitative-only risk display | Ready for numeric score everywhere | Phase 5 | This phase delivers FE-2 |

---

## Open Questions

1. **RESOLVED: Indicator_json key strings**
   - Confirmed: Keys are `"IND1"`, `"IND7"`, `"IND8"`, `"IND9"`, `"IND10"`, `"IND15"`, `"IND16"`, `"IND17"`, `"IND21"`, `"IND23"`, `"IND29"`, `"IND31"` (12 implemented indicators)
   - Confirmed: `indicator_json` only stores fired indicators — absent key = not fired
   - Confirmed: 19 of 31 Shadow Fleet Framework indicators are not yet implemented; they appear as always-not-fired in the breakdown table
   - See Pattern 6 for full `INDICATOR_META` list

2. **RESOLVED: Risk level thresholds**
   - Confirmed: `compute_vessel_score()` does NOT return `risk_level` — only `composite_score` (int), `is_sanctioned` (bool), `indicator_json` (dict), `computed_at` (str)
   - Confirmed thresholds (consistent across `app.js` lines 376-379 and `screening.py`): sanctioned=CRITICAL (score=100), >=70=HIGH, >=40=MEDIUM, else=LOW
   - Client-side derivation using `scoreToRiskLevel(score)` is confirmed correct

3. **CONTEXTUAL: CONTEXT.md risk badge hex colors vs existing CSS**
   - What we know: CONTEXT.md specifies `#dc2626` (CRITICAL), `#ea580c` (HIGH), `#d97706` (MEDIUM), `#16a34a` (LOW). Existing `vessels.css` uses CSS vars `--danger` (#ef4444), `--accent` (#f97316), `--warn` (#eab308), `--success` (#22c55e).
   - What's unclear: Whether exact CONTEXT.md colors should override existing design system
   - Recommendation: Use existing CSS classes (`.risk-badge-critical` etc.) for the ranking table to maintain visual consistency with the existing vessel profile. The CONTEXT.md colors are close but not identical; implementing them as new CSS vars would require touching Phase 4's tested component CSS. Low risk to keep existing classes.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase read: `app.py` — route registration patterns, existing API endpoints
- Direct codebase read: `db/scores.py` — `vessel_scores` schema, `get_all_vessel_scores()` data shape
- Direct codebase read: `map_data.py` — `get_map_vessels()` structure, how composite risk is built
- Direct codebase read: `static/map.js` — `popupHtml(v)` function, `screenBtn` pattern
- Direct codebase read: `static/app.js` — pagination state, `openVesselProfile()`, `renderVesselProfileHtml()`
- Direct codebase read: `static/css/vessels.css` — existing risk badge CSS classes
- Direct codebase read: `static/css/base.css` — CSS variables and design tokens
- Direct codebase read: `security.py` — CSP enforcement configuration
- Direct codebase read: `templates/dashboard.html` — existing tab/panel structure
- Direct codebase read: `screening.py` — `compute_vessel_score()` indicator key format, risk_level omission, score formula thresholds

### Secondary (MEDIUM confidence)
- Python stdlib `csv` documentation — CSV generation pattern is standard stdlib behavior
- Flask routing documentation — `<path:imo>` catch-all precedence is well-established Flask behavior

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already installed; no external research needed
- Architecture: HIGH — derived directly from reading existing code patterns
- Pitfalls: HIGH — route order, CSP, indicator key format pitfalls identified from direct code reading
- Indicator key format: HIGH — confirmed from direct read of `compute_vessel_score()` in `screening.py`
- Risk level thresholds: HIGH — confirmed `compute_vessel_score()` returns no `risk_level`; `app.js` thresholds verified

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable codebase; no fast-moving dependencies)
