# Geosteering under structural uncertainty

## Problem

Three offset wells constrain a dipping target interval, but do not reveal a localized structural change farther along the active lateral. The study asks how progressively acquired logs improve an interpretation, and whether a bounded observation-guided policy can improve placement in the same fixed synthetic geology.

## Data and workflow

The versioned structural_dip_01 scenario contains three vertical offsets and one active well, LAS GR/resistivity logs, surveys, geological crossing markers and explicit local coordinate references. The target is 24 ft thick and the evaluated lateral is 5,000 ft long. Seed 123 is the reference experiment.

The operator estimates regional top/base from offset markers, solves the landing, and receives active measurements in successive intervals. Each recommendation cites observed log/position evidence and an immutable interpretation version. A separate evaluator reveals geological truth only after the run finishes.

The selected pre-job model now travels intact from Correlation to Planning and
the steering run. Plans and runs retain its version, selected offset wells,
boundary coordinates and evidence hashes. Changed source picks require a new
deliberately reviewed model before a new plan or run; earlier histories retain
their original evidence. A selected plan pins geology, while a causal run begins
at its acquired landing station rather than executing saved plan stations.

Before advancing a causal run, the operator can inspect requested versus effective
inclination, the next projected station, DLS and any clipping. This preview uses
acquired geometry and a captured public mechanics snapshot. It neither samples
future logs nor reads private geology. Fixed-path replay shows a recommendation
and reveal interval without inventing a future trajectory preview.

Replay and causal experiments answer different questions. The replay uses a fixed HOLD-like path, so its recommendations can improve interpretation but cannot improve recorded placement. The causal experiments start from the same landing state and apply actual bounded commands.

Decision Review reconstructs the saved information boundary at any recorded
step. Its decision phase shows the chosen interpretation and the observations
known before the command; its after phase adds that interval's observations and
original persisted diagnostic. A side-by-side fork comparison holds the frozen
experiment and acquired endpoint common while exposing divergent commands and
paths. The Evaluation page connects completed placement, interpretation error
and curvature checks to those histories. These views expose the existing evidence;
they do not change or recalibrate the scientific results below.

## Measured reference result

The reference HOLD run places approximately 38.1% of the lateral in the target. The observation-guided causal run places approximately 97.2% in target, while respecting the 3 degrees/100 ft lateral DLS limit. Exact lengths, center-distance errors, overshoot, clipping and action-change counts are in the generated summary.

![Controlled causal comparison](figures/strategy_comparison.png)

![Observed offset constraints](figures/correlation_snapshot.png)

![Persisted estimated-zone diagnostics](figures/kpi_trend.png)

These outcomes are specific to the known synthetic calibration, geometry and seed. The baseline comparison does not validate operational steering. Required report figures include the plan, DLS, observed correlations, interpretation, per-step diagnostics, recommendation timeline and completed comparison.

## Failure analysis

The offsets cannot predict the localized disturbance. In the fixed replay the well eventually leaves the target; recommendations do not change that outcome. Sufficiently distant observations saturate the synthetic sensor, so they cannot justify an exact center inversion. The replay records that information loss and carries an uncertain interpretation forward. Final interpretation residuals and true placement scores remain visible even when they are worse than an estimated diagnostic suggests.

The guided causal policy benefits from a disclosed signed stratigraphic signal. That assumption explains much of its performance and is a central limitation, not an operational capability claim.

## Held-out robustness study

The next experiment asks whether observation guidance remains useful when the
geology changes and measurements become imperfect. A versioned protocol fixes
two development controls, eight different evaluation configurations, disjoint
development/evaluation noise seeds, and three strategies before execution.
The complete study contains 132 trials: 12 development and 120 evaluation.

HOLD, an offset-derived regional plan and observation-guided feedback share the
same landing state, geology, mechanical limits and step-keyed random draws
within each case/seed pair. The regional plan follows a centerline fitted to
offset picks without using active-well logs. Guidance retains the reference
controller and its nominal GR calibration; a fixed validity wrapper excludes
missing/saturated measurements and retains the original acquisition pose of
delayed observations. It applies HOLD when no usable measurement arrives.

| Strategy | Mean true lateral in zone across evaluation cases |
| --- | ---: |
| HOLD | 28.34% |
| Offset-derived regional plan | 39.29% |
| Observation-guided | 85.83% |

Guided steering exceeds the regional-plan baseline in 38 of 40 evaluation
pairs, with a mean difference of 46.54 percentage points. The two slightly
negative differences occur in the saturation case; the minimum is −0.01174
percentage points. All 120 evaluation trials have zero lateral DLS violations
under the evaluator tolerance. These are descriptive outcomes for the predefined
synthetic configurations, not estimates of field performance.

![Paired outcomes across held-out configurations](figures/robustness_results.png)

