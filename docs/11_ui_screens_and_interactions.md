# Title
UI Screens and Interactions

## Objective
Specify the MVP UI structure so an AI agent can implement screens in Streamlit with clear state boundaries.

## Navigation model
Use a left sidebar with page selection:
- Dashboard
- Data QC
- Well Viewer
- Correlation Panel
- Planning
- Steering Console
- Report Export

## Global UI rules
- Always show current project name and root path
- Always show active well selection status
- Any destructive operation requires confirmation
- Any model update must capture a rationale (free text)

## Screen 1: Dashboard
Purpose:
- Project open/create
- High-level status and shortcuts

Components:
- Create project form
- Open project selector
- Wells summary table:
  - well name
  - survey loaded (yes/no)
  - curves present
  - markers count
- Buttons:
  - Go to Data QC
  - Go to Correlation Panel
  - Go to Planning
  - Go to Steering Console

## Screen 2: Data QC
Purpose:
- Verify each well import is valid

Components:
- QC table with warnings
- Per-well QC detail: depth ranges, curves, sampling
- Actions:
  - mark well as offset
  - mark well as active candidate

## Screen 3: Well Viewer
Purpose:
- Inspect logs and trajectory for a selected well

Components:
- Well selector dropdown
- Track template selector (default GR + RES)
- Plot:
  - log tracks with shared depth axis
  - marker overlay
  - optional bit position indicator (if simulation running)
- Trajectory plot:
  - MD vs TVD

## Screen 4: Correlation Panel
Purpose:
- Side-by-side comparison and marker picking across wells

Components:
- Well multi-select (offset wells)
- Curve selection (GR, RES)
- Plot grid (wells in columns)
- Marker list table with edit controls
- Marker add form:
  - name
  - md_ft
  - notes
- Optional alignment shift controls per well (P1)

## Screen 5: Planning
Purpose:
- Create and visualize a plan with DLS constraints

Components:
- Plan parameter form:
  - kickoff_md_ft
  - landing_md_ft
  - lateral_length_ft
  - planned_azi_deg
  - step_ft
  - max_dls_deg_per_100ft
- Outputs:
  - plan trajectory plot (MD vs TVD)
  - DLS plot vs MD with threshold
  - exceedance table
- Actions:
  - Save plan
  - Export plan CSV

## Screen 6: Steering Console
Purpose:
- Run simulated real-time steering

Components:
- Simulation config (active well, offsets, step size)
- Current step display (step index, revealed MD)
- Step controls:
  - Step forward
  - Step back (optional)
- Views:
  - Active well logs in current window (depth range around bit)
  - Offset comparison view (mini-correlation window)
  - Interpretation display (control points table and plotted top/base curves)
- Interpretation update controls:
  - add control point at current md (top/base tvd)
  - rationale text (required)
  - create new version
- Decision logging form:
  - observations
  - recommendation action (hold/build/drop)
  - optional target inc/azi
  - risk note
- KPI panel:
  - percent in zone
  - avg distance to center
  - sparkline over steps (optional)

## Screen 7: Report Export
Purpose:
- Produce portfolio-ready report

Components:
- Report configuration:
  - include which wells
  - include which steps snapshots
- Preview of included sections (headers only)
- Export button
- Link to generated PDF

## Definition of Done
- All screens exist and work with the sample dataset
- State flows correctly between screens (project state single source of truth)
- No screen recomputes heavy data unnecessarily
