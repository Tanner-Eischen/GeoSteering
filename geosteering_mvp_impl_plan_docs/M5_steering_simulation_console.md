# Milestone 5: Steering simulation console

**Primary purpose**: demonstrate core geosteering operations: stepwise “real-time” reveal, interpretation updates, decision logging, and in-zone KPIs.

**Spec refs**: `07_epic_e_steering_simulation_console.md`, `10_core_computations_and_algorithms.md`, `11_ui_screens_and_interactions.md`, `14_templates_and_standard_outputs.md`, `15_risks_failure_modes_and_mitigations.md`, `16_dataset_contract_and_synthetic_data_generator.md`.

---

## Issue: M5-SIM-400 Simulation config/state + persistence

**Spec refs**: `07` (simulation_config/state), `09` (simulations folder), `15` (determinism)

**Depends on**: `M1-IO-030`

**Goal**: deterministic simulation stepping with persisted state.

**Subtasks**
- [x] Define `SimulationConfig`:
  - active well id, offsets list, curves used, step size, window size
- [x] Define `SimulationState`:
  - step_index, revealed_md_ft, version_id_by_step (optional), decision_id_by_step (optional)
- [x] Save/load to:
  - `simulations/simulation_config.json`
  - `simulations/simulation_state.json`
- [x] Implement pure step function:
  - `step_forward(state, config, project) -> new_state`
- [x] Define stop condition (TD reached)

**Deliverables**
- `app/sim/sim_models.py`, `app/sim/sim_store.py`, `app/sim/engine.py`

**Acceptance checks**
- [x] E1 groundwork: stepping produces identical `revealed_md_ft` given same inputs

---

## Issue: M5-ALG-410 Interpretation evaluation model (piecewise linear)

**Spec refs**: `07` (interpretation model), `10` (interpretation evaluation)

**Depends on**: `M1-MODEL-020`

**Goal**: represent top/base as piecewise linear functions of MD and evaluate deterministically.

**Subtasks**
- [x] Implement piecewise linear evaluator over MD grid
- [x] Choose extrapolation policy (recommend hold-constant) and document in code + UI assumptions
- [x] Validation:
  - detect base above top
  - detect insufficient control points (warn)
- [x] Helper to add/update control points with stable sorting

**Deliverables**
- `app/alg/interpretation_model.py`

**Acceptance checks**
- [x] Unit tests for interpolation midpoint and boundary behavior pass

---

## Issue: M5-MODEL-420 Interpretation versioning service (immutable)

**Spec refs**: `07` (versioning + rationale), `09` (append-only persistence), `15` (auditability)

**Depends on**: `M5-ALG-410`, `M1-IO-030`

**Goal**: manage interpretation versions with explicit rationale and provenance.

**Subtasks**
- [x] Create baseline interpretation version (v0) for the project
- [x] Create new versions derived from previous:
  - require non-empty rationale
  - record step index
- [x] Persist append-only in `interpretations/interpretations.json`
- [x] Query helpers: get latest version, get by id

**Deliverables**
- `app/services/interpretations.py`

**Acceptance checks**
- [x] E2: new version has `derived_from_version_id` set and rationale non-empty

---

## Issue: M5-MODEL-430 Decision log service (append-only + CSV export)

**Spec refs**: `07` (decision log), `14` (decision CSV template), `09` (decisions persistence)

**Depends on**: `M1-IO-030`

**Goal**: record step decisions with traceability to interpretation version.

**Subtasks**
- [x] Append-only decision creation with:
  - step_index, md interval, interpretation_version_id, observations, recommendation, risk_note
- [x] Persist decisions in `decisions/decisions.json`
- [x] Implement export to `exports/decision_log.csv` using template in `14`

**Deliverables**
- `app/services/decisions.py`

**Acceptance checks**
- [x] E3: decision references an existing interpretation version id

---

## Issue: M5-ALG-440 KPI computation (in-zone and distance metrics)

**Spec refs**: `07` (KPI definition), `10` (KPI algorithm), `16` (truth.json for tests)

**Depends on**: `M1-ALG-040`, `M5-ALG-410`

**Goal**: compute percent-in-zone and distance-to-center metrics over revealed interval.

**Subtasks**
- [x] Choose evaluation MD grid and document it (must be deterministic)
- [x] Compute well TVD from trajectory interpolation at MD grid
- [x] Evaluate top/base at MD grid
- [x] Compute:
  - percent_in_zone
  - avg_center_distance
  - last-step KPIs (optional)
- [x] Handle edge cases:
  - invalid top/base ordering
  - missing trajectory interpolation (should not happen with valid data)

**Deliverables**
- `app/alg/kpi.py`

**Acceptance checks**
- [x] E4: KPI matches synthetic truth baseline within tolerance

---

## Issue: M5-PLOT-450 Steering console plots (active window, offsets, overlay, KPI)

**Spec refs**: `07` (views), `11` (steering screen), `14` (plot templates)

**Depends on**: `M2-PLOT-110`, `M3-PLOT-210`, `M5-ALG-440`, `M5-ALG-410`

**Goal**: provide the visuals that make the steering workflow understandable and demo-friendly.

**Subtasks**
- [x] Active well window plot:
  - show only revealed data
  - bit position line
- [x] Offset comparison mini-panel for the same window
- [x] Interpretation overlay plot:
  - well TVD vs MD and top/base vs MD
- [x] KPI trend plot over steps (optional but high value)

**Deliverables**
- `app/plot/steering.py`

**Acceptance checks**
- [x] Plots update correctly on step forward and after interpretation updates

---

## Issue: M5-UI-460 Steering Console page

**Spec refs**: `07` (P0 UI), `11` (screen), `15` (determinism and safety)

**Depends on**: `M5-SIM-400`, `M5-MODEL-420`, `M5-MODEL-430`, `M5-ALG-440`, `M5-PLOT-450`

**Goal**: deliver the core interactive module proving you can steer and document decisions.

**Subtasks**
- [x] Simulation configuration UI:
  - active well, offsets, curves, step size
- [x] Step controls (forward; backward optional P1 only if stable)
- [x] Interpretation update UI:
  - add control point at current MD (top/base TVD)
  - rationale required
  - create new version
- [x] Decision entry UI:
  - observations, action hold/build/drop, optional target inc/azi, risk note
- [x] KPI panel (current + history)
- [x] Persist after each action

**Deliverables**
- `app/pages/steering_console.py`

**Acceptance checks**
- [x] Can complete a 10-step simulated run with saved decisions and versions (Milestone 5 gate)

---

## Issue: M5-TEST-470 Simulation + interpretation + KPI tests

**Spec refs**: `07` tests E1–E4, `10` (math), `16` (truth.json)

**Depends on**: all M5 issues

**Goal**: make the steering workflow deterministic and verifiable.

**Subtasks**
- [x] E1 deterministic stepping test (save/reload + step forward yields same state)
- [x] E2 version creation test (provenance + rationale)
- [x] E3 decision links version test
- [x] E4 KPI test against synthetic truth

**Deliverables**
- `tests/test_simulation.py`

**Acceptance checks**
- [x] Milestone 5 gate in `12` satisfied
