# Title
Core Computations and Algorithms

## Objective
Specify the minimal set of computations required for credibility and correctness:
- Minimum curvature trajectory computation
- Dogleg severity (DLS)
- Depth interpolation and curve resampling
- Interpretation model evaluation along MD
- In-zone KPIs

All critical math must have tests.

## 1) Minimum curvature trajectory
### Inputs
Survey stations (MD, inc, azi) in:
- md_ft
- inc_deg
- azi_deg

### Outputs (per station)
- tvd_ft
- north_ft
- east_ft
- dogleg_deg (between previous and current)
- dls_deg_per_100ft

### Algorithm (standard)
For each segment i from station i-1 to i:
- Convert angles to radians:
  - inc1, inc2, azi1, azi2
- Compute dogleg angle:
  cos_dogleg = cos(inc2-inc1) - (sin(inc1)*sin(inc2))*(1 - cos(azi2-azi1))
  dogleg = arccos(clamp(cos_dogleg, -1, 1))

Note: alternative equivalent formulations are acceptable if numerically stable.

- Compute ratio factor RF:
  if dogleg is very small (<1e-8):
    RF = 1.0
  else:
    RF = (2 / dogleg) * tan(dogleg / 2)

- Compute delta_md = md2 - md1

- Compute increments:
  dN = (delta_md/2) * (sin(inc1)*cos(azi1) + sin(inc2)*cos(azi2)) * RF
  dE = (delta_md/2) * (sin(inc1)*sin(azi1) + sin(inc2)*sin(azi2)) * RF
  dTVD = (delta_md/2) * (cos(inc1) + cos(inc2)) * RF

Accumulate:
- north += dN
- east += dE
- tvd += dTVD

DLS:
- dogleg_deg = dogleg * 180/pi
- dls_deg_per_100ft = dogleg_deg / delta_md * 100

### Tests
- Test with straight vertical well:
  inc = 0 for all stations, azi arbitrary
  Expect:
    north=east=0
    tvd increases equal to delta_md
    dogleg=0
- Test with constant inclination and azimuth:
  inc constant, azi constant
  Expect:
    dogleg=0
    north/east follow simple trig

## 2) Trajectory interpolation
### Goal
Given an MD value that is between stations, compute:
- tvd_ft, north_ft, east_ft

### MVP approach
- Linear interpolate computed trajectory outputs by md_ft.
- Validate md is within min/max; if outside, clamp or error (choose and document).

Tests:
- Interpolated values at known midpoints match expected linear interpolation.

## 3) Curve resampling and canonical depth basis
### Goal
Make curves from LAS usable for plotting and windowed computations.

### Approach
- Store raw curves as loaded.
- Create a normalized curve table with:
  - depth_md_ft (float array)
  - curve columns (float arrays)
- For plotting, optionally resample to uniform step (default 0.5 ft or 1 ft) using linear interpolation.
- For KPI calculations, choose a consistent MD sampling:
  - Use trajectory station MDs or use the resampled log depth grid.
  - Recommend: use resampled grid for KPIs for stable resolution.

Edge handling:
- Gaps: interpolation should not bridge large gaps without warning.
- Nonpositive values for log-scale resistivity: set to NaN for display.

Tests:
- Resampling preserves end values within tolerance.
- Known analytic curve resampling matches expected.

## 4) Interpretation model evaluation
### Representation
- Piecewise linear control points for top and base:
  - sorted list of (md_ft, tvd_ft)
- Evaluate at any md_ft:
  - If inside range: linear interpolate between bracketing points
  - If outside range: extrapolate using end slope or hold constant (choose one)
MVP recommendation: hold constant outside range for stability.

Validation:
- Ensure top_tvd <= base_tvd for all md in evaluation domain.

Tests:
- Interpolating at midpoints yields expected values.
- Extrapolation behavior matches spec.

## 5) In-zone KPI computation
### Inputs
- active well trajectory function: tvd_well(md)
- interpretation top/base functions: tvd_top(md), tvd_base(md)
- revealed MD interval: [md_min, md_max]
- evaluation grid: md samples in interval

### Computations
For each md sample:
- well_tvd = tvd_well(md)
- top_tvd = tvd_top(md)
- base_tvd = tvd_base(md)

in_zone = (top_tvd <= well_tvd <= base_tvd)

zone_center = (top_tvd + base_tvd) / 2
center_distance = abs(well_tvd - zone_center)

Aggregate:
- percent_in_zone = mean(in_zone)
- avg_center_distance = mean(center_distance)
- max_center_distance (optional)

Tests:
- Synthetic dataset with known zone and well path yields expected percent.

## 6) Optional: similarity hint for correlation
(Not required for MVP)
- Compute normalized cross-correlation of GR windows between wells
- Suggest tie depth where correlation is maximal within +/- window
- Must not auto-apply; only display as hint with confidence score

## Numerical tolerances
- Use absolute tolerance 1e-6 for angle comparisons
- For TVD and offsets, tolerance 1e-3 ft in unit tests

## Definition of Done
- All computations implemented in isolated modules
- Unit tests cover trajectory, DLS, resampling, KPI
- Any nontrivial assumptions are documented in code docstrings and in UI "Assumptions" section
