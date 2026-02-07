# Traceability Map (Features and Pages ↔ Spec Docs)

Use this map to link every task to one or more spec documents.

## Spec document references (from the MVP zip)
- `00_mvp_goal_and_success_criteria.md`
  - Global goals, measurable success criteria, and non-operational disclaimers.
- `01_mvp_scope_and_non_goals.md`
  - Scope, explicit non-goals, and de-scoping guardrails.
- `02_skill_to_feature_mapping.md`
  - Skill-to-feature mapping and evaluation rubric (portfolio alignment).
- `03_epic_a_project_and_data_loading.md`
  - Project creation/open, well import (survey + LAS), QC, persistence requirements.
- `04_epic_b_single_well_viewer.md`
  - Single well viewer: logs, markers, trajectory, bit position indicator.
- `05_epic_c_multiwell_correlation_panel.md`
  - Correlation panel: multiwell display, marker CRUD, optional display shifts.
- `06_epic_d_planning_target_line_and_dls.md`
  - Planning: target line builder, DLS constraints, export formats.
- `07_epic_e_steering_simulation_console.md`
  - Simulation: stepper, interpretation versioning, decision log, KPIs.
- `08_epic_f_report_export.md`
  - Report export: reproducible PDF report with specific sections.
- `09_data_model_and_persistence.md`
  - Canonical disk layout, Pydantic schemas, persistence rules.
- `10_core_computations_and_algorithms.md`
  - Minimum curvature, DLS, resampling, interpretation evaluation, KPIs.
- `11_ui_screens_and_interactions.md`
  - UI page definitions, global rules, required components by screen.
- `12_milestones_and_delivery_plan.md`
  - Milestone structure and gating acceptance checks.
- `13_demo_script_and_storyboard.md`
  - Demo flow to record and validate end-to-end workflow.
- `14_templates_and_standard_outputs.md`
  - Standard export templates (decision log CSV, report outline, plot templates).
- `15_risks_failure_modes_and_mitigations.md`
  - Risk register and required mitigations (depth basis, determinism, performance).
- `16_dataset_contract_and_synthetic_data_generator.md`
  - Sample data contract and synthetic generator spec to stabilize demos and tests.

## Page / Feature mapping (per UI spec)
- Dashboard, Data QC: `11_ui_screens_and_interactions.md`, `03_epic_a_project_and_data_loading.md`
- Well Viewer: `04_epic_b_single_well_viewer.md`
- Correlation Panel: `05_epic_c_multiwell_correlation_panel.md`
- Planning: `06_epic_d_planning_target_line_and_dls.md`
- Steering Console: `07_epic_e_steering_simulation_console.md`
- Report Export: `08_epic_f_report_export.md`

## Cross-cutting requirements
- Determinism and reproducibility: `00`, `08`, `15`, `16`
- Data model and disk layout: `09`
- Critical math correctness: `10`
