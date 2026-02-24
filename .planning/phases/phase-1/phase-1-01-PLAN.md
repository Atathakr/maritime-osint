---
phase: phase-1
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [schemas.py, db.py]
autonomous: true
requirements: [P1-1]
must_haves:
  truths:
    - "Database schema includes spoof_events table"
    - "Pydantic models for SpoofEvent and detection requests exist"
  artifacts:
    - path: "schemas.py"
      provides: "SpoofEvent and SpoofDetectRequest schemas"
    - path: "db.py"
      provides: "spoof_events table initialization and CRUD helpers"
  key_links:
    - from: "schemas.py"
      to: "db.py"
      via: "Type hints in database helpers"
---

<objective>
Establish the foundational data structures and database schema for the AIS Spoof Detector.

Purpose: Ensure spoof events can be validated and persisted consistently across both SQLite and Postgres backends.
Output: SpoofEvent Pydantic model and spoof_events database table with upsert/query helpers.
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
@schemas.py
@db.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Define Pydantic schemas for Spoof Detection</name>
  <files>schemas.py</files>
  <action>
    Add the following models to schemas.py:
    1. `SpoofEvent`: Mirroring the structure in spoof_detector_plan.md. Include fields: mmsi, imo_number, vessel_name, spoof_type (TELEPORT|OVERLAND|ID_MISMATCH), detected_at, lat, lon, detail (dict/JSON), risk_level, sanctions_hit (bool), risk_zone, indicator_code.
    2. `SpoofDetectRequest`: Parameters for running detection (mmsi: optional, hours_back: int default 48).
    
    Ensure `ConfigDict(from_attributes=True)` is used for model compatibility.
    Add field serializer for `detected_at` if it's a datetime object.
  </action>
  <verify>
    Run a python script to instantiate SpoofEvent with dummy data and verify it serializes to JSON.
    Example: `python3 -c "from schemas import SpoofEvent; from datetime import datetime; print(SpoofEvent(mmsi='123456789', spoof_type='TELEPORT', detected_at=datetime.now(), lat=0, lon=0, risk_level='HIGH').model_dump_json())"`
  </verify>
  <done>SpoofEvent and SpoofDetectRequest schemas are available in schemas.py and pass basic validation.</done>
</task>

<task type="auto">
  <name>Task 2: Update database schema and implement spoof event helpers</name>
  <files>db.py</files>
  <action>
    1. Update `_init_postgres` and `_init_sqlite` to create the `spoof_events` table.
       - SQLite: id (PK), mmsi, imo_number, vessel_name, spoof_type, detected_at, lat, lon, detail (TEXT/JSON), risk_level, sanctions_hit (INT), risk_zone, indicator_code, created_at.
       - Postgres: Use SERIAL for id, TIMESTAMPTZ for timestamps, JSONB for detail, BOOLEAN for sanctions_hit.
    2. Add `upsert_spoof_events(events: list[dict]) -> int`: Follow the pattern used in `upsert_sts_events` or `upsert_dark_periods`. Use `mmsi, spoof_type, detected_at` as a unique constraint/conflict target if possible, or just insert.
    3. Add `get_spoof_events(limit=200, offset=0, mmsi=None, risk_level=None)`: Standard paginated fetch with filters.
  </action>
  <verify>
    Run `python3 db.py` (if it has a main block) or a script to call `init_db()` and check if the table exists.
    Verify `upsert_spoof_events` by inserting a dummy event and retrieving it with `get_spoof_events`.
  </verify>
  <done>spoof_events table is created and accessible via new db.py helpers.</done>
</task>

</tasks>

<verification>
Check that the database schema is updated in both SQLite (local) and Postgres (via code inspection).
Ensure Pydantic models match the implementation plan.
</verification>

<success_criteria>
- `schemas.py` contains `SpoofEvent` and `SpoofDetectRequest`.
- `db.py` has `spoof_events` table defined and initialized.
- `upsert_spoof_events` and `get_spoof_events` are implemented and functional.
</success_criteria>

<output>
After completion, create `.planning/phases/phase-1/phase-1-01-SUMMARY.md`
</output>
