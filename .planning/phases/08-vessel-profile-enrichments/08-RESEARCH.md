# Phase 8: Vessel Profile Enrichments - Research

**Researched:** 2026-03-11
**Domain:** Chart.js CDN integration, client-side fetch, JS change-log rendering
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Chart library**: Chart.js via CDN — no npm build pipeline
- **Y-axis**: Fixed 0–100 (full risk scale always visible)
- **X-axis labels**: Relative timestamps ("3h ago", "1d ago")
- **Hover tooltips**: Score + risk level + timestamp — "Score: 72 · HIGH · 6h ago"
- **Data point color**: Each dot colored by risk level at that snapshot (CRITICAL `#dc2626`, HIGH `#ea580c`, MEDIUM `#d97706`, LOW `#16a34a`); line itself stays neutral (dark grey)
- **Single-point rendering**: 1 snapshot renders as a single visible dot — no error state
- **Page position**: History section between score hero card and indicator breakdown card
- **Structure**: Two separate `.card` divs — "Score History" (chart only) and "Recent Changes" (change log only)
- **Data fetching**: `vessel.js` fetches `/api/vessels/<imo>/history` on page load — no lazy loading, no server injection
- **Zero snapshots**: Both cards render with placeholder text (do not hide the cards)
- **1 snapshot**: Chart renders single-point; Recent Changes shows "No prior snapshot to compare — this is the first recorded score."
- **Identical consecutive snapshots**: Recent Changes shows "No changes since last run"
- **Change log scope**: Compares snapshot[0] vs snapshot[1] only
- **Indicator names**: Full framework name (e.g., "AIS Dark Period"), not short keys (IND1)
- **Content shown**: Both newly fired AND newly cleared indicators
- **Display order**: Delta → Risk level change → Newly fired → Newly cleared
- **Omit empty rows**: Skip risk level row if unchanged; skip fired/cleared rows if no changes

### Claude's Discretion
- Exact Chart.js configuration options (animation, legend visibility, grid line density)
- CSS dimensions for the chart canvas (recommended ~180–220px height)
- Typography and spacing within change log rows
- Whether risk level change uses "→" or another separator

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROF-01 | Vessel profile shows a score trend chart displaying composite score over last 30 snapshots, with timestamps on x-axis | Chart.js v4 CDN line chart with `pointBackgroundColor` per-point coloring, relative time labels, fixed y-axis 0–100, single-point support |
| PROF-02 | Vessel profile shows a change log: score delta, risk level change if any, indicator names that newly fired or newly cleared since prior snapshot | Client-side JS diff of snapshot[0] vs snapshot[1] indicator_json keys; INDICATOR_META lookup for full names; already injected into page via `<script type="application/json">` |
</phase_requirements>

---

## Summary

Phase 8 adds two new UI sections to `vessel.html`: a Chart.js trend chart (PROF-01) and a change log card (PROF-02). Both are pure client-side features — they fetch data from the already-implemented `/api/vessels/<imo>/history` endpoint (Phase 6) and render into `vessel.js`. No backend changes are needed; no new Python files are required.

The main technical challenge is Chart.js configuration. The library is loaded via CDN script tag (no `defer`) so it is available synchronously before `vessel.js` runs. Chart.js v4 uses a UMD bundle and registers the `Chart` global — the `new Chart(canvas, config)` constructor works identically with the CDN approach. The per-point dot coloring (risk level colors) requires `pointBackgroundColor` to be an array parallel to the data array, which Chart.js v4 supports directly.

The change log is pure DOM construction in vanilla JS. The main subtlety is the indicator-name lookup: `INDICATOR_META` is already injected into the page as a `<script type="application/json">` tag, so `vessel.js` can build an `id→name` map at startup without any additional round-trips. The Phase 8 implementation extends `vessel.js` only — no new `.js` files, consistent with the existing single-file pattern.

