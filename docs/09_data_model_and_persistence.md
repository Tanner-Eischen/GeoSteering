# Title
Data Model and Persistence Specification

## Objective
Define a minimal but credible project data model that supports:
- Multiple wells
- Logs and trajectories
- Marker sets
- Interpretation version history
- Decision logs
- Plans and exports
With deterministic persistence to disk.

## Tech constraints
- Python app
- Pydantic models for schema validation
- Parquet for large numeric arrays
- JSON for small structured state

## Canonical project layout
<project_root>/
  project.json
  wells/
    <well_id>/
      well.json
      survey.parquet
      trajectory.parquet
      logs.parquet
      markers.json
  interpretations/
    interpretations.json
  plans/
    <plan_id>.json
    <plan_id>_stations.parquet
  simulations/
    simulation_config.json
    simulation_state.json
  decisions/
    decisions.json
  exports/
    report_<project_name>.pdf
  cache/
    (optional)

## Entity schemas (Pydantic outlines)
### Project
- project_id: uuid
- name: str
- created_at: datetime (optional)
- wells: List[WellRef]
- active_well_id: Optional[str]
- created_by: Optional[str]
- settings:
  - depth_basis: "MD_FT" (MVP fixed)
  - vertical_reference: "TVD_FT" (MVP fixed)
  - required_curves: ["GR", "RES"]

### WellRef
- well_id: str
- name: str

### Well
- well_id: str
- name: str
- metadata:
  - field: Optional[str]
  - api: Optional[str]
- survey_path: str
- trajectory_path: str
- logs_path: str
- markers_path: Optional[str]
- curve_inventory: Dict[str, CurveMeta]

### CurveMeta
- canonical_name: str  # GR, RES, etc
- original_mnemonics: List[str]
- unit: str
- sample_step_ft_est: float
- depth_min_ft: float
- depth_max_ft: float

### Marker
- marker_id: uuid
- name: str
- md_ft: float
- notes: Optional[str]
- created_at: datetime
- updated_at: datetime

### InterpretationVersion
- version_id: uuid
- derived_from_version_id: Optional[uuid]
- created_at: datetime
- step_index: Optional[int]
- rationale: str
- top_control_points: List[ControlPoint]
- base_control_points: List[ControlPoint]
- uncertainty: UncertaintyModel

### ControlPoint
- md_ft: float
- tvd_ft: float

### UncertaintyModel (MVP)
Option A: constant band
- band_tvd_ft: float

Option B: piecewise band
- bands: List[UncertaintyBand]
Where UncertaintyBand:
- md_from_ft: float
- md_to_ft: float
- band_tvd_ft: float

### DecisionEntry
- decision_id: uuid
- step_index: int
- md_from_ft: float
- md_to_ft: float
- interpretation_version_id: uuid
- observations: str
- recommendation: Recommendation
- risk_note: Optional[str]
- created_at: datetime

### Recommendation
- action: "HOLD" | "BUILD" | "DROP"
- target_inc_deg: Optional[float]
- target_azi_deg: Optional[float]
- notes: Optional[str]

### Plan
- plan_id: uuid
- name: str
- created_at: datetime
- parameters: PlanParameters
- stations_path: str
- dls_max_deg_per_100ft: float
- dls_exceedances: List[DLSExceedance]

### PlanParameters
- kickoff_md_ft: float
- landing_md_ft: float
- lateral_length_ft: float
- planned_azi_deg: float
- build_rate_hint_deg_per_100ft: Optional[float]
- step_ft: float

### DLSExceedance
- md_from_ft: float
- md_to_ft: float
- dls_deg_per_100ft: float

## Persistence rules
- All IDs are UUID4 strings.
- All lists that represent ordered data must be stored in sorted order:
  - survey rows by md_ft
  - control points by md_ft
  - decision entries by (step_index, created_at)
- No silent overwrites:
  - decisions append only
  - interpretations append only
- Any modification creates a new versioned entity or a new file.

## Acceptance tests
- Model validation: invalid schema raises clear errors
- Round-trip: load saved project equals original in content (excluding allowed timestamp differences)
