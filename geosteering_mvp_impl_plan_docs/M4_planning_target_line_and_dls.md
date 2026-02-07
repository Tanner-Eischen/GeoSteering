# Milestone 4: Planning (target line + DLS)

**Primary purpose**: show planning competency via target line and DLS constraint feedback, plus exportable deliverables.

**Spec refs**: `06_epic_d_planning_target_line_and_dls.md`, `10_core_computations_and_algorithms.md`, `11_ui_screens_and_interactions.md`, `14_templates_and_standard_outputs.md`.

---

## Issue: M4-PLAN-300 Plan generation engine

**Spec refs**: `06` (math assumptions + outputs), `10` (DLS computation)

**Depends on**: `M1-ALG-040`

**Goal**: generate a plausible plan trajectory and compute DLS warnings.

**Subtasks**
- [x] Implement plan station generator (kickoff → landing build, then lateral hold)
- [x] Compute trajectory outputs (TVD/N/E) using minimum curvature
- [x] Compute DLS deg/100ft between consecutive stations
- [x] Detect and return exceedances list

**Deliverables**
- `app/plan/plan_generator.py`

**Acceptance checks**
- [x] D1: station count as expected for step size
- [x] D2: DLS exceedances appear for aggressive build config

---

## Issue: M4-MODEL-310 Plan persistence and export

**Spec refs**: `09` (plans folder), `06` (export format), `14` (report needs)

**Depends on**: `M1-IO-030`, `M4-PLAN-300`

**Goal**: save plans and export plan CSV with required columns.

**Subtasks**
- [x] Save plan parameters to `plans/<plan_id>.json`
- [x] Save plan stations to `plans/<plan_id>_stations.parquet`
- [x] Implement plan CSV export including required columns:
  - md_ft, inc_deg, azi_deg, tvd_ft, north_ft, east_ft, dls_deg_per_100ft

**Deliverables**
- `app/plan/plan_store.py`
- `app/plan/plan_export.py`

**Acceptance checks**
- [x] D3: export columns and units match spec

---

## Issue: M4-PLOT-320 Planning plots

**Spec refs**: `06` (plot requirements), `14` (plot templates)

**Depends on**: `M4-PLAN-300`

**Goal**: create plan visualization used both in UI and report snapshots.

**Subtasks**
- [x] Plot plan MD vs TVD
- [x] Plot DLS vs MD with threshold line
- [x] Ensure deterministic axis ranges if used later for report

**Deliverables**
- `app/plot/plan_profile.py`
- `app/plot/dls_plot.py`

**Acceptance checks**
- [x] Plots render for typical plan and extreme plan cases

---

## Issue: M4-UI-330 Planning page

**Spec refs**: `06` (P0 requirements), `11` (Planning screen)

**Depends on**: `M2-UI-100`, `M4-PLAN-300`, `M4-MODEL-310`, `M4-PLOT-320`

**Goal**: implement Planning screen with live feedback and exports.

**Subtasks**
- [x] Plan parameter form with validation
- [x] Generate preview plan and show plots
- [x] Exceedance table
- [x] Save plan action
- [x] Export plan CSV action

**Deliverables**
- `app/pages/planning.py`

**Acceptance checks**
- [x] DLS exceedances visible and correct
- [x] CSV export meets format spec

---

## Issue: M4-TEST-340 Planning unit tests

**Spec refs**: `06` tests D1–D3

**Depends on**: `M4-PLAN-300`, `M4-MODEL-310`

**Goal**: prevent regressions in planning math and exports.

**Subtasks**
- [x] Station count test
- [x] DLS exceedance detection test
- [x] Plan CSV export columns test

**Deliverables**
- `tests/test_planning.py`

**Acceptance checks**
- [x] Milestone 4 gate in `12` satisfied
