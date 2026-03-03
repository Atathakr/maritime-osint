# Shadow Fleet Framework — Indicator Reference

Full reference for all 31 risk indicators across 6 categories.
Updated as each sprint adds new scoring logic.

**Current date:** 2026-03-02
**Implemented:** 13 of 31 indicators scored (7 not feasible with open-source data)

---

## Scoring Overview

| Status | Count |
|--------|-------|
| ✅ Fully implemented & scored | 13 |
| ⚠️ Partial (detected, limited scoring) | 1 |
| ❌ Not yet implemented | 10 |
| 🚫 Not feasible (no open-source data) | 7 |

### Non-Sanctioned Risk Score Formula

```
risk_score = min(
    min(dp_count × 10, 40)          -- IND1  dark periods
  + min(sts_count × 15, 45)         -- IND7  STS transfers
  + min(sts_zone_count × 5, 10)     -- IND8  STS in high-risk zones
  + flag_tier × 7                   -- IND17 flag risk (max 21, tier 0–3)
  + min(hop_count × 8, 16)          -- IND15 flag hopping
  + min(spoof_count × 8, 24)        -- IND10 speed anomalies
  + min(port_count × 20, 40)        -- IND29 sanctioned port calls
  + min(loiter_count × 5, 15)       -- IND9  loitering
  + max(0, min((age−15) × 3, 15))   -- IND23 vessel age
  + min(owner_hits × 20, 40)        -- IND21 ownership chain sanctions
  + min(psc_count × 10, 20),        -- IND31 PSC detentions
  99                                -- hard ceiling for non-sanctioned
)
```

Sanctioned vessels always score **100** regardless of behavioral indicators.

---

## Category 1 — AIS / Transponder Behavior

| IND | Name | Status | Score Formula | Data Source |
|-----|------|--------|---------------|-------------|
| IND1 | AIS dark periods | ✅ Implemented | +10 pts/event, cap 40 | AISStream WebSocket |
| IND2 | AIS spoofing / GNSS manipulation | ✅ Implemented | +8 pts/event, cap 24 | AIS speed proxy (>50 kt) |
| IND3 | AIS identity discrepancies (name/IMO/MMSI mismatch) | ❌ Not implemented | — | AIS static vs canonical |
| IND4 | Multiple MMSI for same vessel | ❌ Not implemented | — | vessels_canonical cross-ref |
| IND5 | Disabled LRIT | 🚫 Not feasible | — | Requires LRIT receiver subscription |
| IND6 | Incomplete AIS voyage data (blank destination/ETA) | ❌ Not implemented | — | ais_vessels.destination |

### IND1 — AIS Dark Periods
**Implementation:** `dark_periods.py` detects gaps > 2 h in MMSI position stream.
**DB table:** `dark_periods` (mmsi, gap_start, gap_end, gap_hours, last_lat, last_lon, reappear_lat, reappear_lon, risk_zone)
**Threshold:** 2 hours (configurable via API parameter `min_hours`)

### IND2 — Speed Anomalies (AIS Spoofing Proxy)
**Implementation:** `spoofing.py` flags positions with SOG > 50 kt (physical impossibility for surface vessels).
**DB table:** `speed_anomalies`
**Threshold:** `SPEED_ANOMALY_THRESHOLD_KT = 50.0` in `risk_config.py`
**Note:** This is a proxy indicator only. True GNSS spoofing detection requires cross-referencing satellite imagery or cross-receiver correlation.

---

## Category 2 — Vessel Movement & Behavioral Patterns

| IND | Name | Status | Score Formula | Data Source |
|-----|------|--------|---------------|-------------|
| IND7 | STS transfers in open ocean | ✅ Implemented | +15 pts/event, cap 45 | AIS proximity detection |
| IND8 | STS transfers in high-risk zones | ✅ Implemented | +5 pts/event, cap 10 | Zone check on STS midpoint |
| IND9 | Loitering / unusual anchoring | ✅ Implemented | +5 pts/event, cap 15 | AIS SOG + duration analysis |
| IND10 | Abnormal speed profiles | ✅ Implemented | +8 pts/event, cap 24 | SOG > 50 kt threshold |
| IND11 | Vessel-to-vessel proximity (non-STS) | ❌ Not implemented | — | AIS proximity without low SOG |
| IND12 | Destination manipulation (AIS vs actual) | ❌ Not implemented | — | Port arrival vs AIS destination |
| IND13 | Voyage pattern inconsistent with cargo type | 🚫 Not feasible | — | Requires cargo manifest / BoL |
| IND14 | Communication silence (VHF non-response) | 🚫 Not feasible | — | Requires coastal radio monitoring |

### IND7 — Ship-to-Ship Transfers
**Implementation:** `sts_detection.py` — pairs vessels within 0.5 nm with SOG < 3 kt for at least 30 min.
**DB table:** `sts_events` (mmsi1, mmsi2, event_ts, lat, lon, distance_m, risk_zone)

