# Methods and data contract

## Coordinate reference

The flagship scenario is an idealized 2D eastward cross-section. All distances are feet, inclination is degrees from vertical, azimuth is clockwise from north, and TVD is positive downward from the shared local datum. The spatial horizon coordinate is `x_ft = east_ft`. Northing is retained for trajectory bookkeeping; this scenario has no cross-line geological variation.

Every spatial well supplies `reference.json` with `coordinate_system: LOCAL_EAST_NORTH_FT`, a common `vertical_datum`, `origin_east_ft`, `origin_north_ft`, and `initial_tvd_ft`. Initial TVD and origin coordinates apply at the first survey station. A survey beginning after MD zero must provide an explicit TVD tie-in; the software cannot reconstruct the missing upper well. It rejects nonfinite values, duplicate or decreasing MD, and invalid angles.

Minimum curvature integrates each station interval with the standard ratio factor. The zero-dogleg limit uses ratio factor one. TVD/northing/easting begin at the supplied tie-in rather than an assumed zero. Unit conversion applies to LAS measured depths; unknown depth units are rejected.

## Scenario and observations

The default scenario has three vertical offsets at x=0, 500 and 900 ft. A quarter-circle build begins at MD 500 ft and lands at MD 2,000 ft, approximately x=954.93 ft and TVD=1,454.93 ft. The fixed recorded lateral continues to MD 7,000 ft. Landing DLS is 6 degrees/100 ft; the separate causal lateral limit is 3 degrees/100 ft.

One fixed field supplies top and base for every well and strategy. The regional center dips 0.005 ft per horizontal foot; target thickness is 24 ft. Beyond offset support a compact smooth structural transition changes the center by 25 ft. Genuine offset formation crossings define top, midpoint and base markers. These picks are observed synthetic inputs; the operator never receives private horizon parameters.

The idealized GR signal is 80 + 2 times signed distance below center in feet, clipped to 20-160 API, with Gaussian noise of standard deviation 0.6 API. Resistivity decays with absolute center distance plus independent noise. This calibration is disclosed operator knowledge. Inversion is informative only in the unsaturated range; saturated observations constrain direction rather than an exact center.

Random seeds determine observations. Causal sampling is keyed to seed and step so strategies use comparable noise without sharing future paths or measurements.

## Offset interpretation and planning

Ordinary least squares fits the explicitly selected Top_A and Base_A crossings to offset marker positions transformed from MD into shared x and TVD. Other formations are not pooled into the target; each selected well must have exactly one matching crossing per boundary. Predictions extrapolate beyond offset support and therefore depend on a stated regional-line assumption. The minimum 10-ft uncertainty band is a scenario-assumed range, not a statistical confidence interval. The automated replay expands it when saturation removes precise center information.

New interpretation control points have explicit `x_ft`; the retained `md_ft` field supports old project serialization and is not the horizon independent variable in spatial runs. Mixed coordinate models are rejected. Legacy MD-only interpretations cannot be reused as shared geological truth.

The target planner solves a constant-build eastward landing against the offset-derived centerline. For build length L, displacement in both x and TVD is 2L/pi, with TVD additionally including the vertical kickoff depth. It checks target agreement and curvature feasibility. An infeasible combination is rejected. Prescribed geometry can be inspected with violation warnings but is not silently made feasible.

## Runs and information boundaries

Each run owns its configuration, state, interpretations, decisions, metric snapshots and evaluation products under `runs/<run_id>/`. Reinitialization starts a new run. Existing historical records cannot be deleted or rewritten under an existing ID. Project creation and sample generation refuse populated output directories.

Runs snapshot their input records and original formation picks. Regenerating an older report therefore preserves its original evidence even if current project markers are edited. A recoverable write journal rolls back an interrupted advance across history, metrics, environment and simulation state; a retry begins from the last committed step. Forking copies a saved acquired prefix into a new isolated run for alternative commands.

The operator data service clips active survey stations, logs, trajectory and markers at revealed MD, including inputs to range statistics, correlations and report plots. Offset observations remain available in full. Future active values and private truth are inaccessible through the ordinary operator loader. A replay endpoint between recorded survey stations does not fabricate an observed station using future survey data.

Each advance records the recommendation and its supporting observations, creates the applicable interpretation version, and persists the resulting estimated-zone diagnostics. Historical metrics are never recomputed under the newest interpretation. Estimated metrics and withheld-truth outcome scores have distinct labels.

## Causal response and independent evaluation

HOLD preserves inclination. BUILD increases it, DROP decreases it. Requested changes are bounded by the lateral DLS limit and inclination bounds, then integrated with minimum curvature. The sampler uses fixed geology, never the current interpretation. Requested/effective actions and clipping are recorded.

The comparison policy estimates center and local trend from current and preceding GR observations under the disclosed synthetic calibration. It has no access to future observations or geological field parameters. HOLD and guided comparisons share landing state, geology, seed, evaluation interval and mechanics.

Estimated-zone length metrics integrate the piecewise-linear trajectory and interpretation exactly in MD, including boundary crossings and partial final intervals. Mean center distance integrates absolute signed center error. The denominator excludes the build/landing interval. The final-point indicator is not a step-length fraction.

The nonlinear truth field is evaluated only after completion, using a disclosed fine MD integration grid with crossing interpolation and refinement tests. Reports distinguish lateral DLS from the higher landing curvature. Interpretation residuals compare the offset baseline and final estimate with the same independent field; a failed or uncertain estimate is reported as such.

## Reproducibility

The case-study CLI writes stable numeric summaries and records code revision, dirty-state flag, input hashes, seed, coordinate conventions, run ID and plan ID separately. Repeated seeds must reproduce the numeric summary. Reports contain actual PNG figures generated with Matplotlib Agg, and strict builds fail if required figures are missing. PDF bytes and run identifiers need not be identical.
