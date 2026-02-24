# Roadmap: AIS Spoof Detector

## Phase 1: Foundation & Teleportation
**Goal:** Implement the database schema and the first detection signal (speed).

- [ ] **P1-1: Database Schema**
  - Add `spoof_events` table to `db.py`.
  - Implement `upsert_spoof_events` and query helpers.
- [ ] **P1-2: Teleportation Logic**
  - Implement `find_teleport_candidates` in `db.py`.
  - Create `spoof_detector.py` with `TELEPORT` detection logic (haversine math).
- [ ] **P1-3: Core API Wiring**
  - Add `POST /api/spoof/run` to `app.py`.
  - Add `GET /api/spoof/events` to `app.py`.
- [ ] **P1-4: Verification**
  - Validate teleportation detection against NOAA historical data.

## Phase 2: Identity & UI Integration
**Goal:** Add identity mismatch detection and surface events in the dashboard.

- [ ] **P2-1: Identity Mismatch Detection**
  - Implement `find_imo_conflicts` in `db.py`.
  - Add `ID_MISMATCH` logic to `spoof_detector.py`.
- [ ] **P2-2: Dashboard Card**
  - Update `templates/dashboard.html` with a Spoof Events card.
  - Add event list rendering to `static/app.js`.
- [ ] **P2-3: Map Visualization**
  - Implement map markers for spoof events in `static/map.js`.
  - Distinguish event types with colors (Red/Orange).

## Phase 3: Spatial Analysis (Overland)
**Goal:** Implement overland detection requiring external dependencies.

- [ ] **P3-1: Dependency Setup**
  - Add `shapely` and `pyshp` to `requirements.txt`.
  - Sourcing/Downloading Natural Earth land shapefile.
- [ ] **P3-2: Overland Logic**
  - Implement `OVERLAND` detection logic in `spoof_detector.py`.
  - Optimize spatial lookups.
- [ ] **P3-3: Integration & Polish**
  - Wire all signals into the primary `run_detection` entry point.
  - Final risk scoring and sanctions cross-check refinement.
