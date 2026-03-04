# Feature Gaps Research

**Domain:** Maritime OSINT dashboard — analyst-grade UX for compliance/screening professionals
**Researched:** 2026-03-03
**Scope:** What features are currently missing or insufficient relative to the target user (maritime analyst, compliance researcher, sanctions screener)?

---

## Summary

The platform has strong data infrastructure but the dashboard does not yet surface its output credibly. An analyst opening the tool today cannot answer three fundamental questions:

1. **Which vessel is highest risk?** — No ranked list of all vessels with scores
2. **How risky is it, exactly?** — Risk level labels exist but numeric scores are not visible
3. **Why did it score that high?** — No indicator-level breakdown showing which flags fired

These three gaps are the primary UX barrier to adoption by any professional audience.

---

## P0 — Required for Analyst Credibility

### F1: Vessel Ranking Table

**What:** A sortable table listing all monitored vessels ranked by composite risk score (descending). Columns: Vessel Name, IMO, Flag, Risk Score (number), Risk Level (label), Last AIS Contact, Sanctions Status.

**Why missing is fatal:** Without this, there is no entry point. An analyst opening the tool has no way to triage 5,000 vessels. The map is useful for spatial context but cannot answer "show me the top 20 riskiest vessels."

**Priority driver:** Every maritime compliance platform (Windward, Pole Star, Sayari) leads with a ranked vessel list. It is table stakes for the professional use case.

**Acceptance criteria:**
- Sortable by composite score descending (default), name, flag, last contact
- Paginated at 50/100/250 rows
- Loads in <500ms using pre-computed scores
- Sanctioned vessels visually distinct (row color or badge)

---

### F2: Risk Score as Number Everywhere

**What:** Replace or supplement the current risk label (LOW / MEDIUM / HIGH / CRITICAL) with the actual numeric score (0-99) in all display contexts: vessel ranking table, vessel profile page, map popup, search results.

**Why:** Labels compress the signal. A vessel at score 65 vs 85 are both "CRITICAL" but the latter is meaningfully more urgent. Analysts working across multiple tools calibrate against numbers, not labels. Labels alone fail audit defensibility ("why did you prioritize vessel X over Y?").

**Acceptance criteria:**
- Score displayed as integer alongside label in all vessel-facing UI elements
- Color coding remains (labels still shown)
- Score visible in map marker popup on click
- Vessel profile header shows score prominently

---

### F3: Data Freshness Stamps

**What:** Every data point shown to an analyst must carry its source and when it was last updated. Specifically: AIS last position timestamp, sanctions screening last run timestamp, risk score computed-at timestamp.

**Why:** Stale data displayed without age context is an intelligence liability. An analyst acting on a score computed 72 hours ago during a gap in AIS data may be wrong. Maritime OSINT tools that omit data age are not trusted by professional users.

**Acceptance criteria:**
- Vessel profile shows "AIS last seen: 3h ago" (relative time)
- Vessel profile shows "Sanctions: screened 2 days ago"
- Vessel profile shows "Risk score: computed 18 min ago"
- Risk score table shows "Scores last refreshed: [timestamp]" in page header
- Stale scores (>2h) flagged with visual indicator

---

### F4: Indicator Point-Contribution Breakdown

**What:** For each vessel's risk score, show which of the 31 indicators fired and how many points each contributed. A collapsed accordion or table on the vessel profile: "Dark period detected (6h gap) — 15 pts", "Sanctioned operator — 25 pts", "Flag state: Panama Tier 2 — 8 pts".

**Why — audit defensibility:** An analyst presenting a vessel to compliance leadership cannot say "the system flagged it." They must be able to say "it was flagged because of a 6-hour AIS gap in the Strait of Hormuz on Jan 15, which triggered Indicator 1 for 15 points, plus sanctioned beneficial owner for 25 points." The point breakdown is the difference between an intelligence tool and a black box.

**Why — workflow:** Analysts use indicator breakdowns to triage false positives quickly. A vessel with score 45 driven entirely by flag state (low quality signal) is deprioritized over score 45 with a dark period in a high-risk zone (high quality signal).

**Acceptance criteria:**
- Vessel profile shows per-indicator breakdown: indicator name, description, points awarded, timestamp of detection
- Indicators grouped by category (AIS Manipulation, Geospatial, Ownership, Regulatory)
- Indicators that did NOT fire shown as greyed-out (shows what was checked)
- Total points shown, capped at 99

---

## P1 — Required for Production-Ready Tool

### F5: Score Explanation Narrative

**What:** A one-paragraph plain-English summary of why a vessel scored what it did. Auto-generated from the indicator breakdown. "This vessel was flagged primarily for a 6-hour AIS blackout in the Persian Gulf (Jan 15), a sanctioned beneficial owner (Rosneft Maritime LLC), and a history of 3 ship-to-ship transfers in international waters."

**Why:** Analysts copy this narrative into investigation notes. Compliance officers forward it to leadership. This bridges the gap between "the tool flagged it" and "here is why."

---

### F6: Risk-Colored Table Rows

**What:** In the vessel ranking table, row background color corresponds to risk level. CRITICAL = light red, HIGH = light orange, MEDIUM = light yellow, LOW = default. Border accent or left bar may be preferable to full row color.

**Why:** Enables at-a-glance triage across hundreds of rows. Analysts scan ranked lists; color makes breaks in risk tier immediately visible.

---

### F7: Vessel Profile Permalink

**What:** Each vessel's profile page has a stable URL by IMO number (e.g., `/vessel/IMO9123456`). The URL can be copied, bookmarked, and shared with colleagues.

**Why:** Without permalinks, analysts cannot reference specific vessels in investigation notes, emails, or audit trails. Sharing findings requires re-navigating the tool.

**Acceptance criteria:**
- Route exists: `GET /vessel/<imo>`
- Returns full vessel profile with risk breakdown, AIS history summary, sanctions status
- URL is IMO-based (stable across name changes)

---

### F8: CSV Export

**What:** From the vessel ranking table, export the current view (with filters applied) as CSV. Columns: IMO, Name, Flag, Risk Score, Risk Level, Sanctions Status, Last AIS, Score Computed At.

**Why:** Standard analyst workflow requires exporting lists for Excel, case management systems, or regulatory reporting. Lacking export means the tool cannot integrate into any existing workflow.

---

## P2 — Analyst Quality of Life

### F9: Vessel Search by IMO / Name / MMSI

**What:** Global search bar that accepts IMO number, vessel name (fuzzy), or MMSI and returns matching vessels with their current risk scores.

**Note:** Basic search may already exist via `/api/screen`. P2 here refers specifically to search accessible from the dashboard header without navigating to a separate screen.

---

### F10: AIS Track Replay

**What:** On the vessel's map view, a slider to replay AIS positions over time. Shows vessel movement over the past 7/30 days.

**Why:** Dark periods and STS transfers are spatial-temporal events. A static map showing current position does not convey the detection. Track replay makes detections explainable and presentable.

**Note:** Deprioritized because it requires significant frontend work and the AIS track data is already stored. Defer until P0/P1 features are live.

---

## Feature Priority Matrix

| ID | Feature | Priority | Effort | Blocks |
|----|---------|----------|--------|--------|
| F1 | Vessel Ranking Table | P0 | Medium | Requires pre-computed scores |
| F2 | Risk Score as Number | P0 | Low | Independent |
| F3 | Data Freshness Stamps | P0 | Low | Requires score computed_at field |
| F4 | Indicator Breakdown | P0 | Medium | Requires indicator JSONB storage |
| F5 | Score Narrative | P1 | Low | Requires F4 |
| F6 | Risk-Colored Rows | P1 | Low | Requires F1 |
| F7 | Vessel Permalink | P1 | Low | Independent |
| F8 | CSV Export | P1 | Low | Requires F1 |
| F9 | Global Search Bar | P2 | Low | API exists |
| F10 | AIS Track Replay | P2 | High | Defer |

---

## Interaction with Other Maturity Areas

- **F1 and F3** depend on Database area: pre-computed scores with `computed_at` must exist before vessel ranking table can be fast and fresh-stamped
- **F4** depends on `indicator_breakdown JSONB` field being stored alongside the composite score
- All P0 features depend on the risk score infrastructure being in place — frontend work should follow, not precede, database changes

---

*Features research: 2026-03-03*