### A decision sequence that fails

The saturation/large-change configuration shows the value and limits of the
information boundary:

1. Exact offset markers support a regional model but do not reveal the later
   structural change.
2. As the well diverges from the target, the instrument reaches its clipping
   range. Its validity flag prevents a saturated GR value from being treated as
   an exact center estimate.
3. With no new usable measurements, the fixed wrapper applies HOLD. Respecting
   the curvature bound does not restore geological observability or guarantee
   target placement.

The worst guided trial, seed 1013, has 62 saturated measurements, 37.31% in-zone
placement and a maximum excursion of 78.03 ft beyond a target boundary.
Its trajectory and measurements remain in the evidence rather than being
removed from the headline result.

![Worst guided evaluation trial](figures/robustness_worst_case.png)

The [full study](../case_studies/robustness_v1/README.md) contains per-case
outcomes, the executed manifest, paired CSVs and complete compressed event
histories. Source copies and protocol hashes were frozen before execution;
repeat runs confirm numerical reproducibility, not independent replication.
The evaluated cases are now observed and cannot serve as an untouched holdout
for future policy tuning.

These cases combine sensor and geological stresses in places, so they locate
failure regimes rather than isolate each factor's causal effect. Noise-seed
ranges describe variation within fixed geology. The sensor still supplies
signed-distance information when valid, offset picks remain idealized, and no
calibrated geological uncertainty distribution has been established.

## The original conditional uncertainty ensemble

The original v1 model uses a 256-member spatial particle ensemble. The
prior comes from the frozen offset model. Each acquired step uses at most one
new located GR measurement at its original pose, updates member weights through
the clipped forward sensor likelihood, and records an immutable snapshot.
Missing measurements add no likelihood. Systematic resampling controls weight
concentration; independent future process draws keep forecast spread visible
even when the current weights concentrate on one member.

The app shows weighted center intervals, independent thickness uncertainty,
effective model count, and conditional probability of being in the target. HOLD,
BUILD and DROP assessments share one geological forecast and the existing bounded
mechanics. They describe the next station, not whole-well success. Snapshot zero
already includes the acquired start measurement; it is not an untouched pre-job
prior. Current cards use exact saved weights; displayed forecast paths are Monte
Carlo approximations. Historical review and forks retain their original snapshots.

A separate frozen 34-trial study evaluates center intervals on fixed HOLD paths:
two development controls and six new evaluation configurations, with disjoint
seeds. It measures uncertainty quality rather than ranking steering policies.

| Nominal 90% center interval | Mean evaluation coverage | Mean width |
| --- | ---: | ---: |
| Before current observation | 81.22% | 25.67 ft |
| After current observation | 70.89% | 23.36 ft |
| 250-ft forecast | 85.73% | 31.79 ft |
| 500-ft forecast | 83.96% | 38.59 ft |

![Measured uncertainty coverage and width](figures/uncertainty_coverage.png)

The nominal intervals are not calibrated guarantees. In the worst biased-sensor
trial, seed 7001, the posterior covered the true center at only **3 of 101
stations (2.97%)**, despite mean effective model count 145.43 and zero predictive
conflict flags. The undisclosed +8 API bias shifted the inferred center by about
4 ft under the assumed calibration. The model fit the biased observations while
remaining wrong about geology. Good-looking weights do not establish accuracy.

![Bias failure with healthy particle diagnostics](figures/uncertainty_failure.png)

Coverage must be read alongside width and center error: wider forecasts can
cover a biased center without correcting their medians. Current prior/posterior
scores share the same locations; forecasts have explicit domain exclusions and
paired-origin results. Seed variation combines instrument variation and finite
ensemble Monte Carlo variation. Correlated stations are not independent samples,
and center coverage does not validate the separate thickness prior.

The [uncertainty study](../case_studies/uncertainty_v1/README.md) includes all
settings, valid point counts, event histories, diagnostics, source archive and
failure results. No settings were tuned to these outcomes; repeated execution
checks reproducibility, not independent confirmation. This evidence makes the
model's uncertainty assumptions testable and exposes substantial miscoverage.
The earlier placement benchmarks remain unchanged.

## Preserving unresolved sensor calibration

The v1 failure is now development evidence for a model change. Adding more
independent measurement noise cannot represent one calibration error shared by
all observations. Away from clipping, a +8 API intercept error resembles a
4-ft center shift under the 2 API/ft response. Repeated observations alone do
not determine which interpretation is correct.

New runs default to a separately versioned calibration-sensitivity ensemble.
Five filters share the same physical offset prior and acquired observations,
while assuming persistent biases of -16, -8, 0, 8 and 16 API. Each hypothesis
changes the sensor intercept inside the clipped forward model. The app does
not subtract bias from an already clipped observation. Conditional particles
update within each filter; the external equal hypothesis weights stay fixed.
Those weights express a declared sensitivity analysis, not learned calibration
or a full Bayesian model comparison.

