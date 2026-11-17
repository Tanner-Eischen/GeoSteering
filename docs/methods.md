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

Saved pre-job models embed the selected offset IDs, their observed input hashes,
the active reference metadata, interpretation version and boundary coordinates.
Planning selects a saved model instead of refitting all offsets. Plans and new
runs embed the same content-hashed snapshot; incompatible evidence or changed
source files block a new handoff until the operator reviews and saves a new
model. Historical runs and forks retain the original model and input snapshots.

Command previews use acquired trajectory stations and a content-checked public
mechanics snapshot, never the private geological scenario or future sensor
sampling. They reuse the same bounded minimum-curvature step as advancement,
including shortened final intervals. A replay preview reports only its next
reveal interval because recommendations do not change its recorded path.

Each run owns its configuration, state, interpretations, decisions, metric snapshots and evaluation products under `runs/<run_id>/`. Reinitialization starts a new run. Existing historical records cannot be deleted or rewritten under an existing ID. Project creation and sample generation refuse populated output directories.

Runs snapshot their input records and original formation picks. Regenerating an older report therefore preserves its original evidence even if current project markers are edited. A recoverable write journal rolls back an interrupted advance across history, metrics, environment and simulation state; a retry begins from the last committed step. Forking copies a saved acquired prefix into a new isolated run for alternative commands.

The operator data service clips active survey stations, logs, trajectory and markers at revealed MD, including inputs to range statistics, correlations and report plots. Offset observations remain available in full. Future active values and private truth are inaccessible through the ordinary operator loader. A replay endpoint between recorded survey stations does not fabricate an observed station using future survey data.

Each advance records the recommendation and its supporting observations, creates the applicable interpretation version, and persists the resulting estimated-zone diagnostics. Historical metrics are never recomputed under the newest interpretation. Estimated metrics and withheld-truth outcome scores have distinct labels.

Historical review at decision n uses observations through its `md_from_ft`, the
interpretation recorded with that decision, and persisted metrics through n−1.
After interval n, observations extend through `md_to_ft` and metric n becomes
visible. Frozen input markers replace later project edits. Risk-note strings and
nested newly sampled observations are excluded from decision-time presentation.
Later interpretations never replace an earlier metric snapshot.

Related-branch comparison verifies matching configuration, observed input/model
fingerprints, recorded code identity, mechanical limits, captured field identity
and the common fork prefix. Its endpoint is a station acquired by both branches;
there is no interpolation using a more advanced branch's future station. Both
branches must finish before explicit independent truth comparison, and the
evaluator must return the same lateral denominator. Differences are right minus
left; the denominator includes the shared prefix. Several commands or
interpretation revisions may differ after the fork.

The Evaluation page validates saved completed outcomes against the selected run
before presenting them. Its DLS chart uses the same scenario bound as the
independent scorer. A stricter causal command bound, if configured, is labeled
separately. Placement excludes landing; interpretation mean absolute errors are
averaged over acquired lateral stations, as in the original evaluator.

## Causal response and independent evaluation

HOLD preserves inclination. BUILD increases it, DROP decreases it. Requested changes are bounded by the lateral DLS limit and inclination bounds, then integrated with minimum curvature. The sampler uses fixed geology, never the current interpretation. Requested/effective actions and clipping are recorded.

The comparison policy estimates center and local trend from current and preceding GR observations under the disclosed synthetic calibration. It has no access to future observations or geological field parameters. HOLD and guided comparisons share landing state, geology, seed, evaluation interval and mechanics.

Estimated-zone length metrics integrate the piecewise-linear trajectory and interpretation exactly in MD, including boundary crossings and partial final intervals. Mean center distance integrates absolute signed center error. The denominator excludes the build/landing interval. The final-point indicator is not a step-length fraction.

The nonlinear truth field is evaluated only after completion, using a disclosed fine MD integration grid with crossing interpolation and refinement tests. Reports distinguish lateral DLS from the higher landing curvature. Interpretation residuals compare the offset baseline and final estimate with the same independent field; a failed or uncertain estimate is reported as such.

## Original spatial uncertainty ensemble (v1)

The opt-in ensemble is a sequential particle model, separate from manual
interpretation versions and their assumed uncertainty band. Its structure follows
the importance-weighting/resampling framework described by
[Doucet and Johansen](https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF2011.pdf).
That methodological reference does not validate this application's geological
process or sensor assumptions.