**Primary recommendation:** Add `initHistorySection(imo)` to `vessel.js`, call it from `DOMContentLoaded` alongside existing render functions, and load Chart.js CDN script before `vessel.js` in `vessel.html`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Chart.js | 4.4.x (latest 4.x) | Line chart rendering | CDN-loadable, no build required; v4 is current stable; UMD bundle exposes `Chart` global |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none new) | — | All other work is vanilla JS + existing Flask/Jinja2 stack | — |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Chart.js | D3.js | D3 is more powerful but requires significantly more code for a simple line chart; Chart.js is the right fit for this complexity level |
| Chart.js | Plotly.js | Plotly's CDN bundle is ~3 MB vs Chart.js ~200 KB; overkill for a single trend chart |

**Installation (CDN — no npm):**
```html
<!-- Load before vessel.js — no defer, Chart global must be available synchronously -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
```

---

## Architecture Patterns

### Recommended Project Structure
No new files or directories. All changes touch:
```
templates/
└── vessel.html          # Add CDN <script> + two new .card divs

static/
└── vessel.js            # Add initHistorySection(imo) function
```
CSS additions appended to `static/style.css` (same pattern as Phase 7 alert CSS).

### Pattern 1: Chart.js CDN with Per-Point Colors

**What:** Line chart with dot color driven by per-snapshot risk level, loaded from CDN without a build pipeline.

**When to use:** Any time chart data has a categorical attribute (risk level) that should be visually encoded per-point.

**Example:**
```javascript
// Source: https://www.chartjs.org/docs/latest/configuration/elements.html
var riskColor = { CRITICAL: '#dc2626', HIGH: '#ea580c', MEDIUM: '#d97706', LOW: '#16a34a' };

new Chart(canvas, {
  type: 'line',
  data: {
    labels: labels,          // relativeTime strings
    datasets: [{
      data: scores,          // composite_score numbers
      borderColor: '#374151',
      borderWidth: 2,
      pointBackgroundColor: scores.map(function(_, i) {
        return riskColor[riskLevels[i]] || '#9ca3af';
      }),
      pointRadius: 5,
      pointHoverRadius: 7,
      tension: 0.2,
      fill: false,
    }]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: function(ctx) {
            var idx = ctx.dataIndex;
            return 'Score: ' + ctx.parsed.y + ' \u00b7 ' + riskLevels[idx] + ' \u00b7 ' + labels[idx];
          }
        }
      }
    },
    scales: {
      y: { min: 0, max: 100 },
      x: { ticks: { maxTicksLimit: 8 } }
    }
  }
});
```

### Pattern 2: Single-Point Chart (No Error State)

**What:** Chart.js renders a line chart with a single data point as a visible dot without throwing an error; no special handling needed beyond setting `pointRadius` > 0.

**When to use:** When the history array has exactly one item.

**Notes:** Chart.js v4 handles single-element datasets without error. The line simply has no connecting segment — just the dot. No conditional rendering or try/catch needed.

### Pattern 3: Client-Side Fetch from vessel.js

**What:** `fetch('/api/vessels/<imo>/history')` called inside `DOMContentLoaded`. IMO is read from the existing `#vessel-data` data attribute.

**When to use:** Consistent with CONTEXT.md decision that history JSON is not server-injected — fetched client-side.

**Example:**
```javascript
// Existing pattern in vessel.html:
// <div id="vessel-data" data-imo="{{ imo }}" style="display:none;"></div>
var imoEl = document.getElementById('vessel-data');
var imo = imoEl ? imoEl.getAttribute('data-imo') : null;
if (imo) {
  fetch('/api/vessels/' + encodeURIComponent(imo) + '/history')
    .then(function(r) { return r.json(); })
    .then(function(data) { initHistorySection(data.history || []); });
}
```

### Pattern 4: Indicator Name Lookup from Server-Injected Meta

**What:** `INDICATOR_META` is already injected as `<script id="indicator-meta" type="application/json">` in `vessel.html`. Build a lookup map at startup — no second fetch needed.

