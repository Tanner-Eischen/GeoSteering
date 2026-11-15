# Acquired-data uncertainty ensemble

November 8, 2026. Local implementation and acceptance record.

## Scope and information boundaries

The ensemble is enabled only on a new synthetic-calibration run; existing runs
remain unchanged. Original offset-derived boundaries initialize the prior.
Acquired GR updates particle weights, while manual interpretation revisions are
not counted again as measurements. The existing steering policies, deterministic
reference results and original assumed uncertainty bands are preserved.

Full per-step particle snapshots live under each run's `uncertainty/steps/`.
Frozen settings/baseline fingerprints and a hash chain support inspection and
forks. The step transaction checkpoints the pointer and only its next snapshot,
so failures/retries restore the last committed state without rewriting history.
Decision Review uses the phase-correct original snapshot.

## Acceptance inventory

| Requirement | Verification |
| --- | --- |
| Correct weighted model | Normalized weights, stable extreme likelihoods, exact weighted quantiles and independent thickness prior |
| Honest forecasting | Shared query-independent spatial draws, positive future process spread at ESS1, saved posterior unchanged |
| Acquired information only | No truth/sampler calls; original-pose, missing, duplicate and stationary/no-new-survey cases |
| Durable histories | Retry, rollback, interrupted recovery, immutable snapshots, fork parent preservation and selected-run isolation |
| Useful UI | Actual new-run opt-in, updated ensemble, forecast plot, next-command probabilities, snapshot/CSV downloads |
| Historical fidelity | Pre/post interval snapshots and old snapshots retained after new measurements |
| Measured uncertainty quality | Frozen 34-trial study; coverage, width, domain counts, biases and failure diagnostics |
| Local acceptance | Full suite, lint, source/wheel builds, installed resources, fresh reference verifier and desktop/narrow browser QA |

## Evidence and interpretation

The study uses two development and six new evaluation configurations: 34 trials,
with 30 evaluation trials. Nominal 90% center intervals achieve 81.22% current
prior coverage, 70.89% posterior coverage, 85.73% 250-ft coverage and 83.96% 500-ft
coverage in the predefined cases. These are descriptive point-coverage outcomes,
not calibrated population statements. The bias trial with seed7001 covers only
3/101 posterior stations despite healthy ESS and zero conflict flags. That result
is preserved and shown prominently, with no parameter tuning.

Repeated execution after a figure-layout correction reproduces every numerical
summary value and both compressed event/scoring histories exactly. This is a
reproduction check, not new independent confirmation. The final frozen study
source and all 113 artifacts are verified independently from the later UI source.

## Executed checks

The full suite passed **303 tests in 499.43 seconds** on CPython 3.12.11, without
provenance bypasses. Ruff and `git diff --check` passed. Wheel and source builds
succeeded. An isolated wheel installation imported the new page/engine, verified
all 100 Python source files, and independently loaded both the 34-trial
uncertainty and unchanged 132-trial robustness evidence bundles. A fresh original
reference build passed the saved-project verifier, retaining its earlier
38.0716208% HOLD / 97.1742657% guided outcomes. Final source fingerprint:
`fbf7bf4fab4bcb0e87533a8d9a0829c53df7a04b75c2db337ec02e9761158a91`.

Actual local Chrome controls created an opted-in 256-member causal run, displayed
the acquired start snapshot, assessed commands and downloaded the exact saved
snapshot. A BUILD submission updated it from MD2000 to MD2100, while snapshot0
remained byte-identical. Historical review switched the ensemble from step1 at
MD2100 before decision2 to step2 at MD2200 after the interval. The UI fork test
waited for the selected child identity before submitting its next command; all
37 original parent files stayed unchanged and all three copied ensemble prefix
snapshots were byte-identical. The child independently advanced to step3/MD2300.

Visual acceptance used 1440×1000, 900×900 and 390×844 viewports. Current interval,
model count, probability, ensemble curves, shared-draw command table, historical
controls and calibration failure display were inspected. Narrow document/main
widths stayed at390px with no outer horizontal overflow, and forecast legends
remained clear of axes. The final browser session had zero console errors and
warnings. Physical mobile devices and other browsers were not tested. Existing
PDFs retain the manual-interpretation contract; ensemble-specific exports are
the explicit JSON/CSV downloads and the separate study evidence.

Review added a regression where a5.1% posterior tail spans100ft: current headline
statistics use the exact saved weighted posterior, not its forecast-only
Monte Carlo replication. Forecast-only resampling preserves future process
spread at ESS1 without rewriting current weights. Neither correction changes
the frozen model parameters or uses evaluation coverage for tuning.

Logs and fixtures use `output/verification-gs05-2026-11-08/`; UI captures and
downloads use `output/playwright/gs05-*`. These paths are intentionally ignored.
The versioned study is under `case_studies/uncertainty_v1/`. No commit, push or
deployment was performed.

Suggested repository rule from review: use exact saved weights for current
posterior statistics, and keep forecast-replication approximations separately
labeled. UI tests should wait for a visibly selected child run before issuing
the next command. No AGENTS.md was changed.
