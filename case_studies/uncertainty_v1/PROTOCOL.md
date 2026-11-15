# Uncertainty calibration study v1

This protocol evaluates uncertainty quality along one fixed HOLD trajectory.
It does not rank new steering policies or claim an operational drilling benefit.
The particle model and all settings are fixed before evaluation. The source and
manifest are captured before the first trial. No settings are changed in response
to the reported evaluation outcomes.

Two development controls use two noise seeds each. Six evaluation configurations
use five new noise seeds each, for 34 trials. The evaluation geological settings
and seeds are distinct from development and from the already observed robustness
study. Cases are handpicked stress tests, not samples from a geological population.
This is a local predeclared protocol, not an externally registered experiment.
Once inspected, these evaluation cases are no longer untouched data for later
ensemble development.

## Observations, model and information boundary

All trials use the existing 2D Scenario field and causal minimum-curvature HOLD
path: 5,000 ft after landing, 50-ft stations and 101 measurement locations including
the landing and final station. The path does not respond to observations or truth.
Exact synthetic top/base picks at x=0, 500 and 900 ft fit the initial regional model.
The filter receives those model control points, current acquired pose and GR only.
It cannot read private Scenario parameters, true centers or future measurements.

The instrument independently samples the fixed field using predeclared sensor
noise, bias and missingness. Its stream is keyed by trial seed and station index.
The ensemble seed is the trial seed plus 900,000 and has a separate random stream.
Missing measurements propagate the filter without applying a likelihood.
Available saturated measurements use the known clipped forward model; they are
never converted into an exact signed-distance center. The instrument's private
raw-saturation flag is retained for retrospective diagnostics, not fed to the
filter as hidden geological information. No delayed telemetry is used here.

The model assumes a signed GR center response of 80 API, gradient 2 API/ft and
latent clipping at 20–160 API. Likelihood spread combines 0.6 API measurement
noise and 4 API discrepancy in quadrature. There are 256 particles, a 10-ft
initial center standard deviation, dip standard deviation 0.006 and independent
relative thickness standard deviation 0.10. Process spreads are 2 ft in center
and 0.002 in dip per square root of 50 ft. Systematic resampling occurs before
the next update if the preceding posterior ESS is below half the particle count.
The current posterior's weighted ESS remains visible.

For future process forecasts only, a low-ESS posterior is replicated by systematic
weighted resampling before future process draws. This improves the Monte Carlo
representation without changing the stored posterior or its reported ESS.
Current-station summaries retain the exact weighted particle distribution.

## Intervals and paired scoring locations

The scored quantity is the **geological center**, not top/base coverage, target
placement or a guarantee about the next command. Nominal 90% intervals are the
weighted 5th–95th percentiles under this model.

At every current station, record a propagated **pre-observation prior** before
using that station's GR, then a **posterior** after the update. Both are scored
at the same x coordinate against the same withheld center. The prior is obtained
by a missing-measurement update from the old state; the actual update is also
performed from that old state, using the identical measurement-independent
process draws. The actual observation is not applied to the consumed prior state.

After the posterior, record 250-ft and 500-ft along-track forecasts without using
any future measurements. Only targets within the fixed trajectory's evaluated
x domain are scored. Future targets beyond that domain are excluded with an
explicit reason and denominator count. Primary forecast scores use all valid
origins for each horizon. Additional paired-origin scores restrict both horizons
to origins where both forecasts are in domain, so horizon comparisons can use
the same origins. Their target coordinates remain 250 and 500 ft ahead.

Truth scoring occurs after the complete trial. For each trial and phase, report
point count, covered count, coverage percentage, mean width and mean absolute
median-center error. Then average trial metrics within each case, and give cases
equal weight in development and evaluation summaries. Do not pool correlated MD
points into independent sample sizes or inferential confidence intervals.

## Failure diagnostics and immutable evidence

Report missing/dropped measurements, true instrument saturation, filter-declared
saturation, predictive conflict, resampling and posterior ESS. An ESS collapse
step is defined here as ESS below max(2, 2% of particle count); a collapse episode
starts when a trial enters that state. This is a descriptive particle-degeneracy
flag, not a calibrated probability of geological error. It is fixed before results.

The worst evaluation posterior-coverage trial is retained for a failure figure;
it is not removed from aggregate results. Narrow intervals can have poor coverage,
and good posterior fit does not establish good forecast calibration. The known
sensor assumptions, exact offsets and model discrepancy constrain interpretation.
Thickness is weakly informed by this sensor; center-only scores must not be used
as validation of thickness uncertainty.

`histories.jsonl.gz` stores complete event histories with measurement, prior and
posterior interval summaries, forecast intervals, diagnostics, the initial full
particle state and per-step particle-state/forecast hashes. Intermediate particle
states can be regenerated exactly from the frozen engine and acquired observations;
they are not duplicated thousands of times in the evidence archive. A complete
trial replay is tested against all saved state and forecast hashes.
`point_metrics.csv.gz` retains every scored location and its
truth comparison; `trial_metrics.csv` and `summary.json` contain the prescribed
aggregations. Gzip headers have zero timestamps and no embedded output filename.
`frozen_source.zip` stores source copies with sorted entries and fixed timestamps.
`freeze.json` identifies source bytes, the executed protocol and environment;
`PROTOCOL.md` is copied into the output before trial execution. `artifacts.json` indexes
all evidence. The loader verifies checksums, archived source and metadata
consistency; installed wheels can use the source archive without expanded files.

Reproduce into a new directory from the source repository:

```powershell
python -m tools.run_uncertainty_study --out output/uncertainty-v1-reproduction
```

Existing evidence is never silently replaced. An interrupted or failed run has
no complete artifact index. A rerun of this fixed protocol is a reproducibility
check, not a new independent evaluation.