### IND8 — STS in High-Risk Zones
**Implementation:** `sts_detection.py` `_classify_zone()` checks STS midpoint lat/lon against 9 named zones.
**Zones:** Persian Gulf, Strait of Hormuz, Gulf of Oman, Arabian Sea, Red Sea, Gulf of Aden, Riau Islands, Malacca Strait, West Africa
**DB column:** `sts_events.risk_zone` (NULL = open ocean, named string = zone match)
**Query:** `db.get_sts_zone_count(mmsi)` counts WHERE risk_zone IS NOT NULL

### IND9 — Loitering / Unusual Anchoring
**Implementation:** `loitering.py` — SOG < 0.5 kt sustained for > 4 h outside designated anchorage zones.
**DB table:** `loitering_events`

---

## Category 3 — Ownership, Identity & Registration

| IND | Name | Status | Score Formula | Data Source |
|-----|------|--------|---------------|-------------|
| IND15 | Flag hopping | ✅ Implemented | +8 pts/hop, cap 16 | vessel_flag_history |
| IND16 | Frequent name changes | ✅ Implemented | Informational only | AIS name vs canonical name |
| IND17 | High-risk / flag-of-convenience flag state | ✅ Implemented | tier × 7 pts (max 21) | risk_config FLAG_RISK_TIERS |
| IND18 | Opaque / multi-layered beneficial ownership | ❌ Not implemented | — | vessel_ownership chain depth |
| IND19 | Shell company ownership structure | ❌ Not implemented | — | Requires corporate registry data |
| IND20 | Sudden change in registered owner or manager | ❌ Not implemented | — | vessel_ownership change timestamps |
| IND21 | Association with previously sanctioned entities | ✅ Implemented | +20 pts/entity, cap 40 | Fuzzy name match vs vessels_canonical |

### IND15 — Flag Hopping
**Implementation:** `screening.py` counts distinct flags in `vessel_flag_history` for the vessel IMO.
**Formula:** `hop_count = distinct_flags - 1` → score = min(hop_count × 8, 16)

### IND16 — Vessel Name Discrepancy
**Implementation:** `screening.py` `screen_vessel_detail()` compares `ais_vessels.vessel_name` against `vessels_canonical.entity_name`.
**Logic:** Fires when both names are non-empty, differ case-insensitively, and neither is a substring of the other.
**Scoring:** Informational only — displayed as ⚑ signal in profile, no score contribution.

### IND17 — Flag State Risk
**Implementation:** `risk_config.FLAG_RISK_TIERS` + `get_flag_tier()`.
**Tiers:**
- Tier 3 (21 pts): Paris MOU Black List + sanctioned registries (IR, RU, KP, SY, CM, TZ, MD, VN, KM)
- Tier 2 (14 pts): Shadow fleet registries (PW, TG, GA, CK, SL, KH, PA, BI, CV, GN, ST, GQ)
- Tier 1 (7 pts): Large open registries (MH, LR, BS, BZ, AG, BB, VC, KN)
- Tier 0 (0 pts): All other flags

### IND21 — Ownership Chain Sanctions Match
**Implementation:** `screening.py` `_check_ownership_chain()` — for each entity in `vessel_ownership`, runs `db.search_sanctions_by_name()`.
**Threshold:** Any match in the fuzzy name search triggers the flag.
**Score:** min(matched_entities × 20, 40)
**UI:** Displays as "⚠ OWNERSHIP CHAIN EXPOSURE (IND21)" section in vessel profile.

---

## Category 4 — Physical & Operational Characteristics

| IND | Name | Status | Score Formula | Data Source |
|-----|------|--------|---------------|-------------|
| IND22 | Fraudulent documents | 🚫 Not feasible | — | Requires document authentication |
| IND23 | Vessel age (≥ 15 years elevated risk) | ✅ Implemented | +3 pts/yr over 15, cap 15 | vessels_canonical.build_year |
| IND24 | Physical ship modifications | 🚫 Not feasible | — | Requires satellite imagery |
| IND25 | Draught / waterline anomalies | 🚫 Not feasible | — | No open AIS draught enforcement |
| IND26 | Expired / absent class certification | ❌ Not implemented | — | Classification society APIs |

### IND23 — Vessel Age
**Implementation:** `screening.py` `screen_vessel_detail()` computes age from `vessels_canonical.build_year`.
**Formula:** `age_score = max(0, min((current_year − build_year − 15) × 3, 15))`
**Examples:**
- Built 2015 (11 yrs in 2026): 0 pts (below threshold)
- Built 2005 (21 yrs in 2026): +18 → capped at 15 pts
- Built 1995 (31 yrs in 2026): +48 → capped at 15 pts
**Config:** `IND23_AGE_THRESHOLD = 15`, `IND23_PTS_PER_YEAR = 3`, `IND23_CAP = 15` in `risk_config.py`

---

## Category 5 — Financial, Insurance & Cargo

