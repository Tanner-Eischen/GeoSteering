# Milestone 1: Data ingestion + persistence baseline

**Primary purpose**: establish deterministic project persistence, synthetic demo data, and a reliable ingest pipeline with QC and tests.

**Spec refs**: `03_epic_a_project_and_data_loading.md`, `09_data_model_and_persistence.md`, `10_core_computations_and_algorithms.md`, `16_dataset_contract_and_synthetic_data_generator.md`, plus global constraints in `00/01/15`.

---

## Issue: M1-REPO-001 Repository scaffold and tooling

**Spec refs**: `12` (milestones), `00` (Definition of Done)

**Depends on**: none

**Goal**: create a buildable, testable repo structure with repeatable local execution.

**Subtasks**
- [x] Create package layout: `app/`, `app/pages/`, `tools/`, `tests/`, `data/`, `exports/` (gitignored)
- [x] Add `pyproject.toml` with baseline dependencies:
  - runtime: streamlit, plotly, pandas, numpy, pydantic, pyarrow, lasio
  - test: pytest
  - report: reportlab (recommended) and plot export support (kaleido)
- [x] Add `pytest.ini` and smoke test runner command
- [x] Add style tooling (optional P1): ruff, mypy

**Deliverables**
- Repo layout + dependency installation instructions

**Acceptance checks**
- [x] `python -c "import app"` succeeds
- [x] `pytest` runs (0 tests is acceptable initially)

---

## Issue: M1-DATA-010 Synthetic dataset generator (demo-first)

**Spec refs**: `16` (contract + generator), `15` (risk mitigation: public data quirks), `10` (KPI truth utility)

**Depends on**: `M1-REPO-001`

**Goal**: produce deterministic sample data and `truth.json` to stabilize demos and unit tests.

**Subtasks**
- [x] Implement `tools/generate_sample_data.py` CLI:
  - `python -m tools.generate_sample_data --out data/sample_project --seed 123`
- [x] Generate directory structure per contract:
  - `data/sample_project/wells/{offset_01,offset_02,offset_03,active_01}/...`
- [x] Generate `survey.csv` (md_ft, inc_deg, azi_deg) for each well
- [x] Generate `logs.las` with at least GR and RES curves on MD in feet
- [x] Optionally generate `markers.csv` for offsets to support correlation demo
- [x] Write `truth.json` containing top/base truth model + drift events + expected baseline KPIs
- [x] Enforce determinism (fixed seed, stable ordering)

**Deliverables**
- Synthetic dataset generator + output folder

**Acceptance checks**
- [x] Generated dataset matches `16` contract
- [x] Same seed yields identical `truth.json` contents and stable file checksums (allowing only LAS header timestamp variance if present)

---

## Issue: M1-MODEL-020 Implement core Pydantic schemas

**Spec refs**: `09` (schemas), `14` (outputs), `07` (decision and interpretation needs)

**Depends on**: `M1-REPO-001`

**Goal**: implement validated, serializable domain models for project state.

**Subtasks**
- [x] Create `app/model/` modules:
  - Project, Well, CurveMeta, Marker, InterpretationVersion, ControlPoint, UncertaintyModel, DecisionEntry, Recommendation, Plan, DLSExceedance
- [x] Enforce ID and ordering rules from `09`:
  - UUID4 IDs
  - sorted control points by MD
  - append-only decisions and interpretations
- [x] Implement validation hooks:
  - required fields non-empty (rationale for interpretation updates)
  - range checks where applicable

**Deliverables**
- Pydantic schemas usable by IO layer

**Acceptance checks**
- [x] `Project.model_validate(...)` works on minimal objects
- [x] Invalid schema raises clear validation errors

---

## Issue: M1-IO-030 Project filesystem layout + load/save

**Spec refs**: `09` (canonical layout), `03` (persistence requirements), `15` (determinism)

**Depends on**: `M1-MODEL-020`

**Goal**: implement deterministic persistence and round-trip load/save.

**Subtasks**
- [x] Implement `create_project(root, name)`
- [x] Implement `load_project(root)` and `save_project(project, root)`
- [x] Implement path helpers for canonical layout (folders/files per `09`)
- [x] Deterministic JSON writes:
  - stable ordering of lists
  - sorted keys
  - atomic write (temp file then rename)
- [x] Enforce no silent overwrite for append-only collections

**Deliverables**
- `app/io/project_store.py` and helpers

**Acceptance checks**
- [x] Create → save → load yields equivalent project object (excluding explicitly allowed timestamp differences)

---

