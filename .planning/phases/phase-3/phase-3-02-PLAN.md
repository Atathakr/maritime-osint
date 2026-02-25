---
phase: phase-3
plan: 02
type: execute
wave: 2
depends_on: [phase-3-01]
files_modified: [spoof_detector.py, test_overland.py]
autonomous: true
requirements: [P3-3]
must_haves:
  truths:
    - "OVERLAND detection is wired into run_detection"
    - "OVERLAND events are correctly scored as CRITICAL risk"
  artifacts:
    - path: "spoof_detector.py"
      contains: ["spoof_type=\"OVERLAND\"", "risk_level=\"CRITICAL\""]
    - path: "test_overland.py"
      provides: "Full detection suite verification"
  key_links:
    - from: "run_detection"
      to: "is_overland"
      via: "Position verification loop"
---

<objective>
Integrate overland detection into the main pipeline, refine risk scoring, and perform E2E verification.
</objective>

<execution_context>
@/home/pshap/.gemini/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@spoof_detector.py
@db.py
@.planning/phases/phase-3/phase-3-01-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Integrate OVERLAND into run_detection</name>
  <files>spoof_detector.py</files>
  <action>
    - Update `run_detection` in `spoof_detector.py` to iterate through recent positions.
    - For each position, call `is_overland(lat, lon)`.
    - If True, create a `SpoofEvent` with `spoof_type="OVERLAND"` and `risk_level="CRITICAL"`.
    - Ensure these events are included in the list passed to `db.upsert_spoof_events`.
  </action>
  <verify>
    <automated>python3 -c "from spoof_detector import run_detection; print('Wired') if 'OVERLAND' in str(run_detection.__code__.co_consts) else print('Missing')"</automated>
  </verify>
  <done>OVERLAND detection wired into the main pipeline.</done>
</task>

<task type="auto">
  <name>Task 2: E2E Verification Suite</name>
  <files>test_overland.py</files>
  <action>
    - Create `test_overland.py`.
    - Mock a set of AIS positions: some at sea (Atlantic), some on land (Sahara Desert, Central Europe).
    - Run `run_detection` and assert that the correct number of OVERLAND events are generated and persisted.
    - Verify that TELEPORT and ID_MISMATCH signals still function alongside OVERLAND.
  </action>
  <verify>
    <automated>pytest test_overland.py</automated>
  </verify>
  <done>Full detection suite verified with high-confidence tests.</done>
</task>

</tasks>
