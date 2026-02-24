# Milestone Requirements: AIS Spoof Detector

## 1. Functional Requirements

### 1.1 Detection Signals
- **[REQ-1.1.1] Teleportation Detection**: Identify vessels moving faster than a configurable speed threshold (default 30 kts) by comparing consecutive position fixes.
- **[REQ-1.1.2] Overland Detection**: Flag position fixes located on land using Natural Earth 10m shapefiles.
- **[REQ-1.1.3] Identity Mismatch**: Flag instances where an IMO number is associated with multiple MMSIs or when an MMSI changes mid-voyage for the same IMO.

### 1.2 Data Persistence
- **[REQ-1.2.1] Spoof Events Table**: Persist detected anomalies to a `spoof_events` table with columns for MMSI, IMO, type, timestamp, coordinates, and risk level.
- **[REQ-1.2.2] Indicator Codes**: Assign standardized codes for events: `IND_SPOOF_T` (Teleport), `IND_SPOOF_O` (Overland), `IND_SPOOF_I` (Identity).

### 1.3 Risk Scoring
- **[REQ-1.3.1] Risk Levels**: Assign `HIGH` or `CRITICAL` risk based on signal type and severity (e.g., Overland is always `CRITICAL`).
- **[REQ-1.3.2] Sanctions Integration**: Cross-check flagged vessels against existing sanctions data.

### 1.4 API & UI
- **[REQ-1.4.1] Detection Trigger**: Provide an API endpoint (`POST /api/spoof/run`) to trigger analysis for a specific timeframe/MMSI.
- **[REQ-1.4.2] Event Retrieval**: Provide an API endpoint (`GET /api/spoof/events`) for dashboard consumption.
- **[REQ-1.4.3] Dashboard Visualization**: Display spoof events in a dedicated card and map markers on the main dashboard.

## 2. Technical Requirements

### 2.1 Performance & Scalability
- **[REQ-2.1.1] Efficient Queries**: Detection logic must use indexed queries to avoid full table scans.
- **[REQ-2.1.2] Memory Efficiency**: Shapefile lookups for overland detection must be optimized (e.g., using spatial indexing if necessary).

### 2.2 Dependencies
- **[REQ-2.2.1] Libraries**: `shapely` for geometry operations, `pyshp` for shapefile parsing.
- **[REQ-2.2.2] Assets**: Natural Earth 10m land shapefile (~5MB).

### 2.3 Code Standards
- **[REQ-2.3.1] Consistent Patterns**: Match existing patterns in `dark_periods.py` and `sts_detection.py`.
- **[REQ-2.3.2] Type Safety**: Use Pydantic or type hints for event structures.

## 3. Security Requirements
- **[REQ-3.1] Authentication**: Secure API endpoints with existing session-based authentication.
- **[REQ-3.2] Input Validation**: Sanitize all inputs for detection queries (MMSI, time ranges).