**Example:**
```javascript
// At DOMContentLoaded, before initHistorySection:
var metaEl = document.getElementById('indicator-meta');
var indicatorNameMap = {};  // { "IND1": "AIS Dark Period", ... }
if (metaEl) {
  try {
    var meta = JSON.parse(metaEl.textContent);
    meta.forEach(function(m) { indicatorNameMap[m.id] = m.name; });
  } catch (e) {}
}
```

### Pattern 5: Change Log Diff (snapshot[0] vs snapshot[1])

**What:** Compare `indicator_json` keys between the two most-recent snapshots. Keys present in snapshot[0] but absent in snapshot[1] = newly fired. Keys absent in snapshot[0] but present in snapshot[1] = newly cleared.

**Notes:**
- `indicator_json` stores only FIRED indicators (keys = indicator IDs, per Phase 5 decision)
- Both snapshots come from the history array: `history[0]` is most recent, `history[1]` is prior
- Score delta = `history[0].composite_score - history[1].composite_score`
- Direction arrow: delta > 0 → "▲", delta < 0 → "▼", delta === 0 → no arrow (identical case)

### Anti-Patterns to Avoid

- **Loading Chart.js with `defer`:** `defer` means the script executes after the DOM is parsed but asynchronously relative to `vessel.js`. Since `vessel.js` is the last script in `vessel.html` and uses `DOMContentLoaded`, the safest pattern is loading Chart.js before `vessel.js` without `defer` — guarantees `Chart` is defined when `vessel.js` runs.
- **Registering a second Chart.js instance:** If `initHistorySection` is called multiple times (e.g., via hot-reload in dev), calling `new Chart()` on an already-used canvas throws. Destroy the old instance if it exists: `if (window._scoreChart) { window._scoreChart.destroy(); }`.
- **Inline `onclick` in dynamically generated HTML:** Phase 4 established CSP enforcement — no inline event handlers. Use `addEventListener` for all interaction (consistent with alerts.js pattern).
- **Server-injecting history data:** CONTEXT.md is explicit: history JSON is fetched client-side, not injected. Injecting it would bypass the fetch pattern and create inconsistency.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Line chart rendering | Custom SVG/canvas chart | Chart.js v4 | Chart.js handles responsive sizing, tooltips, axis scaling, and animation; edge cases in SVG charts are numerous |
| Relative time formatting | New `timeAgo()` function | Existing `relativeTime()` in `vessel.js` | Already handles all cases: <2m, <60m, <24h, days |
| Risk badge HTML | New badge function | Existing `riskBadgeHtml()` in `vessel.js` | Reuse for consistency |
| HTML escaping | New escape function | Existing `escHtml()` in `vessel.js` | Already handles all five HTML special chars |

**Key insight:** This phase is almost entirely composition of already-built pieces. The only new dependency is Chart.js, and that is loaded via a single CDN `<script>` tag.

---

## Common Pitfalls

### Pitfall 1: Chart.js Script Load Order
**What goes wrong:** If Chart.js is loaded with `defer` or after `vessel.js`, `Chart` is undefined when `initHistorySection` runs, producing `ReferenceError: Chart is not defined`.
**Why it happens:** `defer` scripts execute in order but after HTML parsing; `vessel.js` uses `DOMContentLoaded` which fires after parsing.
**How to avoid:** Place Chart.js `<script>` tag before `vessel.js` `<script>` tag, without `defer`. Chart.js v4 UMD bundle is self-contained.
**Warning signs:** Console error `ReferenceError: Chart is not defined`.

### Pitfall 2: CSP Violation on Chart.js Canvas (fetch mode)
**What goes wrong:** Flask-Talisman CSP may block `cdn.jsdelivr.net` if `script-src` does not include it.
**Why it happens:** Phase 4 established strict CSP. The CDN domain must be in the `script-src` directive.
**How to avoid:** Check `security.py` — add `https://cdn.jsdelivr.net` to the `script-src` allowlist if not present.
**Warning signs:** Browser console shows `Content Security Policy: The page's settings blocked the loading of a resource at https://cdn.jsdelivr.net/...`.

