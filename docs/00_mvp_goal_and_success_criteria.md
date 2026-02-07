# Title
Geosteering Workbench MVP: Goal and Success Criteria

## Objective
Build an offline-first geosteering workbench that demonstrates fundamental StarSteer-adjacent competencies:
- Multiwell log correlation and marker picking
- Pre-spud target-line planning with DLS constraints
- Stepwise interpretation updating while "drilling" (simulated real time)
- Steering decision logging with traceability to interpretation state
- Reproducible export of an operations-style report package

This is a portfolio and training artifact, not an operational real-time geosteering system.

## Audience
- Hiring managers, geosteering leads, subsurface software engineers
- The developer (you) and AI coding agents implementing features

## Primary Outcomes (portfolio signal)
1) Demonstrate you can execute the workflow: plan → correlate → update model → steer → report.
2) Demonstrate rigor: data QC, explicit assumptions, uncertainty, audit trail.
3) Demonstrate software craftsmanship: deterministic simulation, reproducible outputs, test coverage on critical math.

## Success Criteria (must be measurable)
### SC-1: End-to-end demo run
Given a project with:
- 3 offset wells (surveys + LAS logs + optional markers)
- 1 active well (survey + LAS logs)
When the user runs the app:
- A pre-spud plan can be created and exported
- A correlation panel can be used to pick markers across offsets
- The steering simulation can be stepped from landing to TD in at least 10 steps
- Each step generates a decision log entry linked to an interpretation version
- A report PDF can be exported and re-generated identically from saved state

Pass condition:
- The app supports at least one complete demo scenario without manual file editing.

### SC-2: Deterministic state and reproducibility
- Re-running the same simulation steps with the same inputs produces identical:
  - Interpretation version history
  - Decision log
  - KPI results
  - Report outputs (content identical; minor timestamp fields may differ only if explicitly allowed)

### SC-3: Credible geosteering artifacts
The exported report contains:
- A pre-spud plan section (target window, target line, DLS constraint summary)
- Correlation panel snapshot(s) with marker picks
- Steering decision table (step-by-step)
- KPI summary (percent in zone, average distance to target)
- Final interpretation summary (top/base model along lateral)

### SC-4: Critical computations validated
The following computations must have unit tests with numerical assertions:
- Minimum curvature trajectory computation
- DLS calculation
- Curve resampling/interpolation to canonical depth basis
- In-zone KPI evaluation

## Constraints and design principles
- Offline-first: no external services required for baseline functionality.
- Opinionated and simple: constrain scope to reduce edge cases.
- Transparent math: avoid black-box algorithms in MVP. Any "assistive" features must be explainable.
- Explicit basis: choose one canonical vertical reference for MVP (recommend TVD). Enforce it consistently.

## Non-operational disclaimer
All UI and docs must clearly state:
- "Training and portfolio tool. Not validated for live operations."
- "No WITSML ingestion in MVP."
- "No guarantees about well safety or operational compliance."

## Definition of Done (global)
- Repo builds and runs on a clean machine
- `pytest` passes
- A sample dataset and demo walkthrough are included
- Exported report can be generated from CI or a script
- All P0 requirements (defined per epic docs) are implemented
