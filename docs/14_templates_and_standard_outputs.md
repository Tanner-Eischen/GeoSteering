# Title
Templates and Standard Outputs

## Objective
Standardize the artifacts that prove competency:
- Decision log schema
- Pre-spud plan summary
- Report section layout

## 1) Decision log template (CSV)
Filename: `exports/decision_log.csv`

Columns:
- step_index (int)
- md_from_ft (float)
- md_to_ft (float)
- revealed_md_ft (float)
- curves_used (string, comma-separated)
- offsets_used (string, comma-separated well names)
- interpretation_version_id (uuid string)
- interpretation_delta_summary (string)
- recommendation_action (HOLD|BUILD|DROP)
- target_inc_deg (float, optional)
- target_azi_deg (float, optional)
- observations (string)
- risk_note (string, optional)
- created_at (ISO timestamp)

Rules:
- append-only
- one row per logged decision

## 2) Pre-spud plan summary template (report section)
Fields:
- Plan name and parameters
- Target window:
  - top/base definition
  - thickness
- DLS constraints:
  - max DLS
  - exceedances count
- Expected markers:
  - list of marker names and expected depths (if available)
- Contingency triggers (MVP text block):
  - "If GR signature deviates > X from typewell, re-evaluate top"
  - "If in-zone percent drops below Y% over last Z ft, adjust inclination"

## 3) Interpretation version summary template
Fields:
- version_id
- derived_from_version_id
- step_index
- rationale
- control points table (md_ft, top_tvd_ft, base_tvd_ft)
- uncertainty band

## 4) Report outline (required sections)
1) Cover page:
  - project name
  - dataset
  - disclaimer (training tool)
2) Data summary and QC
3) Correlation and markers
4) Pre-spud plan and DLS
5) Steering decisions and KPI results
6) Final interpretation
7) Assumptions and limitations

## 5) Plot templates
- Log track plot (GR + RES) with markers
- Correlation panel snapshot
- Plan MD vs TVD
- DLS vs MD
- KPI vs step index
- Interpretation top/base vs MD overlayed with well TVD

## Definition of Done
- Templates are implemented in code
- Exported report uses these templates consistently
- Exports are easy to inspect and reuse
