---
phase: phase-2
plan: 02
type: execute
wave: 2
depends_on: [phase-2-01]
files_modified: [db.py, map_data.py]
autonomous: true
requirements: [MAP-02]
must_haves:
  truths:
    - "Vessels with spoofing events are correctly highlighted on the risk map"
    - "Composite risk scores include spoofing signals"
  artifacts:
    - path: "db.py"
      provides: "Updated get_map_vessels_raw with spoofing aggregation"
    - path: "map_data.py"
      provides: "Composite risk calculation including spoof_risk_num"
  key_links:
    - from: "map_data.py"
      to: "db.py"
      via: "get_map_vessels_raw call receiving spoof_risk_num"
---

<objective>
Integrate spoofing detection results into the risk aggregation pipeline for the map and dashboard.
Purpose: Ensure that spoofing anomalies contribute to the overall risk score of a vessel on the map.
Output: Updated risk aggregation logic in db.py and map_data.py.
</objective>

<execution_context>
@/home/pshap/.gemini/get-shit-done/workflows/execute-plan.md
@/home/pshap/.gemini/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/phases/phase-2/RESEARCH.md
@db.py
@map_data.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update get_map_vessels_raw in db.py</name>
  <files>db.py</files>
  <action>
    Update `get_map_vessels_raw` in `db.py` (around line 2100) to include spoofing event risk:
    1. Add a `spoof_agg` CTE to pre-aggregate spoofing risk per MMSI within the `sts_days` window.
    2. Join `spoof_agg` to the main query.
    3. Include `COALESCE(spoof.risk_num, 0) AS spoof_risk_num` in the final SELECT.
    4. Update the `ORDER BY` clause to include `spoof_risk_num` in the behavioral risk sum.
    
    Pattern for `spoof_agg`:
    ```sql
    spoof_agg AS (
        SELECT mmsi, MAX({risk_case}) AS risk_num
        FROM spoof_events
        WHERE detected_at >= {sts_cutoff} -- Reuse sts_days for simplicity or add spoof_days
        GROUP BY mmsi
    )
    ```
  </action>
  <verify>
    Check `get_map_vessels_raw` in `db.py` for `spoof_agg` and `spoof_risk_num`.
  </verify>
  <done>
    The database query for map vessels now returns the highest spoofing risk per vessel.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update composite risk logic in map_data.py</name>
  <files>map_data.py</files>
  <action>
    Update `get_map_vessels` in `map_data.py`:
    1. Extract `spoof_risk_num` from the database results.
    2. Include `spoof_risk_num` in the `composite_num = max(...)` calculation.
    3. Add a human-readable reason to the `reasons` list if `spoof_risk_num > 0`.
    4. Ensure `spoof_risk` label (e.g., HIGH) is included in the returned dictionary if desired for client-side display.
  </action>
  <verify>
    Check `get_map_vessels` in `map_data.py` for `spoof_risk_num` integration.
  </verify>
  <done>
    The map vessel data now reflects spoofing risk in its composite score and reason list.
  </done>
</task>

</tasks>

<verification>
Verify that `get_map_vessels` correctly aggregates risk from all three behavioural signals (Dark Periods, STS, Spoofing).
</verification>

<success_criteria>
Spoofing events contribute to the composite risk level and are listed as a risk reason on the map.
</success_criteria>

<output>
After completion, create `.planning/phases/phase-2/phase-2-02-SUMMARY.md`
</output>
