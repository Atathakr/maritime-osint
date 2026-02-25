---
phase: phase-2
plan: 03
type: execute
wave: 3
depends_on: [phase-2-02]
files_modified: [templates/dashboard.html, static/app.js, static/map.js]
autonomous: true
requirements: [P2-2, P2-3]
must_haves:
  truths:
    - "Spoofing alerts card is visible on the dashboard"
    - "Users can trigger spoof detection from the UI"
  artifacts:
    - path: "templates/dashboard.html"
      provides: "Spoofing Alerts card UI"
    - path: "static/app.js"
      provides: "loadSpoofEvents and runSpoofDetect logic"
---

<objective>
Implement the frontend UI for displaying and triggering spoof detection.
Purpose: Allow users to visualize detected spoofing events and manually run the detection pipeline from the dashboard.
Output: Updated dashboard HTML and JavaScript functionality.
</objective>

<execution_context>
@/home/pshap/.gemini/get-shit-done/workflows/execute-plan.md
@/home/pshap/.gemini/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/phases/phase-2/RESEARCH.md
@templates/dashboard.html
@static/app.js
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Spoofing Alerts card to dashboard.html</name>
  <files>templates/dashboard.html</files>
  <action>
    Add a new card for "Spoofing Alerts" in templates/dashboard.html:
    1. Clone the structure of the "Dark Period Alerts" or "STS Transfer Events" card.
    2. Add a table with ID `spoof-table` to display events.
    3. Include columns: Vessel, Type, Detected At, Risk, Details.
    4. Add a "Run Spoof Detection" button with ID `run-spoof-btn`.
    5. Ensure proper styling consistent with the dashboard's design.
  </action>
  <verify>
    Verify the new card and table are present in templates/dashboard.html.
  </verify>
  <done>
    The dashboard UI now includes a dedicated section for spoofing alerts.
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement spoof event logic in app.js and map.js</name>
  <files>static/app.js, static/map.js</files>
  <action>
    Update frontend logic to handle spoofing events:
    1. In `static/app.js`:
       - Implement `loadSpoofEvents()`: Fetches events from `/api/spoof/events` and populates `spoof-table`.
       - Implement `runSpoofDetect()`: Sends a POST request to `/api/spoof/run`, shows a loading state/toast, and reloads the table upon completion.
       - Wire the "Run Spoof Detection" button to `runSpoofDetect()`.
       - Call `loadSpoofEvents()` during dashboard initialization.
    2. In `static/map.js`:
       - Update marker rendering to handle spoofing events.
       - Implement color distinction: Red for `CRITICAL` risk (e.g., Overland in Phase 3 or high-confidence spoofing) and Orange for `HIGH` risk (Teleportation/Identity Mismatch).
       - Ensure spoofing reasons are displayed in the marker popup.
  </action>
  <verify>
    Verify that `loadSpoofEvents`, `runSpoofDetect`, and map marker updates are correctly implemented.
  </verify>
  <done>
    The dashboard and map now dynamically load, trigger, and visualize spoof detection events.
  </done>
</task>

</tasks>

<verification>
Check dashboard HTML for the new card.
Verify app.js contains the necessary event handling logic.
</verification>

<success_criteria>
The dashboard displays spoofing events and allows manual detection triggers.
</success_criteria>

<output>
After completion, create `.planning/phases/phase-2/phase-2-03-SUMMARY.md`
</output>
