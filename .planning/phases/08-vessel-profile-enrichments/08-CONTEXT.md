# Phase 8: Vessel Profile Enrichments - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a score trend chart and a change log to the existing vessel profile page (`/vessel/<imo>`). Both read from the Phase 6 history API. Analyst arriving from an alert can see score trajectory and exactly what changed in the last scheduler run, without leaving the profile page.

Creating alerts, ingesting history, or modifying the scheduler are out of scope — data infrastructure is already in place.

</domain>

<decisions>
## Implementation Decisions

### Chart presentation (PROF-01)
- **Library**: Chart.js via CDN (locked in requirements — no npm build pipeline)
- **Y-axis**: Fixed 0–100. Analyst always sees the full risk scale regardless of how narrow the vessel's actual score range is
- **X-axis labels**: Relative timestamps ("3h ago", "1d ago") — matches freshness stamp style used elsewhere on the page
- **Hover tooltips**: Score + risk level + timestamp — e.g. "Score: 72 · HIGH · 6h ago"
- **Data point color**: Each dot colored by risk level at that snapshot (CRITICAL `#dc2626`, HIGH `#ea580c`, MEDIUM `#d97706`, LOW `#16a34a`); line itself stays neutral (dark grey or chart default)
- **Single-point rendering**: A vessel with exactly 1 snapshot renders as a single visible dot — no error state

### Page layout
- **Position**: History section sits between the score hero card and the indicator breakdown card
- **Structure**: Two separate cards, consistent with existing card-per-section pattern:
  1. **"Score History"** card — chart only
  2. **"Recent Changes"** card — change log only
- **Data fetching**: `vessel.js` fetches `/api/vessels/<imo>/history` on page load (same fetch pattern as score data). No lazy loading. History JSON is not server-injected — fetched client-side.

### History edge cases
- **Zero snapshots**: Both cards render with placeholder text:
  - Score History card: "No score history yet — snapshots are recorded when the score changes."
  - Recent Changes card: "No changes recorded yet."
  - (Do not hide the cards — analyst needs to understand the feature exists)
- **Exactly 1 snapshot**: Chart renders single-point. Recent Changes card shows: "No prior snapshot to compare — this is the first recorded score."
- **Identical consecutive snapshots**: Recent Changes shows "No changes since last run" (requirement SC4)

### Change log format (PROF-02)
- **Scope**: Compares snapshot[0] (most recent) vs snapshot[1] (second-most-recent) only — one scheduler run
- **Indicator names**: Full framework name ("Ship-to-ship transfer", "Dark period detected") — not short keys (IND7)
- **Content shown**: Both newly fired AND newly cleared indicators
- **Display order**: Delta → Risk level change → Newly fired → Newly cleared
  - Example: "▲ +12 pts  ·  LOW → MEDIUM  ·  Newly fired: Ship-to-ship transfer  ·  Newly cleared: Dark period detected"
- **No risk level change**: Omit risk level row if level is unchanged between snapshots
- **No fired/cleared indicators**: Omit those rows if no changes — only show rows that have actual content

### Claude's Discretion
- Exact Chart.js configuration options (animation, legend visibility, grid line density)
- CSS dimensions for the chart canvas (reasonable height: ~180–220px)
- Typography and spacing within change log rows
- Whether risk level change uses "→" or another separator

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vessel.js` — 6.7K, established DOM patterns; all history rendering should extend this file. Uses `escHtml()`, `relativeTime()`, `riskBadgeHtml()` helpers already defined.
- `static/style.css` — existing `.card`, `.risk-badge-*`, `.text-muted`, `.text-warn` classes. Extend, don't replace.
- Risk badge colors defined in vessel.js and style.css: CRITICAL `#dc2626`, HIGH `#ea580c`, MEDIUM `#d97706`, LOW `#16a34a`

### Established Patterns
- **Data injection**: Score data injected via `<script id="vessel-score-data" type="application/json">` in vessel.html; JS reads it with `JSON.parse(document.getElementById(...).textContent)`. Use same pattern for any server-side data; history data is client-fetched.
- **CSP enforcement**: No inline scripts in HTML. All logic in `vessel.js`. All data passed via `type="application/json"` script tags or fetched client-side.
- **DOM structure**: Cards rendered in `<main class="main">` as `<div class="card">` blocks. Existing order: back link → header card → score hero card → indicator section.

### Integration Points
- `vessel.html`: Add two new `<div class="card">` blocks between `#score-hero` and `#indicator-section`
- `vessel.js`: Add `initHistorySection(imo)` function called on DOMContentLoaded alongside existing `renderScoreHero()`
- `/api/vessels/<imo>/history` (app.py:580): Returns `{"history": [...]}` where each item has `composite_score`, `risk_level`, `is_sanctioned`, `indicator_json`, `recorded_at`
- `db/scores.py`: `get_score_history(imo, limit=30)` — already used by the API route
- Chart.js: Load via CDN `<script>` tag in vessel.html (no `defer` — must be available before vessel.js runs the chart init)

</code_context>

<specifics>
## Specific Ideas

No specific product references came up. Standard Chart.js line chart with the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 08-vessel-profile-enrichments*
*Context gathered: 2026-03-11*
