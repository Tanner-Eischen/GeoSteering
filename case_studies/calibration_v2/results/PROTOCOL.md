# Calibration sensitivity study v2

This study was designed after the v1 uncertainty study exposed a systematic +8 API
calibration failure. The five bias hypotheses −16, −8, 0, +8 and +16 API and their
equal weights are **empirically chosen sensitivity support**. They are not learned
calibration probabilities or a demonstrated 90% coverage guarantee. No hypothesis
support, weights, likelihood spread or process settings may be tuned to the new
evaluation outcomes.

The manifest is fixed before the new evaluation. Two development trials use seed
7001: one exactly reproduces the already observed `uncertainty_v1/eval_bias/7001`
failure and is labeled **reused diagnostic**; the other is a nominal control.
The reused failure is not fresh validation. Six new evaluation geological/sensor
configurations use seeds 8101, 8103 and 8107. Evaluation geology and measurement
seeds are disjoint from both earlier protocols. There are **20 paired trials**:
two development pairs and 18 evaluation pairs, each run under v1 and v2. These
are not 40 independent experiments. Cases remain handpicked descriptive tests.

## Paired information and model contract

Each pair uses one fixed 5,000-ft HOLD path with 101 stations at 50-ft spacing,
the same synthetic observed offset picks at x=0, 500 and 900 ft, and exactly the
same acquired GR values and missingness. The instrument is sampled once per
station. The filter receives only the offset-derived model and acquired pose/GR;
it cannot access private geology or future observations. Truth scoring starts
after the entire paired observation sequence has been processed.

The v1 settings are unchanged. V2 maintains five independent conditional v1
filters whose sensor center is `80 + bias` API inside the known 20–160 API latent
clipping model. Bias weights stay fixed at 0.2 throughout. All components and
the paired v1 filter start with the same ensemble seed, trial seed +900,000,
and share the underlying namespaced process and resampling random streams.
The zero-bias conditional state must match the paired v1 state exactly at every
step. The hypotheses do not imply that the data identify calibration bias.

Both filters retain 256 members per conditional branch, 10-ft center prior spread,
dip spread 0.006, independent thickness relative spread 0.10, process spreads
2 ft and 0.002 per square root of 50 ft, and likelihood error combining 0.6 API
noise and 4 API discrepancy in quadrature. Missing observations propagate without
likelihood. Saturated observations use clipped forward likelihoods, never exact
center inversion. All fixed settings are written explicitly in the manifest.

## Three interval types and four scoring phases

The study scores geological **center** intervals, not steering performance,
thickness accuracy or drilling safety:

1. **V1 nominal:** the original model's weighted 5th–95th percentile interval.
2. **V2 pooled nominal:** weighted 5th–95th percentiles of the fixed equal-weight
   mixture. These are conditional on an assumed calibration mixture, not an
   identified posterior probability for calibration bias.
3. **V2 sensitivity envelope:** the minimum conditional q05 through maximum
   conditional q95, with the pooled median for center-error scoring. It is the
   hull of conditional intervals and has **no nominal coverage guarantee**.

For each type, report the current pre-observation prior, current posterior and
250-ft/500-ft forecasts. Prior queries use a missing-GR update from the old state;
the actual measurement update also starts from that old state and shares the
same measurement-independent propagation draws. Forecasts use no future logs.
Current prior/posterior scores use identical truth locations. Forecast targets
beyond the public evaluated x domain are excluded explicitly. There are 101
current points, 96 valid 250-ft forecasts and 91 valid 500-ft forecasts per trial.
Additional paired-origin results use the same 91 origins for both horizons.

## Aggregation, failures and evidence

First calculate coverage, interval width and median-center absolute error within
each trial. Then average trials within cases and give cases equal weight. Report
within-pair coverage and width deltas relative to v1, alongside all absolute
metrics. Correlated spatial stations are not independent confidence-interval
samples. Seed variation includes instrument variability and finite-ensemble Monte
Carlo variation. No inferential population confidence intervals are claimed.

Retain the fresh worst posterior-envelope-coverage trial and the +28 API bias
case outside the specified support, even if the envelope fails. Wider intervals
may improve coverage by trading precision; this is not automatically more accurate
inference. Record conditional ESS, predictive conflict, saturation and missingness.
The reused historical failure is plotted separately from the worst fresh trial.

The source, protocol and manifest are frozen before new evaluation. Histories
retain initial states, one shared acquired measurement sequence, prior/posterior
state hashes and forecast hashes for both models, interval summaries and health
diagnostics. Exact replay from the frozen engine verifies state and forecast
hashes. Deterministic gzip, CSV tables, source ZIP and an artifact checksum index
preserve evidence; the loader verifies complete source/metadata consistency.

```powershell
python -m tools.run_calibration_study --out output/new-calibration-sensitivity
```

Use a fresh output directory. A repeated run is a reproducibility check, not fresh
independent evaluation. The new evaluation cases become observed after this study;
future tuning requires different held-out cases. Earlier v1 evidence is preserved.
