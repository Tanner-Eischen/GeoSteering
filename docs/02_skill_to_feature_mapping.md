# Title
Skill-to-Feature Mapping and Evaluation Rubric

## Purpose
Make the portfolio alignment explicit:
- Each fundamental skill maps to one or more MVP features
- Each skill has observable evidence artifacts
- The demo and report prove competency without requiring StarSteer access

## Skill map
### Skill 1: Multiwell correlation and marker picking
Feature(s):
- Correlation panel: side-by-side logs for multiple wells
- Marker CRUD: add, move, delete markers per well
Evidence:
- Screenshot(s) of correlation panel with picks
- Saved marker file in project
- Short narrative in report describing ties and uncertainty

### Skill 2: Pre-spud planning with target line and DLS constraints
Feature(s):
- Plan builder that outputs MD/inc/azi stations
- DLS computation and constraint warnings
Evidence:
- Plan summary page in report
- Exported plan CSV
- Feasibility summary (max DLS vs computed)

### Skill 3: Interpretation updating while drilling
Feature(s):
- Simulated real-time log reveal stepper
- Interpretation versions (v0, v1, v2...) linked to steps
Evidence:
- Version timeline in UI or report
- Controls showing the update applied at each step
- Decision log entries with justification

### Skill 4: Steering decision making and documentation
Feature(s):
- Decision log with interval, observations, recommendation, risks
- KPI feedback (in-zone percent, distance to target) visible per step
Evidence:
- Decision table in report
- KPI plots
- Traceability from decision to interpretation version

### Skill 5 (optional): Mapping and gridding
Feature(s):
- Simple surface update from control points (IDW) with before/after view
Evidence:
- Map figures in report
- Surface export (CSV grid)

## Evaluation rubric (for demo reviewers)
Score each item 0 to 3:
- 0: Not implemented
- 1: Implemented minimally, hard to use, unreliable
- 2: Works end-to-end, clear artifacts, minor UX issues acceptable
- 3: Polished, robust, demonstrates strong operational thinking

Rubric categories:
- Data ingestion and QC
- Correlation workflow and marker persistence
- Planning and DLS constraint feedback clarity
- Simulation stepper reliability and determinism
- Interpretation versioning and audit trail quality
- Decision logging quality
- Report completeness and reproducibility
- Code quality: tests and modularity
