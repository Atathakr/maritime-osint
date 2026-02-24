# AIS Spoof Detector — Planning Doc
*maritime-osint · February 2026*

---

## Purpose

Add `spoof_detector.py` to the codebase to identify vessels broadcasting implausible or manipulated AIS data. Results persist to a new `spoof_events` table and surface in the dashboard alongside dark periods and STS events.

---

## Detection Signals

### 1. Teleportation (speed violation)
Compare consecutive position fixes per MMSI. If implied speed between two points exceeds a physical maximum, the vessel can't have travelled that path legitimately.

- Query consecutive `ais_positions` rows per MMSI ordered by `position_ts`
- Flag if: `haversine(p1, p2) / time_delta > MAX_SOG_KTS`
- Threshold: **30 kts** (configurable — bulk carriers ~15 kts, tankers ~18 kts)

### 2. Overland track
A position fix on land or in water shallower than the vessel's draft is physically impossible — indicates injected GPS coordinates.

- Use Natural Earth 10m land shapefile (free, ~5 MB)
- Check each fix with shapely: `if Point(lon, lat).within(land_polygon) → flag`
- Optionally cross-check GEBCO bathymetry if draft is available from static data

### 3. MMSI/IMO identity mismatch
AIS static messages broadcast both MMSI and IMO. If a vessel broadcasts an IMO already associated with a different MMSI in the DB, that's a strong identity spoofing signal — common in flag-hopping shadow fleet vessels.

- On each `ShipStaticData` message: does this IMO already map to a different MMSI in `ais_vessels`?
- Also flag: MMSI changes within a voyage (same IMO, new MMSI mid-track)

---

## Database Schema

New table: `spoof_events`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `mmsi` | TEXT | Vessel MMSI |
| `imo_number` | TEXT | If available from static data |
| `vessel_name` | TEXT | From `ais_vessels` lookup |
| `spoof_type` | TEXT | `TELEPORT` \| `OVERLAND` \| `ID_MISMATCH` |
| `detected_at` | TIMESTAMP | When the anomaly was detected |
| `lat` | REAL | Position of anomaly (midpoint for teleport) |
| `lon` | REAL | Position of anomaly |
| `detail` | TEXT | JSON blob: `implied_sog`, `delta_km`, `conflicting_imo`, etc. |
| `risk_level` | TEXT | `HIGH` \| `CRITICAL` |
| `sanctions_hit` | BOOLEAN | Cross-checked against sanctions DB |
| `risk_zone` | TEXT | Named zone or NULL |
| `indicator_code` | TEXT | `IND_SPOOF_T` / `IND_SPOOF_O` / `IND_SPOOF_I` |

---

## Implementation Plan

### New file: `spoof_detector.py`
Mirrors `dark_periods.py` and `sts_detection.py` — one public entry point, persists to DB.

```
run_detection(mmsi=None, hours_back=48)  → list[dict]
summarise(events)                        → dict
```

### Changes to `db.py`
- Add `CREATE TABLE spoof_events` to schema init
- Add `upsert_spoof_events(events)` — same pattern as `upsert_sts_events`
- Add `find_teleport_candidates(hours_back, mmsi)` — returns consecutive position pairs per MMSI
- Add `find_imo_conflicts()` — returns MMSIs broadcasting an IMO already seen on a different MMSI

### Changes to `app.py`
- Add `POST /api/spoof/run` — triggers detection, returns summary
- Add `GET /api/spoof/events` — paginated list for dashboard table

### Changes to dashboard
- Add Spoof Events card alongside Dark Periods and STS Events
- Map markers for OVERLAND and TELEPORT events (distinct colour — red vs orange)

---

## Dependencies

| Package | Use | Install |
|---|---|---|
| `shapely` | Point-in-polygon for overland check | `pip install shapely` |
| Natural Earth land shapefile | Land polygon data | Free download ~5 MB |
| `pyshp` | Load the shapefile | `pip install pyshp` |

`shapely` + `pyshp` alone is sufficient — no need for the full `geopandas` stack.

---

## Risk Scoring

| Spoof Type | Base Risk | Upgrade to CRITICAL if... |
|---|---|---|
| `TELEPORT` | HIGH | Implied SOG > 100 kts OR sanctions hit |
| `OVERLAND` | CRITICAL | Always CRITICAL (physically impossible) |
| `ID_MISMATCH` | HIGH | Either MMSI is on sanctions list |

---

## Build Order

1. Add `spoof_events` schema to `db.py` and run migration
2. **Teleportation check first** — no new dependencies, just SQL + haversine math already in the codebase
3. Wire up `/api/spoof/run` and verify against NOAA historical data
4. MMSI/IMO mismatch check — purely DB-side, no new deps
5. Overland check — requires `shapely` + land data, slightly more setup
6. Dashboard card and map markers

> Start with Step 2. Teleportation requires nothing new and lets you validate the full pipeline end-to-end before adding any dependencies.
