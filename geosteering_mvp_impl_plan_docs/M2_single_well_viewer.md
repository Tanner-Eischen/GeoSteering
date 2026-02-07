# Milestone 2: Single well viewer

**Primary purpose**: implement the Well Viewer screen used for inspection and later report snapshots.

**Spec refs**: `04_epic_b_single_well_viewer.md`, `11_ui_screens_and_interactions.md`.

---

## Issue: M2-UI-100 Streamlit app shell + navigation

**Spec refs**: `11` (navigation model), `15` (determinism risk), `00` (disclaimer visibility)

**Depends on**: `M1-IO-030`

**Goal**: establish app navigation and global project context.

**Subtasks**
- [x] Sidebar navigation pages:
  - Dashboard, Data QC, Well Viewer, Correlation Panel, Planning, Steering Console, Report Export
- [x] Project open/create UI:
  - store selected project root path in session state
- [x] Global header showing project name/root and active well status
- [x] Add non-operational disclaimer in sidebar or header (must be visible)

**Deliverables**
- `streamlit_app.py` (or equivalent entrypoint), `app/pages/*.py`

**Acceptance checks**
- [x] Can open a project and navigate pages without losing loaded project

---

## Issue: M2-PLOT-110 Log track plotting utilities (Plotly)

**Spec refs**: `04` (plot requirements), `10` (resampling constraints), `15` (performance risk)

**Depends on**: `M1-IO-060`

**Goal**: implement reusable log plotting with aligned depth axis and resistivity log scale support.

**Subtasks**
- [x] Implement GR track and RES track with shared depth axis
- [x] Resistivity log scale:
  - clip nonpositive values to NaN in display layer only
  - return metadata for clipped count
- [x] Implement decimation/resampling for display performance
- [x] Provide ability to render a window (min/max depth) and full depth

**Deliverables**
- `app/plot/log_tracks.py`

**Acceptance checks**
- [x] Renders GR + RES for `active_01` synthetic well

---

## Issue: M2-UI-120 Well Viewer page

**Spec refs**: `04` (P0 requirements B1–B3), `11` (screen definition)

**Depends on**: `M2-UI-100`, `M2-PLOT-110`, `M1-IO-050`

**Goal**: implement single-well inspection UI including trajectory view and marker overlay.

**Subtasks**
- [x] Well selector
- [x] Curve selection (default GR + RES)
- [x] Render aligned tracks
- [x] Overlay markers (if available)
- [x] Render trajectory plot (MD vs TVD)
- [x] Bit position indicator hook:
  - if simulation state exists, draw line at `revealed_md_ft`

**Deliverables**
- `app/pages/well_viewer.py`

**Acceptance checks**
- [x] B1: baseline tracks render
- [x] B2: markers show when present
- [x] B3: bit indicator shows when simulation state exists (can be mocked)

---

## Issue: M2-TEST-130 Plot smoke tests

**Spec refs**: `04` (graceful handling), `15` (avoid runtime crashes)

**Depends on**: `M2-PLOT-110`

**Goal**: ensure plot functions do not crash on common edge cases.

**Subtasks**
- [x] Test missing curve behavior (e.g., no RES) degrades gracefully
- [x] Test marker out-of-range does not crash
- [x] Test window rendering with small and large ranges

**Deliverables**
- `tests/test_plots_smoke.py`

**Acceptance checks**
- [x] Tests pass and prevent credibility-killing UI failures
