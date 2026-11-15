# Interpretation handoff, command preview and robustness study

November 7, 2026. Local implementation and acceptance record.

## Scope and acceptance inventory

The implementation preserves the selected offset interpretation through correlation,
planning and run initialization; previews bounded command geometry without acquiring
future measurements; and exposes a frozen paired synthetic robustness study.

| Requirement | Functional check | Visual state / evidence |
| --- | --- | --- |
| Selected offset model survives handoff | Save a subset, select its model, save a plan, start its run; compare model hashes | Correlation success, selected plan card, run starting-geology card |
| Evidence changes require deliberate refresh | Change an offset pick; new plan/run rejects stale evidence; saved histories remain unchanged | Actionable changed-evidence message |
| Preview changes before advancement | HOLD/BUILD/DROP, custom target, clipping and contradictory target | Requested/effective inclination, projected station and DLS |
| Preview remains read-only | Hash complete run before/after previews; forbid private scenario and sampler calls | No step/reveal change until evidence is submitted |
| Commit agrees with preview | Compare projected station/response with committed station | Next-step progress and acquired geometry |
| Fixed replay remains distinct | Replay recommendation preview | Explicit fixed-path explanation; no future geometry |
| Held-out study is inspectable | Split switch, configuration selection, downloads and artifact hashes | Paired chart, failure figure, methods/limits and per-case table |
| Layout remains usable | Desktop, half-width and narrow viewport; keyboard traversal | Screenshots and overflow/console checks |
| Reproduction remains intact | Full suite, lint, build, reference CLI, saved-project verifier, study rerun | Command logs, numerical comparisons, PDF/PNG inspection |

Off-path checks include incompatible command targets, missing required evidence,
stale model evidence, selected older models/runs, and a saturated-sensor study failure.

## Scientific scope

The original seed-123 reference remains a separate single-scenario demonstration.
The new study freezes two development controls and eight evaluation configurations,
uses disjoint development/evaluation seeds, and compares three causal strategies.
Evaluation cases are held out from controller development; after execution their
results are available evidence and are not a fresh holdout for future tuning.

The guided controller is unchanged; a disclosed fixed validity wrapper excludes
missing/saturated observations, retains delayed acquisition coordinates, and uses
HOLD when no new usable measurement arrives. Comparisons are descriptive for
handpicked synthetic cases. Seed ranges do not measure uncertainty over geology.

## Verification

The initial full suite passed 192 tests on CPython 3.12.11. Review then added
regressions for legacy causal advancement, target-widget persistence, and
piecewise boundary rendering; all 11 targeted preview/workspace checks passed.
The full suite then passed **196 tests in 341.48 seconds**. A final narrow-chart
spacing adjustment and distinction between genuinely legacy metadata and missing
modern metadata were followed by **12 passing focused checks in 27.85 seconds**.
The full-suite and final-focused source identities are retained separately in
the task-local logs. Ruff and `git diff --check` pass on the final source.

Actual local Chrome controls exercised the two-offset model handoff, plan save,
causal initialization, HOLD/BUILD/DROP and inclination targets, rejected
contradictory targets, required evidence, and one committed step. All 24 run files
were byte-identical through read-only previews and rejected submissions. The
committed DROP station matched the preview (MD 2100 ft, inclination 87 degrees)
and the plan/run model hashes agreed. Changing one synthetic offset Top_A pick
by 0.1 ft displayed the stale-evidence message and disabled new initialization;
the existing run retained the original picks. The test input was restored.

The study page was exercised through both split selections, configuration
selection, methods disclosure and four actual downloads. CSV, JSON and frozen
source ZIP downloads matched bundled artifacts byte for byte. Visual checks use
1440×1000, 900×900 and 390×844 viewports; half-width columns wrap to prevent metric
truncation. Narrow command inputs preserve targets when HOLD is selected and
then deselected. The app's hidden outer container remains at scrollTop zero,
and narrow document/main scroll widths equal the viewport width.

The independent saved-project verifier passed on a fresh reference build. Its
13-page PDF contains seven embedded figures; all pages were rendered and their
overall layouts inspected. The original causal results remain 38.0716208% HOLD
and 97.1742657% guided. A clean Python 3.12 wheel installation independently
loaded and verified all bundled study evidence, including the source archive,
without importing this checkout.

The complete 132-trial robustness study was also rerun under supported CPython
3.12.11. Every numerical summary value matched the published packet exactly
(the source fingerprint differs because app presentation changed). This is
reproduction of the same observed study, not another independent holdout. An
independent review additionally rescored all 132 archived trajectories with zero
metric mismatches and rebuilt the summary exactly from the event histories.

Final wheel and source builds succeeded after the last source changes. The
final wheel was reinstalled into an isolated environment and its executable
source hashes and all study artifacts verified. The fresh final reference
build passed the saved-project verifier under the same source fingerprint:
`9a2a4fb194e624b63d7af4eb873929b33e610e13c66d924444084fe2f8dfb542`.
The actual Chrome console had zero errors and warnings in the final session.
This is local Windows/Chrome acceptance, not other-device/browser certification.

Task-local evidence and command logs are under `output/verification-2026-11-07/`;
browser captures/downloads are under `output/playwright/increment-*`. These paths
are intentionally ignored. The versioned study has its own frozen source,
artifact index, histories, protocol and numerical results in
`case_studies/robustness_v1/`.

## Proposed AGENTS.md additions from review

These are draft repository rules; no AGENTS.md was created or modified:

- Optional previews must preserve legacy execution. Distinguish unavailable
  historical metadata from corrupt metadata; fail closed only for the latter.
- Geological plots must include the interior knots of piecewise interpretations,
  so the displayed boundary matches the model used for scoring.
- Keep command widgets rendered while disabled to preserve user-entered values
  across reversible mode changes. Check this with real controls and component tests.
- Verify frozen executable evidence as well as result files before labeling an
  experiment packet complete, including the installed-package resource path.