## Issue: M1-ALG-040 Minimum curvature trajectory + DLS

**Spec refs**: `10` (trajectory + DLS), `06` (planning depends), `03` (trajectory persistence)

**Depends on**: `M1-REPO-001`

**Goal**: compute trajectory (TVD/N/E) and DLS from survey stations.

**Subtasks**
- [x] Implement `compute_trajectory(df)` using minimum curvature method
- [x] Clamp numeric extremes for stability
- [x] Compute dogleg and DLS deg/100ft per segment
- [x] Implement interpolation helper `interp_trajectory(md_query)`

**Deliverables**
- `app/alg/trajectory_min_curve.py`, `app/alg/trajectory_interp.py`

**Acceptance checks**
- [x] Unit tests from `10` pass:
  - vertical well: TVD equals MD, N/E approx 0
  - constant inc/azi: dogleg 0 and expected N/E increments

---

## Issue: M1-IO-050 Survey CSV import + validation

**Spec refs**: `03` (survey schema + Test A1), `10` (trajectory inputs)

**Depends on**: `M1-ALG-040`, `M1-IO-030`

**Goal**: read and validate survey CSV and persist survey + computed trajectory.

**Subtasks**
- [x] Implement `read_survey_csv(path)` with required columns (md_ft, inc_deg, azi_deg)
- [x] Validate monotonic MD and angle ranges
- [x] Compute trajectory and persist:
  - `survey.parquet`
  - `trajectory.parquet`

**Deliverables**
- `app/io/survey_import.py`

**Acceptance checks**
- [x] Implements Test A1 from `03`

---

## Issue: M1-IO-060 LAS import + curve normalization + unit conversion

**Spec refs**: `03` (LAS requirements + Test A2), `15` (edge cases), `10` (resampling later)

**Depends on**: `M1-IO-030`, `M1-MODEL-020`

**Goal**: parse LAS and store normalized curve table with canonical names (GR, RES).

**Subtasks**
- [x] Parse LAS depth basis and curves using `lasio`
- [x] Convert depth units to feet (if needed)
- [x] Normalize curve mnemonics to canonical names:
  - GR, RES (map RT/ILD/etc to RES)
- [x] Persist `logs.parquet` with column `md_ft` + curve columns
- [x] Persist `curve_inventory` metadata in `well.json`

**Deliverables**
- `app/io/las_import.py`, `app/io/curve_normalize.py`

**Acceptance checks**
- [x] Implements Test A2 from `03`

---

## Issue: M1-QC-070 QC summary (overlap, curve presence, sampling)

**Spec refs**: `03` (QC checks + Test A3), `15` (risk: depth confusion)

**Depends on**: `M1-IO-050`, `M1-IO-060`

**Goal**: produce a QC summary and machine-readable warnings per well.

**Subtasks**
- [x] Implement overlap check: logs MD range intersects survey MD range by >= threshold
- [x] Implement required curve presence check (GR + RES)
- [x] Estimate sampling step per curve
- [x] Persist QC status and warnings in well metadata

**Deliverables**
- `app/qc/qc_checks.py`, `app/qc/qc_models.py`

**Acceptance checks**
- [x] Implements Test A3 from `03`

---

## Issue: M1-IO-080 CLI tool: import well

**Spec refs**: `03` (import flow), `12` (deliverables), `16` (dataset contract)

**Depends on**: `M1-IO-050`, `M1-IO-060`, `M1-QC-070`

**Goal**: one command to import a well folder into a project with QC and persistence.

**Subtasks**
- [x] Implement `tools/import_well.py`:
  - inputs: project root, well folder path, well name
  - outputs: well added to project state and persisted under `wells/<well_id>/`
- [x] Error handling includes file path and reason
- [x] Logging to console

**Deliverables**
- Import CLI tool

**Acceptance checks**
- [x] Imports the synthetic wells from `data/sample_project`

---

## Issue: M1-TEST-090 Ingestion + persistence unit tests

**Spec refs**: `03` tests A1–A4, `09` persistence rules, `10` trajectory tests

**Depends on**: all above M1 issues

**Goal**: enforce correctness gates for the foundation.

**Subtasks**
- [x] Test A1: survey import validation and trajectory row counts
- [x] Test A2: LAS import includes canonical curves GR + RES
- [x] Test A3: QC overlap failure case (no overlap) raises/flags invalid
- [x] Test A4: persistence round-trip yields identical state

**Deliverables**
- `tests/` suite for Milestone 1

**Acceptance checks**
- [x] Milestone 1 gate in `12` satisfied
