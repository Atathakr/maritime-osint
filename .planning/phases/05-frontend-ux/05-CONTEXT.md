# Phase 5 — Frontend UX: Implementation Context

_Created by discuss-phase. Decisions here are locked for researcher and planner agents._

---

## 1. Ranking Table Design (FE-1, FE-2)

### Layout — Expanded (8 columns)
Each row: `#` | `Score` | `Vessel Name` | `IMO` | `Flag` | `Evidence` | `Last Seen` | `Risk`

- **Score**: integer 0–100
- **Evidence**: `X/31` (fired indicator count / total indicators)
- **Last Seen**: human-readable relative time (`2h ago`, `3d ago`) from `computed_at` — not raw AIS timestamp
- **Risk badge**: colored pill — CRITICAL (red `#dc2626`), HIGH (orange `#ea580c`), MEDIUM (amber `#d97706`), LOW (green `#16a34a`)
- **Row click**: navigates to vessel permalink `/vessel/<imo>`
- **Pagination**: page-size selector 50 / 100 / 250 rows; default 50

### Sorting + Filter
- All numeric columns sortable (Score, Evidence): click header to toggle asc/desc; default sort is Score desc
- Last Seen sortable (newest first = freshest data)
- Risk badge sortable by tier: CRITICAL > HIGH > MEDIUM > LOW
- **Client-side text filter bar** above the table: filters by vessel name OR IMO in real time (no server round-trip)
- Filter input resets to empty on page load; no URL persistence required

### API backing
- Uses existing `/api/vessels/ranking` endpoint (built in Phase 2)
- Endpoint already returns `composite_score`, `risk_level`, `computed_at`, `is_stale`, `indicator_json`
- Count fired indicators client-side: `Object.values(indicator_json).filter(i => i.fired).length`

---

## 2. Vessel Profile Page (FE-4, FE-5, FE-3)

### URL structure
- Permalink: `/vessel/<imo>` (e.g., `/vessel/IMO9811943`)
- Template: `templates/vessel.html` (new file)
- API backing: existing `/api/vessels/<imo>` endpoint (app.py route already exists)

### Page layout — top to bottom
1. **Back link** — `← Back to dashboard` (top-left)
2. **Header row** — vessel name (h1) + flag emoji + IMO + MMSI
3. **Score hero** — large numeric score (e.g. `87`) with risk badge pill beside it, freshness stamp directly beneath (`Computed 3h ago · Stale` or `Computed 3h ago`)
4. **Indicator breakdown table** (FE-4) — all 31 indicators, see Section 3
5. _(Optional — no scope for Phase 5)_ Map embed, voyage history

### Freshness stamp rules (FE-3)
- Show `computed_at` as relative time: `Computed 2h ago`
- If `is_stale = True`: append ` · ⚠ Stale` in amber; tooltip: "Score has not been refreshed — AIS data may be outdated"
- If `computed_at` is NULL (vessel has no score yet): show `Score not computed`
- Same freshness treatment on dashboard table rows (Last Seen column is `computed_at`)

---

## 3. Indicator Breakdown Table (FE-4)

### Structure
One row per indicator = 31 rows always shown (all indicators, fired or not).

| Column | Content |
|--------|---------|
| Category | e.g. `Ownership`, `Behavior` |
| Indicator | Short name from framework |
| Points | Numeric pts assigned to this indicator |
| Status | `Fired` (colored) or `—` (grey) |
| Last Fired | Relative time if `fired_at` present, else `—` |

### Fired vs. not-fired display
- **Fired indicators float to top** within their category group (or globally — global float preferred, simpler)
- Fired row: highlighted background (`#fef2f2` light red), Status badge = colored pill matching risk level of that indicator's pts weight
- Not-fired row: normal background, Status = `—` (em dash, grey)
- Category column uses a subtle section divider (no heavy borders)

### Data source
- `indicator_json` JSONB structure per indicator: `{"pts": 15, "fired": true, "fired_at": "2025-03-01T12:00:00Z"}`
- Indicator metadata (name, category, max pts) must be embedded in the frontend or served from a static config — no DB table for indicator metadata exists; embed in JS or Jinja

---

## 4. Map Popup Enhancement (FE-2)

### What changes
- Existing map popup shows: vessel name, flag, risk level (CRITICAL/HIGH/MEDIUM/LOW), last position
- Phase 5 adds: **numeric score** (e.g., `Score: 87`) displayed beneath the risk level
- Phase 5 adds: **"View Profile →"** link pointing to `/vessel/<imo>`
- If `composite_score` is NULL (no score computed yet): omit score line, keep qualitative risk level

### Implementation
- `map_data.py` already builds popup HTML string — add score and permalink to the popup builder
- OR: map popups are constructed in `static/map.js` — check which pattern is used and follow it
- Do not change the qualitative CRITICAL/HIGH risk display — add numeric score as a supplementary line

---

## 5. CSV Export (FE-6)

### Scope: Full fleet always
- Exports all vessels with computed scores, regardless of current table sort/filter
- Predictable behavior — analysts know exactly what they get
- Single **"Export CSV"** button in dashboard top-right (beside pagination controls)

### Columns exported
`vessel_name, imo, mmsi, flag, composite_score, risk_level, evidence_count, computed_at, is_stale`

- `evidence_count` = count of fired indicators (computed server-side before sending CSV)
- `computed_at` in ISO 8601 format (UTC), not humanized
- `is_stale` as boolean string (`true`/`false`)

### Implementation
- New Flask route: `GET /export/vessels.csv`
- Returns `text/csv` with `Content-Disposition: attachment; filename="maritime-osint-vessels.csv"`
- Queries `vessel_scores` joined with `vessels` table for all vessels
- No authentication bypass — same login requirement as all other routes

---

## 6. Code Context (for planner agents)

```
Key files:
  templates/dashboard.html      — main dashboard (ranking table goes here)
  templates/vessel.html          — NEW (vessel profile + indicator breakdown)
  templates/login.html           — untouched
  static/css/style.css           — existing styles (extend, don't replace)
  static/map.js                  — Leaflet map + popup builder
  app.py                         — Flask routes (add /vessel/<imo> + /export/vessels.csv)
  map_data.py                    — popup HTML builder (may need score/permalink added)

Existing API endpoints (Phase 2):
  GET /api/vessels/ranking        — returns ranked vessels with scores
  GET /api/vessels/<imo>          — returns single vessel with full indicator_json

vessel_scores schema:
  imo TEXT PK, composite_score INT, risk_level TEXT, indicator_json JSONB,
  computed_at TIMESTAMP, is_stale BOOLEAN

indicator_json structure (per indicator key):
  { "pts": 15, "fired": true, "fired_at": "2025-03-01T12:00:00Z" }
```

---

## Deferred ideas (not in Phase 5 scope)
- Voyage history timeline on vessel profile
- AIS position map embed on vessel profile
- Per-category score breakdown (radar chart)
- Analyst notes / annotation system
- Dark mode
