# Title
Epic E: Steering Simulation Console (Simulated Real-Time)

## Objective
Provide a deterministic stepwise simulation that reveals active well logs progressively and supports:
- Comparing active well to offsets/typewell
- Updating interpretation (top/base model along MD)
- Recording a steering decision with justification
- Tracking KPIs (in-zone percent, distance to target)

This is the core portfolio differentiator.

## Core concepts
### Simulation step
A step reveals an incremental MD interval of the active well logs.
Example:
- step size = 100 ft
- step n reveals logs up to md = landing_md + n*100

### Interpretation version
At each step, the user may update the interpretation:
- top target depth vs MD (TVD)
- base target depth vs MD (TVD)
- uncertainty envelope

Each update creates a new immutable interpretation version linked to:
- previous version id
- the step id
- rationale text

### Decision log entry
Each step can create an append-only decision entry referencing:
- interpretation version id used
- MD interval considered
- recommendation (hold/build/drop with optional target inc)
- risk notes

## Functional requirements
### P0
- Configure simulation:
  - select active well
  - select offset wells
  - select guiding curves (default GR and RES)
  - step size (ft)
- Step controls:
  - Step forward
  - Step backward (optional; if implemented, must restore state deterministically)
  - Jump to step (optional)
- Views:
  - Active well log viewer with bit position and revealed depth limit
  - Offset comparison view (mini correlation) in the same depth window
  - Current interpretation display (top/base along MD)
- Interpretation update UI:
  - add/update control point at current MD: top_tvd_ft, base_tvd_ft
  - or apply a global shift to top/base for a window
  - rationale text required for each version
- Decision log UI:
  - add entry per step
  - fields: observations, recommendation, risk note
  - link to interpretation version id
- KPIs:
  - percent-in-zone over revealed interval
  - average distance to center of zone (TVD distance)
  - last-step in-zone value

### P1
- Step backward with full state rollback
- Auto-snapshot plots per step for report

### P2
- Assistive suggestion:
  - compute "distance to top/base" vs MD and highlight deviations
  - no automatic decision making

## Data and state
Simulation state must be saved as part of project:
- `simulation_config.json`
- `simulation_state.json` including:
  - current step index
  - revealed_md_ft
  - interpretation version ids list per step (if any)
  - decision ids per step (if any)

## Interpretation model (MVP)
Represent top/base as piecewise linear functions of MD:
- A list of control points sorted by MD: (md_ft, top_tvd_ft), (md_ft, base_tvd_ft)
- Between points, linearly interpolate.
- Outside points, extrapolate using end slopes or hold constant (choose one and document it).

Uncertainty model (MVP):
- A constant +/- tvd_ft band, or piecewise constant by MD window.

## KPI definition (MVP)
For each MD sample in the revealed interval:
- compute wellbore TVD from trajectory at that MD
- compute top_tvd and base_tvd from interpretation model at that MD
- in-zone if top_tvd <= well_tvd <= base_tvd (assuming top is shallower than base)
- distance to zone center = abs(well_tvd - (top_tvd+base_tvd)/2)

Aggregate:
- percent_in_zone = mean(in_zone)
- avg_center_distance = mean(distance_to_center)

## Edge cases
- Top/base reversed (base above top). Must detect and error.
- Missing trajectory TVD at some MD (interpolate trajectory)
- Sparse control points early in sim (extrapolation risk)
- Logs with gaps in revealed window

## Acceptance tests
### Test E1: Deterministic stepping
Given same project state
When running step forward N times
Then revealed_md_ft and KPI values match expected deterministic values

### Test E2: Interpretation version creation
Given a control point update at step k
When saving
Then a new interpretation version exists with derived_from pointing to prior version
And rationale is non-empty

### Test E3: Decision entry links
Given a decision recorded at step k
Then decision_entry.interpretation_version_id references an existing version

### Test E4: KPI correctness on synthetic dataset
Given a synthetic dataset with known top/base and a wellbore path
When computing percent_in_zone
Then result matches analytic expected value within tolerance

## Definition of Done
- A full simulated steer can be performed end-to-end
- Interpretation versions and decision logs persist and are reproducible
- KPIs update per step and are validated by tests
