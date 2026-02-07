# Milestone 3: Correlation panel + marker CRUD

**Primary purpose**: implement the core geosteering skill showcase: multiwell correlation and marker picking.

**Spec refs**: `05_epic_c_multiwell_correlation_panel.md`, `03_epic_a_project_and_data_loading.md` (markers), `11_ui_screens_and_interactions.md`.

---

## Issue: M3-MODEL-200 MarkerSet persistence and CRUD API

**Spec refs**: `05` (marker schema), `09` (persistence), `15` (auditability)

**Depends on**: `M1-IO-030`, `M1-MODEL-020`

**Goal**: stable marker CRUD for correlation workflows.

**Subtasks**
- [x] Implement marker store per well:
  - load/save `wells/<id>/markers.json`
- [x] Implement CRUD operations:
  - add, edit (depth, name, notes), delete
- [x] Enforce deterministic ordering:
  - always sort by `md_ft` before save
- [x] Track `created_at`/`updated_at` fields (optional but recommended)

**Deliverables**
- `app/services/markers.py`

**Acceptance checks**
- [x] Implements Test C1 (persistence round-trip)

---

## Issue: M3-PLOT-210 Correlation panel plotting

**Spec refs**: `05` (plot constraints), `11` (correlation screen), `15` (performance)

**Depends on**: `M2-PLOT-110`

**Goal**: multiwell aligned view of logs with marker overlays.

**Subtasks**
- [x] Implement multiwell layout:
  - wells in columns or stacked with alignment cues
- [x] Shared depth axis / window controls
- [x] Marker overlays and labels per well
- [x] Optional P1: display-only alignment shifts per well

**Deliverables**
- `app/plot/correlation_panel.py`

**Acceptance checks**
- [x] Supports minimum 3 wells display (Test C3)

---

## Issue: M3-UI-220 Correlation Panel page

**Spec refs**: `05` (P0 requirements), `11` (screen definition)

**Depends on**: `M3-MODEL-200`, `M3-PLOT-210`, `M2-UI-100`

**Goal**: usable correlation panel with marker CRUD.

**Subtasks**
- [x] Well multi-select (offset wells)
- [x] Curve selection (GR + RES)
- [x] Marker add form (name, md_ft, notes)
- [x] Marker edit and delete controls (table-based)
- [x] Jump-to-marker control (sets displayed window)
- [x] Persist markers immediately or via explicit save button (choose one; default immediate)

**Deliverables**
- `app/pages/correlation_panel.py`

**Acceptance checks**
- [x] C1: marker persistence across restart
- [x] C3: multiwell display works for 3 offsets

---

## Issue: M3-TEST-230 Correlation panel persistence and behavior tests

**Spec refs**: `05` tests C1–C3

**Depends on**: `M3-MODEL-200`, `M3-PLOT-210`

**Goal**: enforce marker stability and avoid silent regressions.

**Subtasks**
- [x] Test marker CRUD and persisted file content
- [x] If alignment shift P1 implemented:
  - test it is display-only by default (stored marker md unchanged)

**Deliverables**
- `tests/test_markers_round_trip.py`
- `tests/test_correlation_panel_behavior.py` (optional)

**Acceptance checks**
- [x] Milestone 3 gate in `12` satisfied
