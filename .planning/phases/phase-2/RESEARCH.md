# Phase 2: Identity Mismatch Detection and UI Integration - Research

**Researched:** 2025-03-05
**Domain:** AIS Spoofing Detection, SQL, Flask/UI
**Confidence:** HIGH

## Summary

This phase focuses on enhancing the `spoof_detector.py` to identify identity-based anomalies (`ID_MISMATCH`) and integrating spoofing alerts into the dashboard and map. Research confirms that the database already contains tables for `spoof_events`, and the dashboard follows a consistent pattern for behavioral alerts (Dark Periods, STS Events) that can be easily cloned for Spoofing.

**Primary recommendation:** Use `ais_positions` as the source of truth for identity history, as `ais_vessels` only stores the latest state. Implement two distinct identity mismatch sub-types: `IMO_CONFLICT` (one IMO, multiple MMSIs) and `IDENTITY_FLIP` (one MMSI, multiple IMOs/Names).

<user_constraints>
## User Constraints (from CONTEXT.md)

*No CONTEXT.md found; proceeding with user prompt instructions.*

### Locked Decisions
- Logic for `ID_MISMATCH` must detect identity changes during a voyage.
- UI must follow the pattern of STS and Dark Period cards.
- Map visualization should use a Red/Orange color scheme for spoof events.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SPOOF-04 | SQL query for `find_imo_conflicts` | Identified `ais_positions` and `ais_vessels` as target tables. |
| SPOOF-05 | Logic for `ID_MISMATCH` | Defined sub-types: IMO Conflict and Identity Flip. |
| UI-03 | Dashboard Integration | Cloned pattern from `templates/dashboard.html` and `static/app.js`. |
| MAP-02 | Map Visualization | Verified `map_data.py` and `static/map.js` integration points. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12+ | Backend logic | Project standard |
| SQLite / Postgres | Latest | Data storage | Project dual-backend |
| Flask | 3.0+ | Web framework | Project standard |
| Leaflet | 1.9.4 | Map visualization | Project standard |

## Architecture Patterns

### Database Queries (db.py)

#### IMO Conflict Detection
Finds different MMSIs claiming the same IMO number.
```sql
SELECT 
    imo_number, 
    GROUP_CONCAT(DISTINCT mmsi) AS mmsis, 
    COUNT(DISTINCT mmsi) AS mmsi_count
FROM ais_positions
WHERE imo_number IS NOT NULL AND imo_number != ''
GROUP BY imo_number
HAVING COUNT(DISTINCT mmsi) > 1;
```

#### Identity Flip Detection
Finds a single MMSI broadcasting different IMOs over time.
```sql
SELECT 
    mmsi, 
    COUNT(DISTINCT imo_number) AS distinct_imos,
    GROUP_CONCAT(DISTINCT imo_number) AS imos
FROM ais_positions
WHERE mmsi IS NOT NULL
GROUP BY mmsi
HAVING COUNT(DISTINCT imo_number) > 1;
```

### Detection Logic (spoof_detector.py)
The `run_detection` function should be expanded to call these queries.
- `IMO_CONFLICT`: Risk level HIGH/CRITICAL.
- `IDENTITY_FLIP`: Risk level HIGH (often indicates a vessel trying to hide its identity mid-voyage).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Geo-spatial calculation | Custom distance logic | `_haversine` in `spoof_detector.py` | Already implemented and tested. |
| UI Components | Custom Table/Card styles | `.panel`, `.table-wrapper` | Existing CSS maintains consistency. |

## Common Pitfalls

### Pitfall 1: Typo-induced Mismatches
**What goes wrong:** Minor typos in `vessel_name` trigger alerts.
**How to avoid:** Focus primarily on `imo_number` for `ID_MISMATCH`. If using `vessel_name`, use Levenshtein distance or only flag if the name changes completely (e.g., from "HAPPY SHIP" to "SAD TANKER").

### Pitfall 2: Reused MMSIs
**What goes wrong:** Some MMSIs are reused by different vessels over very long periods.
**How to avoid:** Limit the lookback window (e.g., 30 days) to ensure the mismatch is happening "during a voyage".

## Code Examples

### Dashboard Integration Pattern
Clone the STS/Dark Period pattern in `templates/dashboard.html`:
```html
<div class="panel">
  <div class="panel-header">
    <span class="panel-title">Spoofing Alerts</span>
    <span class="text-muted" style="font-size:.7rem;">Indicator 2 — AIS Identity / Location manipulation</span>
  </div>
  <div class="panel-body">
    <!-- Filters and "Run Detection" button -->
    <!-- Table with columns: Risk, MMSI, Vessel, Type, Detected At, Details -->
  </div>
</div>
```

### Map Data Integration
Update `map_data.py` to include `spoof_risk_num` in `get_map_vessels`:
```python
# In map_data.py
spoof_agg = """
    SELECT mmsi, MAX(CASE risk_level ...) as risk_num 
    FROM spoof_events GROUP BY mmsi
"""
# ...
composite_num = max(sanc_num, dp_risk_num, sts_risk_num, spoof_risk_num)
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Manual AIS cross-ref | Automated `ID_MISMATCH` detection | Real-time identification of "identity cloning". |

## Sources

### Primary (HIGH confidence)
- `db.py` - Reviewed existing schema and `spoof_events` table.
- `spoof_detector.py` - Analyzed existing `TELEPORT` detection logic.
- `templates/dashboard.html` - Identified UI patterns for cloning.
- `map_data.py` - Verified risk aggregation logic.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH
- Architecture: HIGH
- Pitfalls: MEDIUM (Requires real-world AIS data to tune name-mismatch sensitivity)

**Research date:** 2025-03-05
**Valid until:** 2025-04-05
