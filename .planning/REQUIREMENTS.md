# Requirements: maritime-osint

**Defined:** 2026-03-10 (v1.1 — Analyst Workflow)
**Core Value:** Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.

---

## v1.0 Requirements (Complete)

All shipped and verified in production. See MILESTONES.md for details.

### Database
- ✅ **DB-01**: db/ package decomposition — schema, ingestion, detection, screening modules
- ✅ **DB-02**: Pre-computed risk scores stored in vessel_scores table
- ✅ **DB-03**: N+1 query patterns eliminated in dashboard data loading
- ✅ **DB-04**: AIS position table archival strategy implemented
- ✅ **DB-05**: Unused Anthropic SDK dependency removed

### Infrastructure & Testing
- ✅ **INF-01**: APScheduler refreshes all vessel scores on 15-minute cycle
- ✅ **INF-02**: Detection logic has automated test coverage (pytest, 151 tests green)
- ✅ **INF-03**: SECRET_KEY enforced via environment variable

### Security
- ✅ **SEC-01**: Rate limiting on login endpoint (Redis-backed, multi-worker safe)
- ✅ **SEC-02**: CSRF protection on state-changing endpoints (flask-wtf)
- ✅ **SEC-03**: Security headers: CSP (enforcement), HSTS, X-Frame-Options, X-Content-Type-Options
- ✅ **SEC-04**: CodeQL false positive alerts addressed
- ✅ **SEC-05**: Session secret enforced via environment variable

### Frontend
- ✅ **FE-01**: Vessel ranking table — sortable columns, paginated 50/100/250, loads <500ms
- ✅ **FE-02**: Numeric risk scores visible everywhere (table, vessel profile, map popup)
- ✅ **FE-03**: Freshness stamps on vessel profile; stale scores visually flagged
- ✅ **FE-04**: Indicator breakdown table — all 31 indicators, fired ones highlighted
- ✅ **FE-05**: Vessel permalink at /vessel/<imo> — stable, bookmarkable
- ✅ **FE-06**: CSV export from ranking table (full fleet, 9 columns)

---

## v1.1 Requirements

### Score History

- [ ] **HIST-01**: System stores a snapshot of each vessel's composite score, risk level, is_sanctioned, and indicator_json each time the scheduler runs and the score has changed from the previous snapshot
- [ ] **HIST-02**: Analyst can retrieve the last 30 score snapshots for any vessel via `/api/vessels/<imo>/history` (used by trend chart and change log)

### Alerting

- [x] **ALRT-01**: Dashboard header shows a notification badge with unread alert count; badge is hidden when count is zero
- [x] **ALRT-02**: Analyst can open an alert panel listing all unread alerts: vessel name, alert type, score at trigger, time since triggered
- [x] **ALRT-03**: Analyst can click any alert to open a detail view showing: before/after composite score, before/after risk level, list of indicators that newly fired, and a "View Vessel →" link to the vessel profile
- [x] **ALRT-04**: Alert is generated when a vessel's risk level crosses a threshold in either direction (LOW↔MEDIUM↔HIGH↔CRITICAL); one alert per crossing event per scheduler run
- [x] **ALRT-05**: Alert is generated when a vessel enters the top 50 highest-scoring vessels list (was not in top 50 in the prior scheduler run)
- [x] **ALRT-06**: Alert is generated when a vessel's `is_sanctioned` field flips from false to true (newly matched against a sanctions list)
- [x] **ALRT-07**: Alert is generated when a vessel's composite score changes by 15 or more points in a single scheduler run
- [x] **ALRT-08**: Analyst can mark individual alerts as read (dismissed); unread badge count decrements accordingly; read alerts remain visible in a "read" section

### Vessel Profile Enrichments

- [ ] **PROF-01**: Vessel profile shows a score trend chart displaying the vessel's composite score over the last 30 snapshots, with timestamps on the x-axis
- [ ] **PROF-02**: Vessel profile shows a change log summarizing what changed in the most recent scheduler run: score delta (e.g. "▲ +12 pts"), risk level change if any, and names of indicators that newly fired or newly cleared since the prior snapshot

### Watchlist

- [ ] **WTCH-01**: Analyst can pin a vessel to their watchlist via a button on the ranking table row or the vessel profile page
- [ ] **WTCH-02**: Analyst can remove a vessel from their watchlist using the same button (toggles)
- [ ] **WTCH-03**: Watchlisted vessels appear pinned to the top of the ranking table with a distinct visual indicator (e.g. pin icon); they appear above all non-pinned vessels regardless of score

### Visual Legibility

- [ ] **VIS-01**: Base body font size increased to at least 15px across dashboard and vessel profile; table row height adjusted to match
- [ ] **VIS-02**: Vertical spacing between dashboard panels and sections increased; table rows have additional padding for breathing room
- [ ] **VIS-03**: Composite score number, risk badge, and section headings are visually dominant relative to supporting data; font weight and size hierarchy established

---

## Future Requirements (v1.2+)

### Alerting Extensions
- Email / webhook alert delivery (SMTP or configurable webhook URL)
- Alert frequency controls (suppress repeated alerts for same vessel within N hours)
- Analyst-configurable threshold values for alerts

### Data Sources
- Equasis ownership/management data integration (beneficial owner opacity indicators)
- EU consolidated + UN Security Council + UK HM Treasury sanctions lists
- Paris MOU / Tokyo MOU PSC inspection and detention records (active ingestion)
- Global Fishing Watch API (AIS manipulation and loitering patterns)

### Indicator Coverage
- Implement remaining 19 unimplemented indicators (currently 12/31 active)
- Beneficial ownership opacity indicators (requires Equasis)

### Analyst Tools
- Saved/named search filters (persist filter state by name)
- Analyst annotations on vessel profiles (freeform notes)
- Vessel comparison view (side-by-side two vessels)

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time WebSocket push updates | Polling sufficient; adds complexity |
| Multi-user auth / RBAC | Single-operator tool |
| Mobile application | Web-first |
| ML-based anomaly detection | Rule-based indicators only |
| Paid data sources (Lloyd's, Refinitiv) | Open data only |
| Email/webhook alerts | Deferred to v1.2+ |
| Cross-device watchlist sync | localStorage acceptable for single operator |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| HIST-01 | Phase 6 | Pending |
| HIST-02 | Phase 6 | Pending |
| ALRT-01 | Phase 7 | Complete |
| ALRT-02 | Phase 7 | Complete |
| ALRT-03 | Phase 7 | Complete |
| ALRT-04 | Phase 7 | Complete |
| ALRT-05 | Phase 7 | Complete |
| ALRT-06 | Phase 7 | Complete |
| ALRT-07 | Phase 7 | Complete |
| ALRT-08 | Phase 7 | Complete |
| PROF-01 | Phase 8 | Pending |
| PROF-02 | Phase 8 | Pending |
| WTCH-01 | Phase 9 | Pending |
| WTCH-02 | Phase 9 | Pending |
| WTCH-03 | Phase 9 | Pending |
| VIS-01 | Phase 10 | Pending |
| VIS-02 | Phase 10 | Pending |
| VIS-03 | Phase 10 | Pending |

**Coverage:**
- v1.1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 — v1.1 roadmap created; traceability fully populated*
