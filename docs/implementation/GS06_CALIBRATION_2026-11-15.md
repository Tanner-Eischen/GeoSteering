# Persistent calibration sensitivity

November 15, 2026. Implementation plan and local acceptance record.

## Plan reviewed against the source

The v1 study exposed a persistent +8 API bias that its independent per-reading
discrepancy could absorb while reporting narrow, inaccurate center intervals.
The synthetic instrument adds bias before clipping. Correct conditional filters
therefore change the sensor intercept inside the clipped forward response; they
must not subtract bias from already clipped GR observations.

Preserve v1 settings, saved histories and evidence. Add a distinct v2 model
containing five unchanged v1 filters, each with the same physical offset prior
and one persistent bias assumption (-16, -8, 0, 8, 16 API). Their external equal
weights remain fixed. GR alone does not estimate those weights or certify its
own calibration. Combine particle distributions for mixture quantiles and show
the envelope of conditional intervals separately. Retain independent thickness.

Affected modules: ensemble settings and dispatch, a new calibration engine,
run configuration, uncertainty displays/plots and command assessment, a new
paired study, packaging and case-study documentation. Existing acquisition,
transaction and fork mechanisms should carry the new JSON state unchanged.

Risks: calibration/geology confounding, incorrect clipping order, accidental
v1 serialization migration, loss of nuisance spread through resampling,
misleading mixture probabilities and increased filtering/snapshot cost.

Verification: pure model and saturation fixtures, exact zero-bias reduction,
fixed hypothesis masses, old-history replay, persistence/retry/fork checks,
new evidence frozen before evaluation, full supported-Python test suite, lint,
source/wheel builds and installed evidence, unchanged reference outcomes, and
actual desktop/narrow browser run creation, command assessment, history,
downloads and branch preservation. UI checks are explicitly authorized by the
current user request.

## Acceptance results

The new study completed all 20 pairs (two development and 18 fresh evaluation
pairs; 40 model runs). Fresh posterior center coverage / mean width is 47.63% /
16.87 ft for v1, 78.22% / 28.62 ft for the fixed mixture, and 79.43% / 35.11 ft for
the envelope. Median-center MAE does not improve (9.65 ft versus 9.70 ft).
The reused +8 API/seed7001 diagnostic improves from 3/101 to 101/101 covered
stations. It informed development and is excluded from the fresh aggregate.

The +28 API outside-support trial still covers 0/101 posterior stations with all
three interval types. Healthy mean minimum-conditional ESS (123.52) and zero
all-hypothesis predictive conflicts do not certify coverage. Abrupt/saturation
envelope coverage is 76.57%. These failures remain visible and unmodified. No
calibration or operational-accuracy guarantee is implied by the change.

All 120 new study artifacts/source hashes were verified. The complete worst
fresh 101-event pair replayed exactly; all 2,020 study events retain weight0.2
for every hypothesis and exact equality between the zero-bias branch and paired
v1. The 219 files in both earlier evidence directories remain byte-identical.
All 34 original uncertainty histories replayed against 3,434 state/forecast
events without a mismatch. The original four serialized engine fixtures and
single-zero-bias reduction also pass.

The supported CPython3.12.11 run passed all 352 tests outside the separate bundled
evidence-page file in 811.50 seconds. The additional evidence-page test passed,
for 353 distinct tests. A final presentation-only adjustment makes coverage and
width visible together on narrow screens; all 11 affected UI/integration tests
then passed in20.59 seconds. There are no persisted provenance bypasses.
The final source differs from the full-suite snapshot only in
`app/pages/calibration_evidence.py`, which those final checks exercise.

Browser controls created a256-particle-per-hypothesis v2 causal run, downloaded
its exact original snapshot, recorded BUILD to step1, forked it and recorded
DROP to step2 in the visibly selected child. All36 parent files, both copied
ensemble prefix snapshots, and all31 legacy-run files remain unchanged. The
historical child step0 download equals the original parent download. No command
assessment samples future logs or private geology.

Local Chrome checks cover1440×1000,900×900 and390×844 layouts. The command
summary puts probability ranges before geometry, with detailed fields in an
expander. The evidence view separates pooled intervals from envelopes, reports
coverage alongside width, labels the reused diagnostic and preserves the
0/101 outside-support failure. The original v1 study remains selectable. Physical
mobile devices, other browsers, Linux runtime/CI and deployment were not tested.

Frozen scientific-study source:
`63bf85b1cd76e562cbabaa1b5b1c3ca551d7b22b1254809aff6415cba64fcec5`.
Final application source:
`b6bf716b28a6433afd5c6634690da7b6406e4822d0fedc8b9da8b7b8381d521d`.
The scientific engine/study modules still match their frozen study copies;
later display changes have their own source identity.

Logs, reference projects and machine acceptance records are under
`output/verification-gs06-2026-11-15/`; browser images/downloads use
`output/playwright/gs06-*`. These local output paths are intentionally ignored.
No commit, push or deployment was requested or performed for this increment.

Review corrections: preserve bias inside clipping, keep old model serialization
unchanged, and bind result-table columns to explicit interval keys. A README
table initially interchanged pooled and envelope columns after JSON sorted its
keys; all three numerical tables were subsequently checked against the saved
summary. Suggested repository rule: use explicit column ordering for evidence
tables and check each labeled value against its source artifact. Restart an
owned Streamlit helper before final browser QA after imported page modules
change. No AGENTS.md or memory files were changed.

Final packaging acceptance: source and wheel builds succeeded. A fresh isolated
CPython3.12 environment installed the exact hash-checked Windows release lock.
The installed-wheel probe verified all104 executable Python files, all61 locked
distributions, exact wheel/checkout/installed bytes and `pip check`. Installed
resource checks loaded the20-pair calibration bundle,34-trial original uncertainty
bundle and132-trial placement bundle. The installed calibration page rendered
successfully under the locked Streamlit version. An initial probe against an
older reused runtime environment lacked the complete release lock; the fresh
locked-environment probe passed without changing or bypassing its checks.

A fresh reference built with the final application fingerprint passed its
verifier, retaining38.0716208% HOLD and97.1742657% guided placement. The final
Chrome session recorded zero console errors and warnings; earlier restart
connection errors remain in their original trace. The final helper is available
at `http://127.0.0.1:8523`. Machine results are in `verification.json` alongside
the test XML, installed probes, final reference verifier and fork proofs.