| IND | Name | Status | Score Formula | Data Source |
|-----|------|--------|---------------|-------------|
| IND27 | No P&I insurance / substandard P&I club | ⚠️ Schema only | — | Not yet ingested |
| IND28 | Cargo inconsistencies | 🚫 Not feasible | — | Requires Bill of Lading data |
| IND29 | Port calls to sanctioned / high-risk ports | ✅ Implemented | +20 pts/call, cap 40 | port_calls table vs sanctioned_ports |

### IND29 — Sanctioned Port Calls
**Implementation:** `ports.py` matches AIS vessel positions against a list of sanctioned port bounding boxes.
**DB table:** `port_calls` (mmsi, imo_number, port_name, port_country, sanctions_level, arrival_ts)
**Sanctioned port list:** Maintained in `ports.py` — includes Iranian, Russian, North Korean, and Venezuelan ports.

---

## Category 6 — Port & Geographic Patterns

| IND | Name | Status | Score Formula | Data Source |
|-----|------|--------|---------------|-------------|
| IND30 | Avoidance of PSC-regulated ports | ❌ Not implemented | — | Requires port-call history analysis |
| IND31 | Poor PSC detention / inspection record | ✅ Implemented | +10 pts/detention, cap 20 | Paris MOU / Tokyo MOU CSV |

### IND31 — PSC Detention Record
**Implementation:** `ingest.py` `fetch_psc_detentions(source)` downloads monthly CSV; `db.upsert_psc_detentions()` stores records; `screening.py` queries last 24 months.
**Data sources:**
- Paris MOU: `https://www.parismou.org/sites/default/files/Paris%20MOU%20Detention%20List.csv`
- Tokyo MOU: `https://www.tokyo-mou.org/doc/DetentionList.csv`
**DB table:** `psc_detentions` (imo_number, vessel_name, flag_state, detention_date, release_date, port_name, port_country, authority, deficiency_count)
**Score:** min(detention_count × 10, 20) — counts detentions within last 24 months only
**API endpoint:** `POST /api/ingest/psc/<source>` where source = `paris` or `tokyo`

---

## Not Feasible — Deferred Indicators

These 7 indicators require proprietary data sources unavailable in open-source intelligence:

| IND | Name | Reason |
|-----|------|--------|
| IND5 | Disabled LRIT | Requires LRIT receiver network subscription (commercial) |
| IND13 | Voyage vs cargo inconsistency | Requires cargo manifest / Bill of Lading data (commercial) |
| IND14 | VHF communication silence | Requires coastal radio monitoring network |
| IND22 | Fraudulent documents | Requires document authentication / flag registry API |
| IND24 | Physical ship modifications | Requires satellite imagery (Planet, Maxar) |
| IND25 | Draught / waterline anomalies | AIS draught field is self-reported, not enforced |
| IND28 | Cargo inconsistencies | Requires customs / BoL data (commercial) |

---

## Score Impact Summary (Sprint 10)

**New indicators added this sprint:**

| Indicator | Max Contribution | Typical Signal |
|-----------|-----------------|----------------|
| IND23 (vessel age) | +15 pts | Old tanker, built pre-2010 |
| IND21 (ownership chain) | +40 pts | Owner entity on OFAC list |
| IND31 (PSC detentions) | +20 pts | 2+ detentions in 24 months |
| IND16 (name discrepancy) | Informational | AIS name ≠ canonical |

A vessel that is **not directly sanctioned** but scores across all new indicators:
- Old tanker (built 1998, age 28): IND23 = 15 pts
- Tier 2 flag (Panama): IND17 = 14 pts
- Flag hop × 2: IND15 = 16 pts
- Sanctioned owner entity: IND21 = 20 pts
- 2 PSC detentions: IND31 = 20 pts

**Total: 85 pts → HIGH risk** without any AIS behavioral signals at all.

---

## Implementation Files

| File | Role |
|------|------|
| `screening.py` | Risk scoring engine; `screen_vessel_detail()` assembles all indicators |
| `risk_config.py` | Scoring weights, thresholds, flag tier registry |
| `db.py` | All database queries; schema creation for all tables |
| `ingest.py` | Data downloaders: OFAC SDN, OpenSanctions, PSC MOU lists |
| `app.py` | Flask API endpoints; routes to screening / ingest / detection |
| `ais_listener.py` | Real-time AIS WebSocket consumer |
| `dark_periods.py` | IND1 dark period detector |
| `sts_detection.py` | IND7/IND8 ship-to-ship transfer detector with zone classification |
| `loitering.py` | IND9 loitering detector |
| `spoofing.py` | IND10 speed anomaly / AIS spoofing proxy |
| `ports.py` | IND29 sanctioned port call detector |
| `reconcile.py` | Canonical vessel deduplication |
| `schemas.py` | Pydantic models for all data types |
| `static/app.js` | Frontend: vessel profile renderer, signal rows, ingest controls |
