# Title
Epic A: Project and Data Loading

## Objective
Implement a reliable, explicit, and testable pipeline to create/open a project and load:
- Well surveys (CSV)
- Well logs (LAS)
- Optional markers (CSV)
Persist everything to disk in a deterministic project structure.

## Functional requirements
### P0
- Create new project (name, root folder)
- Open existing project (load state from disk)
- Import well:
  - Import survey CSV and compute trajectory
  - Import LAS logs and normalize curve names/units
  - Produce a QC summary and allow user to confirm the well is "valid"
- Support at least 4 wells in a project

### P1
- Import markers CSV for a well
- Rename wells and curve aliases (for display)

### P2
- Batch import via folder structure

## Inputs and formats
### Survey CSV (required)
Filename: `survey.csv`
Required columns:
- `md_ft` (float)
- `inc_deg` (float)
- `azi_deg` (float)

Optional columns (if present should be used or validated):
- `tvd_ft` (float)
- `north_ft` (float)
- `east_ft` (float)

Rules:
- `md_ft` strictly increasing
- `inc_deg` in [0, 180]
- `azi_deg` in [0, 360)

### Logs LAS (required)
Filename: `logs.las`
At minimum require one curve:
- `GR` (Gamma Ray) in API units or equivalent
Plus one resistivity curve:
- `RT` or `RES` or similar

Rules:
- Depth basis is MD in feet (MVP assumption). If LAS uses meters, convert.
- Curves must be resampled to a canonical step for plotting, but preserve original sampling.

### Markers CSV (optional)
Filename: `markers.csv`
Columns:
- `marker_name` (string)
- `md_ft` (float) or `tvd_ft` (float, choose one basis for MVP; recommend md_ft)
- `color` (optional)
- `notes` (optional)

## Data QC
### P0 checks
- Survey monotonic MD
- No NaNs in required columns
- Curve presence check for required curves
- Depth overlap between survey and logs:
  - log depth range must intersect survey MD range by at least X (configurable, default 80%)

QC outputs:
- A QC table listing:
  - well name
  - min/max MD
  - count of survey stations
  - curves present
  - sampling step (estimated)
  - warnings

## Persistence and project structure
See `docs/09_data_model_and_persistence.md` for exact layout.
Epic A must implement:
- `project.json` (metadata)
- `wells/<well_id>/survey.parquet`
- `wells/<well_id>/trajectory.parquet` (computed)
- `wells/<well_id>/logs.parquet` (normalized)
- `wells/<well_id>/markers.json` (if present)

## Implementation notes (agent guidance)
- Use `lasio` for LAS parsing.
- Normalize curve mnemonics:
  - Map common aliases to canonical names: GR, RES, RHOB, NPHI, DT (optional)
- Convert units:
  - depth to feet if needed
  - angles remain degrees
- Store raw and normalized curve names for traceability.

## Edge cases
- LAS with nonstandard depth mnemonic (DEPT vs DEPTH)
- Multiple log runs or spliced sections
- Duplicate MD rows in survey
- Negative or nonsensical curve values

## Acceptance tests
### Test A1: Survey parsing
Given a valid survey CSV
When imported
Then trajectory stations count equals input row count
And MD is strictly increasing

### Test A2: LAS parsing and curve detection
Given a LAS containing GR and RT
When imported
Then canonical curves include GR and RES (normalized name)
And depth units are converted to feet if needed

### Test A3: QC overlap check
Given logs whose depth range does not overlap survey
When importing
Then the well is marked invalid and a clear error is produced

### Test A4: Persistence round-trip
Given a project with one imported well
When the project is saved and reopened
Then the well loads without recomputation differences
And QC summary remains unchanged

## Definition of Done
- Import workflow works for sample dataset contract
- QC outputs are visible in UI
- Persistence works across restarts
- Unit tests for parsing and QC exist