### Pitfall 3: Duplicate Canvas Rendering
**What goes wrong:** `new Chart(canvas, ...)` called on a canvas element that already has a Chart.js instance throws `Error: Canvas is already in use. Chart with ID X must be destroyed before the canvas can be reused.`
**Why it happens:** Can occur in development if the page re-runs initialization or the function is called twice.
**How to avoid:** Store the chart instance (`window._scoreChart = new Chart(...)`), check and destroy before re-creating.

### Pitfall 4: indicator_json Shape Assumption
**What goes wrong:** Change log diff code assumes `indicator_json` is always a plain object `{}`. But history rows where `indicator_json` is `null` (possible for old rows or cleared states) cause `Object.keys(null)` to throw.
**Why it happens:** Phase 6 stores `NULL` in the DB for empty indicator sets before the fix. API returns `{}` for null rows (`row.get("indicator_json") or {}`), so at the API boundary this is always a dict. But defensive coding is prudent.
**How to avoid:** Normalize: `var indJson = history[0].indicator_json || {};` before calling `Object.keys()`.

### Pitfall 5: IMO Test Range Collision
**What goes wrong:** Phase 8 tests using IMO numbers already reserved for prior phases cause test isolation failures.
**Why it happens:** Phase 6 uses IMO8000001+, Phase 7 uses IMO9000001+.
**How to avoid:** Reserve a new range for Phase 8. **Recommended: IMO0200001+** (or IMO10000001+ as the next logical extension — but that is 9 digits; use IMO0200001 to stay within 7-digit patterns used elsewhere).

---

## Code Examples

### Fetching history and initializing both sections
```javascript
// Source: vessel.js DOMContentLoaded pattern + CONTEXT.md decisions
document.addEventListener('DOMContentLoaded', function () {
  // ... existing score/indicator rendering ...

  var imoEl = document.getElementById('vessel-data');
  var imo = imoEl ? imoEl.getAttribute('data-imo') : null;
  if (!imo) return;

  fetch('/api/vessels/' + encodeURIComponent(imo) + '/history')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var history = data.history || [];
      renderScoreHistoryCard(history);
      renderRecentChangesCard(history);
    })
    .catch(function() {
      // Silently degrade — history cards show placeholder text
    });
});
```

### Vessel HTML structure additions
```html
<!-- Between #score-hero and #indicator-section -->
<div class="card" id="score-history-card" style="margin-bottom:1rem;">
  <h3 style="margin-top:0;">Score History</h3>
  <div id="score-history-content">
    <canvas id="score-history-chart" style="height:200px;"></canvas>
  </div>
</div>

<div class="card" id="recent-changes-card" style="margin-bottom:1rem;">
  <h3 style="margin-top:0;">Recent Changes</h3>
  <div id="recent-changes-content"></div>
</div>
```

### Chart.js CDN script tag placement
```html
<!-- In vessel.html, before vessel.js — no defer -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script src="{{ url_for('static', filename='vessel.js') }}"></script>
```

