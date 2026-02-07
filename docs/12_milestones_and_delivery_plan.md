# Title
Milestones and Delivery Plan

## Objective
Define an implementation sequence with gating acceptance checks so an AI coding agent can deliver incrementally without scope creep.

## Milestone 1: Data ingestion + persistence baseline
Scope:
- Project create/open
- Import survey CSV, compute trajectory
- Import LAS logs, normalize curves
- Save to disk, reopen

Gate:
- Unit tests for parsing + round-trip pass
- One well loads and displays QC summary

Deliverables:
- Data model scaffolding
- Persistence layer
- CLI script: `import_well`

## Milestone 2: Single well viewer
Scope:
- Log plotting GR + RES
- Marker overlay
- Trajectory plot MD vs TVD

Gate:
- Viewer renders for active well and offset wells
- Performance acceptable on sample dataset

Deliverables:
- Plotting module producing PNG snapshots for later report

## Milestone 3: Correlation panel + marker CRUD
Scope:
- Multiwell side-by-side log display
- Marker add/edit/delete
- Persist markers

Gate:
- Markers persist across restart
- Panel supports at least 3 wells

Deliverables:
- Marker schema and editor UI

## Milestone 4: Planning module
Scope:
- Plan generation
- DLS computation and warnings
- Export plan CSV

Gate:
- DLS exceedance detection tested
- Plan export meets format spec

Deliverables:
- Plan model and UI screen

## Milestone 5: Steering simulation console
Scope:
- Stepper reveal mechanism
- Interpretation versioning
- Decision log
- KPI computation

Gate:
- Deterministic stepping test passes
- Can run full demo steering session end-to-end

Deliverables:
- Simulation engine module
- Interpretation module
- KPI module

## Milestone 6: Report export
Scope:
- One-click report PDF generation
- Include key plots and tables

Gate:
- Report generation works headlessly (CLI)
- Report contains required section headers and non-empty content

Deliverables:
- Report generator module
- Template assets

## Optional Milestone 7: Mapping/gridding
Scope:
- Surface update from control points
- Before/after maps

Gate:
- Surface generation test on synthetic control points passes
- Export included in report

## CI and quality gates
- `pytest` required
- Static checks (optional): ruff, mypy
- Deterministic outputs: lock random seeds for synthetic data and any sampling

## Definition of Done
- All P0 epics implemented
- Sample dataset included
- Demo script can be executed as documented