The default model uses 256 members initialized at the acquired start position
from the frozen offset centerline and thickness. Initial center and dip standard
deviations are 10 ft and 0.006 ft/ft. Forward spatial substeps are at most 50 ft.
Center and dip process standard deviations are 2 ft and 0.002 ft/ft per square
root of a 50-ft advance, with dip bounded to ±0.15. A 10% relative lognormal
thickness prior is represented by 64 fixed equal-probability quadrature nodes.
It stays independent because the sensor likelihood identifies center, not
thickness.

The likelihood evaluates the public signed GR response in the forward direction,
clips its latent mean to 20–160 API, and combines 0.6 API sensor noise with an
assumed 4 API model discrepancy in quadrature. Saturation therefore does not
become an exact center inversion. Effective model count is `1 / sum(weight²)`.
Systematic resampling occurs before the next update when the previous ESS is
below half the member count. Forecast-only replication prevents a concentrated
posterior from erasing future process spread; it never changes saved weights.
Current headline statistics use exact saved posterior weights, while forecast
curves are Monte Carlo approximations on one shared 50-ft lattice.

The acquired-data service locates at most one new GR sample per run step using
only acquired survey brackets. It does not multiply likelihoods over every dense
LAS sample. Missing data propagate without weighting; already processed or
non-forward positions are not assimilated again. If a newer station has no new
GR, prediction-only propagation uses that station's pose and never relabels an
old reading. Initial snapshot zero already incorporates the located start GR
when available. Settings, original baseline and per-step snapshots are hashed,
immutable, transactionally recovered and copied with a fork. Decision review
selects ensemble n−1 before decision n and ensemble n after its acquired interval.

Conditional in-target probability marginalizes the center posterior and the
independent thickness prior. Command alternatives share one forecast realization
and bounded geometry. These are next-station probabilities under assumptions,
not calibrated success probabilities. The separate `uncertainty_v1` protocol
measures pre/post observation center coverage, width and valid-domain 250/500-ft
forecasts, retaining the calibration-bias failure. No interval level or model
setting was tuned to its evaluation outcomes.

## Persistent calibration sensitivity (v2)

The original `spatial-particle-v1` settings and state formats remain unchanged.
New `spatial-calibration-v2` runs contain separate conditional filters. For
each fixed bias hypothesis b, the latent response is
`clip(80 + b + 2 * (TVD - center), 20, 160)` API. Observation noise is added
after clipping. Each filter receives the same acquired GR, physical offset
prior and random-stream keys. Shifting already clipped observations is not
equivalent to this model and is not used.

The default five hypotheses are -16, -8, 0, 8 and 16 API with equal external
weights. The support was chosen after the v1 failure became known. It is an
empirical sensitivity range, not an independently calibrated bias distribution.
GR updates only within-hypothesis particle weights. External hypothesis masses
never collapse, resample or learn from GR. This deliberate separation prevents
the confounded geological likelihood from certifying its own calibration.

Pooled particle weights are external hypothesis mass times the conditional
particle weight. Mixture quantiles are inverse weighted empirical-CDF quantiles
of that combined distribution, not averages of conditional quantiles. Thickness
retains the original independent quadrature prior. The separate calibration
envelope takes the minimum conditional 5th percentile and maximum conditional
95th percentile at each location. It is a union of conditional intervals,
not an unconditional calibrated 90% confidence region. The median shown with
that envelope is the mixture median.

Target-probability ranges are the minimum and maximum conditional probabilities;
the separately labeled pooled probability assumes the fixed external weights.
Each command uses the same conditional forecast draws. The reported minimum
effective model count describes within-hypothesis concentration and cannot be
interpreted as evidence that a calibration assumption is correct.

The distinct `calibration_v2` protocol pairs original and new filters on identical
observations. Historical failures are development diagnostics. New evaluation
configurations and seeds are frozen before any outcomes are read, and an
outside-support bias case tests the limits of the assumed range. Coverage and
width are reported separately for original nominal intervals, pooled nominal
intervals and sensitivity envelopes. Truth is consulted only after all updates
and predictions. Existing study artifacts remain immutable.

## Reproducibility

The case-study CLI writes stable numeric summaries and records code revision, dirty-state flag, input hashes, seed, coordinate conventions, run ID and plan ID separately. Repeated seeds must reproduce the numeric summary. Reports contain actual PNG figures generated with Matplotlib Agg, and strict builds fail if required figures are missing. PDF bytes and run identifiers need not be identical.
