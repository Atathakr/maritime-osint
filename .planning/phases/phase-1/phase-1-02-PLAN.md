---
phase: phase-1
plan: 02
type: execute
wave: 2
depends_on: [phase-1-01]
files_modified: [db.py, spoof_detector.py]
autonomous: true
requirements: [P1-2]
must_haves:
  truths:
    - "System can identify consecutive AIS positions for a vessel"
    - "Teleportation detection flags speed violations (>30 kts)"
  artifacts:
    - path: "spoof_detector.py"
      provides: "run_detection logic for TELEPORT signal"
  key_links:
    - from: "spoof_detector.py"
      to: "db.find_teleport_candidates"
      via: "Function call to fetch candidate pairs"
    - from: "spoof_detector.py"
      to: "db.upsert_spoof_events"
      via: "Function call to persist results"
---

<objective>
Implement the core logic for detecting AIS "teleportation" (physically impossible speeds).

Purpose: Identify vessels that move faster than the 30-knot physical limit, indicating possible GPS manipulation.
Output: spoof_detector.py module and find_teleport_candidates database helper.
</objective>

<execution_context>
@/home/pshap/.gemini/get-shit-done/workflows/execute-plan.md
@/home/pshap/.gemini/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/spoof_detector_plan.md
@.planning/phases/phase-1/phase-1-01-SUMMARY.md
@db.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add find_teleport_candidates to db.py</name>
  <files>db.py</files>
  <action>
    Implement `find_teleport_candidates(hours_back=48, mmsi=None, limit=5000)`:
    - Use a Window Function (`LEAD` or `LAG`) to pair consecutive `ais_positions` rows for the same MMSI, ordered by `position_ts`.
    - Return a list of pairs (or rows containing current and next position data).
    - Support both SQLite and Postgres syntax (Window functions are supported in both).
    - Ensure it filters by `hours_back`.
  </action>
  <verify>
    Run a test script to call `find_teleport_candidates` and verify it returns pairs of positions for a known MMSI with more than one position in the DB.
  </verify>
  <done>db.py provides a way to fetch consecutive position pairs efficiently.</done>
</task>

<task type="auto">
  <name>Task 2: Implement TELEPORT detection in spoof_detector.py</name>
  <files>spoof_detector.py</files>
  <action>
    Create `spoof_detector.py`:
    1. Implement `_haversine(lat1, lon1, lat2, lon2) -> float` (reuse implementation from dark_periods.py).
    2. Implement `run_detection(mmsi=None, hours_back=48) -> list[dict]`:
       - Fetch candidates using `db.find_teleport_candidates`.
       - For each pair:
         - Calculate distance (km) using haversine.
         - Calculate time delta (hours).
         - Calculate implied SOG (km / hours / 1.852 for knots).
         - If `implied_sog > 30` (configurable), create a `SpoofEvent` dict with type `TELEPORT`.
         - Set `risk_level` to `HIGH`.
       - Call `db.upsert_spoof_events(events)` to persist findings.
       - Return the list of detected events.
    3. Implement `summarise(events) -> dict`: Returns a count of events by type.
  </action>
  <verify>
    Create a mock position pair in the DB (or via mocking) that exceeds 30 knots.
    Run `run_detection` and verify it identifies the spoof and saves it to the DB.
  </verify>
  <done>spoof_detector.py correctly identifies and persists teleportation events.</done>
</task>

</tasks>

<verification>
Ensure haversine math is correct and conversion to knots is accurate.
Verify that consecutive positions are correctly paired by the SQL query.
</verification>

<success_criteria>
- `db.find_teleport_candidates` returns expected data.
- `spoof_detector.py` identifies speed violations correctly.
- Events are persisted to the database.
</success_criteria>

<output>
After completion, create `.planning/phases/phase-1/phase-1-02-SUMMARY.md`
</output>
