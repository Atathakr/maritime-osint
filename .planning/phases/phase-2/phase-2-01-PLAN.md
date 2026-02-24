---
phase: phase-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [db.py, spoof_detector.py]
autonomous: true
requirements: [P2-1, SPOOF-04, SPOOF-05]
must_haves:
  truths:
    - "Identity mismatch detection identifies vessels sharing IMOs or flipping identities"
    - "Spoofing events are persisted to the database with appropriate risk levels"
  artifacts:
    - path: "db.py"
      provides: "find_imo_conflicts and find_identity_flips functions"
    - path: "spoof_detector.py"
      provides: "ID_MISMATCH detection logic in run_detection"
  key_links:
    - from: "spoof_detector.py"
      to: "db.py"
      via: "find_imo_conflicts and find_identity_flips calls"
---

<objective>
Implement the core identity mismatch detection logic in the database and detector layers.
Purpose: Identify vessels that are likely spoofing their identity by using conflicting IMO numbers or changing their reported identity.
Output: Backend functions for identity anomaly detection and updated spoof detector logic.
</objective>

<execution_context>
@/home/pshap/.gemini/get-shit-done/workflows/execute-plan.md
@/home/pshap/.gemini/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/phases/phase-2/RESEARCH.md
@db.py
@spoof_detector.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement Identity Mismatch queries in db.py</name>
  <files>db.py</files>
  <action>
    Add two new functions to db.py:
    1. `find_imo_conflicts(days=30)`: Finds different MMSIs claiming the same IMO number in ais_positions.
    2. `find_identity_flips(days=30)`: Finds a single MMSI broadcasting different IMOs over time in ais_positions.
    
    Implementation details:
    - Use a lookback window of 30 days (default) to focus on current voyage anomalies.
    - Handle both SQLite (`GROUP_CONCAT`) and Postgres (`STRING_AGG`) syntax for the aggregations if necessary, or use a more basic approach if string aggregation isn't strictly required for the detection logic itself (though useful for details).
    - Ensure queries ignore null or empty IMO numbers.
  </action>
  <verify>
    Check db.py for the new functions.
    Automated check: `python3 -c "import db; print('find_imo_conflicts' in dir(db) and 'find_identity_flips' in dir(db))"`
  </verify>
  <done>
    Both functions are implemented and follow the project's database-agnostic patterns.
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement ID_MISMATCH logic in spoof_detector.py</name>
  <files>spoof_detector.py</files>
  <action>
    Expand the `run_detection` function in `spoof_detector.py` to include identity mismatch detection:
    1. Call `db.find_imo_conflicts()` and `db.find_identity_flips()`.
    2. For each conflict found, create a `SpoofEvent` with `spoof_type='ID_MISMATCH'`.
    3. Categorize sub-types in the `detail` field (e.g., `conflict_type: 'IMO_CONFLICT'` or `'IDENTITY_FLIP'`).
    4. Assign `risk_level='HIGH'` for these events.
    5. Perform sanctions cross-reference using MMSI and IMO.
    6. Upsert the new events using `db.upsert_spoof_events`.
    
    Ensure `schemas.SpoofEvent` is used for validation (see `spoof_detector.py` lines 86-107 for pattern).
  </action>
  <verify>
    Check `run_detection` in `spoof_detector.py` for ID_MISMATCH logic.
    Run `python3 -c "import spoof_detector; print('run_detection' in dir(spoof_detector))"`
  </verify>
  <done>
    ID_MISMATCH events are correctly identified and persisted when `run_detection` is called.
  </done>
</task>

</tasks>

<verification>
Check for existence of `find_imo_conflicts` and `find_identity_flips` in `db.py`.
Verify `spoof_detector.py` calls these new functions and handles the results.
</verification>

<success_criteria>
Detection logic identifies identity mismatches and persists them to the `spoof_events` table.
</success_criteria>

<output>
After completion, create `.planning/phases/phase-2/phase-2-01-SUMMARY.md`
</output>
