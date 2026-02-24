# Roadmap: AIS Spoof Detector

## Phase 1: Foundation & Teleportation
**Goal:** Implement the database schema and the first detection signal (speed).
**Plans:** 3 plans

- [x] phase-1-01-PLAN.md — Foundation (Schemas & DB)
- [x] phase-1-02-PLAN.md — Teleportation Logic
- [x] phase-1-03-PLAN.md — API & Verification

- [x] **P1-1: Database Schema**
- [x] **P1-2: Teleportation Logic**
- [x] **P1-3: Core API Wiring**
- [x] **P1-4: Verification**

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