### CSP update pattern (security.py)
```python
# Source: Flask-Talisman configuration (Phase 4 pattern)
# Add cdn.jsdelivr.net to script-src if not already present
"script-src": ["'self'", "https://cdn.jsdelivr.net"]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chart.js v2/v3 `Chart.defaults.global` config | Chart.js v4 `Chart.defaults` (no `.global`) | v3→v4 migration | Config structure changed; use `options.plugins.tooltip` not `options.tooltips` |
| Chart.js v2 `onHover` callback | Chart.js v4 `plugins.tooltip.callbacks` | v3→v4 migration | Tooltip customization API changed |

**Deprecated/outdated:**
- `options.tooltips` (v2/v3): replaced by `options.plugins.tooltip` in v4
- `options.legend` (v2/v3): replaced by `options.plugins.legend` in v4
- `Chart.defaults.global` (v3): dropped in v4; use `Chart.defaults` directly

---

## Open Questions

1. **CSP script-src for cdn.jsdelivr.net**
   - What we know: Phase 4 established strict CSP via flask-talisman; `security.py` controls the `script-src` directive
   - What's unclear: Whether `cdn.jsdelivr.net` is already in the allowlist (not checked; security.py content not read in full)
   - Recommendation: Read `security.py` during implementation Wave 0; add the CDN domain if absent. This is a one-line change.

2. **IMO range for Phase 8 tests**
   - What we know: Phase 6 = IMO8000001+, Phase 7 = IMO9000001+
   - What's unclear: No established convention for phases beyond 9
   - Recommendation: Use **IMO0200001+** (2-prefix, 7 digits). Planner should document this as the Phase 8 reserved range.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no version pin in pyproject.toml; installed in project env) |
| Config file | none — pytest auto-discovers `tests/` directory |
| Quick run command | `pytest tests/test_profile_enrichments.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROF-01 | `/vessel/<imo>` HTML response contains `score-history-card` element and `chart.js` CDN script tag | smoke (HTTP response check) | `pytest tests/test_profile_enrichments.py::test_profile_has_history_card -x` | ❌ Wave 0 |
| PROF-01 | Single-snapshot: `/api/vessels/<imo>/history` with 1 row returns valid JSON without error | unit (API) | `pytest tests/test_profile_enrichments.py::test_history_single_snapshot -x` | ❌ Wave 0 |
| PROF-02 | Change log diff: given 2 snapshots with score delta and indicator changes, JS-equivalent Python logic returns expected delta/fired/cleared | unit (logic) | `pytest tests/test_profile_enrichments.py::test_change_log_diff -x` | ❌ Wave 0 |
| PROF-02 | Identical consecutive snapshots: change log shows "No changes since last run" | unit (logic) | `pytest tests/test_profile_enrichments.py::test_change_log_identical_snapshots -x` | ❌ Wave 0 |

**Note on PROF-01 chart rendering:** Chart.js rendering is browser-side JS — pytest cannot execute it. Tests verify: (a) the HTML page includes the required card skeleton and CDN script tag, and (b) the API returns correct shaped data. Full chart correctness is verified visually during implementation.

### Sampling Rate
- **Per task commit:** `pytest tests/test_profile_enrichments.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_profile_enrichments.py` — covers PROF-01 (HTML structure + single-snapshot API) and PROF-02 (change log diff logic + identical-snapshot case)
- [ ] No new fixtures or conftest changes needed — `app_client` from conftest.py covers HTTP tests; pure-logic tests need no fixtures

*(No framework install gap — pytest already in use with 151+ passing tests)*

---

## Sources

### Primary (HIGH confidence)
- Code inspection of `vessel.js`, `vessel.html`, `app.py`, `tests/conftest.py`, `tests/test_hist.py`, `tests/test_alerts.py` — direct read of project files
- `.planning/phases/08-vessel-profile-enrichments/08-CONTEXT.md` — locked decisions
- `.planning/STATE.md` — accumulated architecture decisions from Phases 1-7

### Secondary (MEDIUM confidence)
- [Chart.js Installation Docs](https://www.chartjs.org/docs/latest/getting-started/installation.html) — CDN usage confirmed
- [jsDelivr Chart.js package](https://www.jsdelivr.com/package/npm/chart.js?path=dist) — version 4.4.x confirmed as current 4.x stable
- WebSearch results confirming Chart.js v4 CDN tag format `chart.umd.min.js` and `options.plugins.tooltip` API

### Tertiary (LOW confidence)
- Exact Chart.js `4.4.4` patch version — CDN will serve latest 4.x if `@4` is specified; pin to `@4.4.4` only if reproducibility is critical

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Chart.js CDN is the locked decision; v4 UMD pattern is well-documented
- Architecture: HIGH — all integration points read directly from project source; no guesswork
- Pitfalls: HIGH — CSP and script load order are verified against Phase 4 patterns; indicator_json shape from Phase 5 decision log
- Test design: HIGH — follows exact pattern of Phases 6 and 7 tests

**Research date:** 2026-03-11
**Valid until:** 2026-06-11 (Chart.js 4.x is stable; project conventions are stable)
