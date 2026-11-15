# Synthetic robustness study v1

The manifest fixes two development configurations, eight evaluation configurations,
two development noise seeds and five distinct evaluation noise seeds. The 132
trials pair three strategies within each case and seed. Evaluation geology is
different from development geology, rather than merely changing random noise.
The manifest and executable source copies are frozen before trial execution.
This is a local, predeclared protocol, not an externally registered experiment.
The evaluation set is used once for this reported study and is no longer an
untouched holdout for future policy development.

## Controller and information contract

All runs start from the same landing and use the same fixed 2D field, 50-ft
command intervals, 5,000-ft lateral and 3 degrees/100 ft curvature limit. The
85–95 degree inclination bounds and existing minimum-curvature integration are
unchanged. Truth is sampled by the synthetic instrument and after completion by
the independent evaluator, never by the controller.

- **HOLD:** retain inclination, irrespective of observed logs.
- **Offset-derived plan:** fit a regional centerline to the exact synthetic
  top/base marker picks at x=0, 500 and 900 ft; follow that frozen line using the
  same 150-ft correction length and slope limits as the guided controller.
  It can use current pose, but never active logs or the hidden disturbance.
- **Observation-guided:** use the unchanged reference `guided_command` function.
  Its 80 API center and 2 API/ft gradient assumptions are retained in every case.
  A fixed validity wrapper excludes missing and instrument-flagged saturated
  observations. If no usable observation arrives at a step, HOLD is applied.
  Measurements delayed by telemetry keep their actual acquisition x and TVD;
  they are never relabeled with the receiving station's pose or appended twice.

The instrument uses a configured bias and gradient, clips before adding Gaussian
noise, and reports its clipping status as a saturation flag. Saturated samples
provide no exact-center estimate. A narrower configured range models an
instrument that loses dynamic range. The controller receives valid GR values
and acquisition coordinates, but not the true bias, gradient or geology.

Noise is keyed by `(seed, acquisition step, 7183)`, with a standard-normal draw
and a missingness uniform drawn at every station. The three strategies share
these draws; their signal and saturation may differ because their paths differ.
This stream differs from the historical reference experiment and does not replace
its seed-123 numerical results. Trajectories are causal and only final placement
is scored against private truth at the existing 1-ft integration resolution.

## Reported outcomes and limits

`trials.csv` contains final placement, center error, overshoot, DLS, clipping,
action changes, total inclination change and observation-availability counts.
`paired.csv` contains within-case, within-seed percentage-point differences.
`histories.jsonl.gz` retains every sampled/delivered observation, command and
station in deterministic gzip encoding (zero timestamp and no embedded filename).
`summary.json` separates development and evaluation results and identifies the
worst guided trial without removing it. Equal case-weighted evaluation means and
mean/min/max over seeds are descriptive. No inferential confidence intervals,
p-values or real-field performance claims are made.

Sensor stresses and geology change together in several cases. These cases locate
failure regimes; they are not a factorial experiment identifying isolated causal
effects. The sparse marker picks remain exact and the sensor continues to supply
a signed-distance signal when valid. Neither the regional-plan baseline nor the
guided controller models tool physics or drilling safety.

Reproduce from the repository root into a fresh directory:

```powershell
python -m tools.run_robustness_study --out output/robustness-v1-reproduction
```

`freeze.json` records source hashes, Python and dependency versions. `frozen_source`
contains executable source copies and the project dependency specification taken
before any trial; `manifest.json` is the exact executed manifest. `artifacts.json`
hashes all output artifacts, including source copies. Existing outputs cannot be
silently replaced. An interrupted or failed run records `failure.json`, never a
complete artifact index.

`frozen_source.zip` contains the same source bytes with sorted entries and fixed
timestamps. It is mandatory in both repository and installed-wheel evidence.
Loading a study verifies root artifact checksums, every archived source against
the freeze index, and the expanded source tree whenever it is present. It also
checks that manifest identity and source fingerprints agree across the manifest,
freeze and summary; unsafe archive or index paths are rejected without extraction.
