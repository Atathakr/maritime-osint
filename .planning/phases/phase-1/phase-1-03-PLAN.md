---
phase: phase-1
plan: 03
type: execute
wave: 3
depends_on: [phase-1-02]
files_modified: [app.py, verify_spoof.py]
autonomous: true
requirements: [P1-3, P1-4]
must_haves:
  truths:
    - "API endpoint /api/spoof/run triggers detection"
    - "API endpoint /api/spoof/events lists results"
    - "Detection verified against historical data"
  artifacts:
    - path: "app.py"
      provides: "REST API endpoints for spoof detection"
    - path: "verify_spoof.py"
      provides: "Verification script for end-to-end testing"
  key_links:
    - from: "app.py"
      to: "spoof_detector.run_detection"
      via: "Route handler call"
    - from: "verify_spoof.py"
      to: "/api/spoof/run"
      via: "HTTP POST request"
---

<objective>
Expose the spoof detection logic via REST API and verify the implementation end-to-end.

Purpose: Allow users to trigger detection and view results via the web platform/API.
Output: API endpoints in app.py and a verification script.
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
@.planning/phases/phase-1/phase-1-02-SUMMARY.md
@app.py
@spoof_detector.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Spoof API endpoints to app.py</name>
  <files>app.py</files>
  <action>
    Add the following routes to app.py:
    1. `POST /api/spoof/run`:
       - Validate request using `schemas.SpoofDetectRequest`.
       - Call `spoof_detector.run_detection`.
       - Return summary of found events.
    2. `GET /api/spoof/events`:
       - Paginated list of events from `db.get_spoof_events`.
       - Support filters for mmsi and risk_level.
    
    Ensure `login_required` decorator is used for both.
    Import `spoof_detector` at the top of the file.
  </action>
  <verify>
    Use `curl` or a test script to hit `/api/spoof/run` (with dummy auth or while disabled for testing) and verify it returns a 200 OK with a JSON response.
  </verify>
  <done>Spoof API endpoints are functional and integrated into the Flask app.</done>
</task>

<task type="auto">
  <name>Task 2: Create verification script and run end-to-end test</name>
  <files>verify_spoof.py</files>
  <action>
    Create a script `verify_spoof.py` that:
    1. Injects two `ais_positions` for a test MMSI that are far apart in space but close in time (e.g., > 100km apart, 1 minute delta).
    2. Calls the local Flask API `/api/spoof/run` for that MMSI (or calls the detector directly if preferred for speed).
    3. Asserts that a `TELEPORT` event was created and saved to the DB.
    4. Cleans up the test data.
  </action>
  <verify>
    Run `python3 verify_spoof.py` and ensure it passes all assertions.
  </verify>
  <done>Verification script confirms the teleportation detection pipeline is working as expected.</done>
</task>

</tasks>

<verification>
Verify API responses match the expected JSON structure.
Confirm that the verification script covers the happy path (detection of speed violation).
</verification>

<success_criteria>
- `POST /api/spoof/run` triggers detection and returns summary.
- `GET /api/spoof/events` returns list of events.
- `verify_spoof.py` passes successfully.
</success_criteria>

<output>
After completion, create `.planning/phases/phase-1/phase-1-03-SUMMARY.md`
</output>