The pooled nominal 90% interval uses the combined weighted particle distribution.
The calibration envelope spans the conditional lower and upper interval bounds
across hypotheses. The app distinguishes these two intervals, shows minimum
conditional effective model count, and reports the range of conditional target
probabilities for each command. A well-fitting hypothesis cannot erase the
other calibration assumptions. At default settings this requires five sets of
256 particles rather than one, increasing computation and saved-state size.

This change preserves unresolved ambiguity rather than claiming to recover the
true bias. Original v1 runs, settings, snapshots and study evidence remain
unchanged. Neither the pooled interval nor the envelope is certified to achieve
90% field coverage. Clipping, structural mismatch, sparse offset constraints,
and calibration errors outside the declared support remain failure modes.

The [paired calibration study](../case_studies/calibration_v2/PROTOCOL.md) freezes
the new settings and source before execution. It reuses the historical +8 API
failure only as a labeled development diagnostic. Fresh evaluation cases and
seeds compare both models on exactly the same fixed-HOLD observations, including
negative bias, bias between hypotheses and bias outside the assumed range.
Coverage is reported alongside width and explicit forecast-domain counts.

The completed study contains 20 pairs: two development diagnostics and 18 new
evaluation pairs across six configurations. Both models use the same observations;
the 40 model runs are not independent experiments. Equal-case current posterior
results are:

| Reported interval | Center coverage | Mean width |
| --- | ---: | ---: |
| Original v1 nominal 90% | 47.63% | 16.87 ft |
| Fixed calibration mixture nominal 90% | 78.22% | 28.62 ft |
| Calibration sensitivity envelope | 79.43% | 35.11 ft |

![Paired calibration coverage and interval width](figures/calibration_coverage.png)

This improvement comes from preserving a wider set of plausible positions.
Mean median-center absolute error does not improve: 9.65 ft for v1 and 9.70 ft
for v2. The reused +8 API/seed7001 diagnostic changes from 3/101 covered stations
to 101/101 for both new interval types, while mean width increases from 5.30 ft
to 18.19 ft for the mixture and 21.28 ft for the envelope. This repair informed
development and is explicitly excluded from the fresh evaluation aggregate.

The correction has a clear boundary. In the new +28 API case, outside the
declared ±16 API support, all three interval types cover **0/101 posterior
stations** in seed8101. The envelope averages 21.27 ft wide and its median
remains about 14 ft wrong. Minimum conditional effective model count averages
123.52, and no observation conflicts with every hypothesis's predictive interval.
Internal fit still cannot establish calibration. Abrupt/saturated geology also
under-covers: the envelope averages 76.57% current posterior coverage in that
configuration. Both failures remain in the headline aggregate.

![Reused diagnostic and new outside-support failure](figures/calibration_failure.png)

Across the six fresh cases, 250-ft envelope coverage is 95.20% with 45.03-ft mean
width, and 500-ft coverage is 95.18% with 52.82-ft width. Larger forecast widths
can cover a biased center without improving the median. The respective 96 and
91 valid targets per pair are scored only within the evaluated domain. These
descriptive results do not establish nominal coverage for the envelope, validate
thickness or turn conditional command probabilities into field guarantees.

The [complete paired results](../case_studies/calibration_v2/README.md) retain
all observations, interval summaries, paired differences, source/protocol hashes
and failure diagnostics. The evaluated configurations are now observed and must
not be reused as untouched validation after further model changes.

## Validation and reproduction

```powershell
python -m pip install -e ".[test,dev]"
python -m pytest
python -m ruff check app tools tests app.py
python -m build
python -m tools.run_case_study --out output/my-case-study --seed 123
python -m tools.run_robustness_study --out output/my-robustness-study
python -m tools.run_uncertainty_study --out output/my-uncertainty-study
python -m tools.run_calibration_study --out output/my-calibration-study
```

Use a fresh output directory. The report, numerical summary, decision CSV, plan CSV and artifact manifest are under the generated project exports. The run manifest identifies input hashes, seed, scenario version, code revision and coordinate reference. Automated tests independently check geometry, interval scoring, information isolation, history, reproducibility, bounded causal consequences, PDF text and embedded images.

See [methods](methods.md) for the full contract and [limitations](limitations.md) for the scope of the conclusions.

## Portfolio wording

Implemented a reproducible synthetic geosteering workbench with evidence-pinned
interpretation/plan/run handoffs, acquired-only steering command previews,
minimum-curvature modeling, immutable decision-time metrics and independent
evaluation. A frozen 132-trial study tests three causal strategies across held-out
geological configurations and sensor stresses, including documented failures.

A separate portfolio repository or resume has not been modified.
