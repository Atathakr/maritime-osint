---
name: New indicator proposal
about: Propose an implementation for one of the 31 shadow fleet framework indicators
title: "[INDICATOR] IND__ — "
labels: indicator, enhancement
assignees: ''
---

## Indicator Reference

**Code and name:** (e.g., IND11 — Vessel-to-vessel proximity, non-STS)

**Framework category:**
- [ ] Category 1 — AIS / Transponder Behavior
- [ ] Category 2 — Vessel Movement & Behavioral Patterns
- [ ] Category 3 — Ownership, Identity & Registration
- [ ] Category 4 — Physical & Operational Characteristics
- [ ] Category 5 — Financial, Insurance & Cargo
- [ ] Category 6 — Port & Geographic Patterns

**Current status in `docs/indicators.md`:**
(If "Not feasible", explain why you believe it has become feasible.)

---

## Data Source

| Field | Detail |
|---|---|
| Source name | |
| URL | |
| Format | CSV / JSON / XML / API |
| Update frequency | |
| License / terms | |
| Authentication required | Yes / No |

---

## Detection Logic

Describe the proposed algorithm. Include specific thresholds and decision
criteria.

**Proposed thresholds:**

| Parameter | Proposed Value | Rationale |
|---|---|---|

---

## Scoring Proposal

| Component | Value |
|---|---|
| Points per event | |
| Maximum cap | |
| Formula | `min(count × N, CAP)` |

Justify the weighting relative to the existing formula in `docs/indicators.md`.

---

## Implementation Sketch

- [ ] New detection module or extension of existing one
- [ ] New DB table and query functions in `db.py`
- [ ] Scoring in `screening.py` → `screen_vessel_detail()`
- [ ] Constants in `risk_config.py`
- [ ] API endpoint in `app.py`
- [ ] Updated `docs/indicators.md`

---

## Validation Approach

How will you confirm correct results and measure false positive rate? Is there
published research supporting the threshold values?

---

## References

- [ ] C4ADS research
- [ ] EPRS shadow fleet reports
- [ ] Windward / maritime intelligence reports
- [ ] UN Panel of Experts reports
- [ ] Academic papers
- [ ] Other:
