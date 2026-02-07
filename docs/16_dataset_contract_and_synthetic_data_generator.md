# Title
Dataset Contract and Synthetic Data Generator

## Objective
Define a deterministic dataset contract so:
- AI agents can implement import pipelines reliably
- The demo can run without external datasets
- Unit tests can be built against known truth

## Dataset contract (required for demo)
Directory structure:
data/
  sample_project/
    wells/
      offset_01/
        survey.csv
        logs.las
        markers.csv (optional)
      offset_02/
        survey.csv
        logs.las
      offset_03/
        survey.csv
        logs.las
      active_01/
        survey.csv
        logs.las

## Survey CSV schema
Columns:
- md_ft, inc_deg, azi_deg

Constraints:
- md_ft strictly increasing
- inc_deg and azi_deg valid ranges

## Logs LAS requirements
Must include:
- GR
- One resistivity curve (RT or equivalent)
Optional:
- RHOB, NPHI, DT

Depth basis:
- Must be MD in feet for sample dataset (avoid unit conversion complexity in demo data)

## Synthetic data generator
### Purpose
Generate a clean demo dataset with:
- A known target zone top/base defined as functions of MD
- Logs that vary with zone membership
- A trajectory that sometimes drifts out of zone so steering decisions matter

### Generator inputs
- number_of_offsets (default 3)
- active_well_length_ft (default 8000)
- sampling_step_ft (default 0.5)
- zone_thickness_ft (default 20)
- structure_trend_ft_per_1000ft (default 5)
- noise_level (default)
- random_seed (fixed default)

### Truth model
Define:
- top_tvd(md) = base_top + trend*md + sinusoidal wiggle
- base_tvd(md) = top_tvd(md) + thickness
Define wellbore TVD:
- planned near zone center but includes drift events.

Generate GR:
- lower GR in zone, higher GR out of zone, plus noise
Generate RES:
- higher RES in zone, lower RES out of zone, plus noise

Offsets:
- Apply small structural shifts and noise so correlation is non-trivial.

### Outputs
- survey.csv: MD/inc/azi representing a plausible lateral (simplified)
- logs.las: GR and RES curves as functions of MD
- markers.csv: optional markers at key MDs (for offsets only or for all)

### Determinism
- All randomness uses a fixed seed
- The generator saves a `truth.json` containing:
  - top/base truth control points
  - drift events
  - expected in-zone percent under baseline plan

### Unit test utility
- Use truth.json to assert KPI and interpretation evaluation correctness.

## Acceptance tests
- Generator produces valid files matching schema
- Import pipeline loads generated dataset without warnings
- KPI computed on baseline interpretation matches expected truth within tolerance

## Definition of Done
- A `python -m tools.generate_sample_data` command creates the dataset
- Repo includes generated sample dataset or can generate it during setup
