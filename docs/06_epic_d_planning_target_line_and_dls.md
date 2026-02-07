# Title
Epic D: Planning Module (Target Line + DLS Constraints)

## Objective
Implement a planning interface that allows a user to define a target line and generate a planned trajectory with DLS checks.

The goal is to show you understand:
- Planning constraints (DLS)
- Waypointed target lines
- Exportable deliverables

## Functional requirements
### P0
- Create a plan for the active well:
  - Inputs:
    - kickoff MD (ft)
    - landing MD (ft) or landing TVD (ft)
    - lateral length (ft)
    - planned azimuth (deg)
    - target window thickness (ft) or explicit top/base
    - max DLS (deg/100ft)
  - Generate a plan trajectory (survey stations) at fixed step (default 100 ft):
    - MD, inc, azi, TVD, north, east
  - Compute DLS between consecutive stations
  - Display warnings when DLS exceeds max
  - Export plan as CSV

### P1
- Support waypoint editing:
  - user adds intermediate waypoints (MD, inc or TVD targets)
- Visualize plan vs actual (if actual exists)

### P2
- Suggest plan modifications to reduce DLS (optional)

## Planning math assumptions (MVP)
- Use minimum curvature to compute XYZ and TVD from survey stations.
- Plan generation approach (simple):
  - Build section: inc increases linearly from 0 to 90 deg between kickoff and landing
  - Hold section: inc remains near 90 deg for lateral
  - Azi constant for all stations
This is not a fully realistic directional planning engine, but it is sufficient to:
- produce a credible-looking plan
- compute DLS and show constraint effects

## DLS computation
- Compute dogleg angle between stations using standard directional drilling formulas.
- DLS = (dogleg_deg / delta_md_ft) * 100

The algorithm is specified in `docs/10_core_computations_and_algorithms.md`.

## UI requirements
- Form inputs with validation and default values
- Live preview plot:
  - MD vs TVD (plan)
  - DLS vs MD with threshold line
- Export button produces plan CSV in project folder

## Acceptance tests
### Test D1: Plan generation station count
Given kickoff=1000, landing=3000, lateral=5000, step=100
When generating plan
Then number of stations equals expected based on MD range

### Test D2: DLS threshold warning
Given an unrealistically short build section and max DLS=3 deg/100ft
When generating plan
Then warnings list at least one interval exceeding DLS

### Test D3: Export format
When exporting plan
Then CSV includes required columns: md_ft, inc_deg, azi_deg, tvd_ft, north_ft, east_ft, dls_deg_per_100ft

## Definition of Done
- User can produce a plan and export it
- DLS feedback is clear and correct
- Plan plots are usable in report export
