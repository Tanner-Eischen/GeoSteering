# Decision review, branch comparison and evaluation

November 7, 2026. Local implementation and acceptance record.

## Scope and information contract

Decision Review reconstructs a saved command in two phases. At decision n,
observations stop at its starting MD and persisted metrics stop at n−1. The
applied interpretation and its previous version are shown separately. After
interval n, the view adds acquired observations and the original metric n.
Current marker edits, later interpretations, risk-note sensor payloads and
retrospective truth scores are not substituted into historical views.

Run Comparison accepts related fork branches of the same frozen experiment.
It checks configuration, observed input fingerprints, initial model, mechanical
limits, captured field identity, code identity and shared acquired prefix.
Both paths and logs stop at their common recorded MD station. Estimates come
from each branch's persisted snapshot at that endpoint; no missing estimate is
filled in using a later interpretation. Both runs must complete before explicit
independent truth comparison. Differences are right minus left and use the same
lateral denominator, including the shared prefix.

Evaluation keeps independent scores sealed until completion and explicit
evaluation. Saved scores are checked against the selected completed run before
display. Placement, interpretation error and DLS have distinct labels. The DLS
chart uses the evaluator's scenario scoring bound; a stricter causal command
bound is disclosed separately. Fixed replay recommendations do not change the
recorded path. Interpretation errors remain station-averaged as in the existing
independent evaluator.

## Acceptance inventory

| Requirement | Functional verification | UI evidence |
| --- | --- | --- |
| Historical information boundary | Poison later logs/models/metrics; assert clipped selected payload and no truth reads | At-decision and after-interval phases show different endpoints |
| Historical immutability | Hash files before/after review; change current picks and advance other runs | Original rationale, evidence, model and prefix downloads |
| Branch pairing | Reject incompatible fields/configurations/models/ancestry; preserve parent history | Run families and explicit left/right selectors |
| Common acquired horizon | Advance one branch farther; clip both to common recorded station | Common MD and lateral denominator, overlaid paths/logs |
| Completed comparison gate | Completed versus unfinished branch exposes no truth data | Disabled evaluation until both finish |
| Selected-run navigation | Navigate from a second fork family and switch manual selectors | Shortcuts retain the chosen run/family |
| Independent evaluation | Partial/unevaluated/cached/corrupt result cases | Placement plot, error table, lateral DLS and report navigation |
| Local UI quality | Desktop, half-width, narrow layout and keyboard checks | Reviewed screenshots, downloads and console checks |

Off-path cases include corrupted saved outcomes, contradictory comparison
selection, modified frozen inputs, differing scoring intervals, incomplete survey
intervals, multiple fork families and missing historical records.

## Validation

The final full suite passed **242 tests in 389.20 seconds** on CPython 3.12.11.
Ruff and `git diff --check` passed. Wheel and source builds succeeded, and an
isolated wheel installation imported all three new pages, verified its 91 Python
source files and loaded the complete existing 132-trial study. The fresh
seed-123 reference rebuilt and passed the independent saved-project verifier;
its scientific outcomes remain unchanged. The final source fingerprint is
`e509722ba5caf08801db773cb60f3cb7b45a0b0f5494fceb69421310942ab1ed`.

Actual local Chrome controls exercised the complete new workflow using a
separate short synthetic acceptance fixture, not a new scientific benchmark:

- Step 2 switched from MD 2100 and metric 1 at decision time to MD 2200 and
  metric 2 after the interval. After that run completed at MD 2600, its downloaded
  Step 2 decision-time CSV still ended at MD 2100.
- A completed parent versus an unfinished child clipped both downloaded paths
  and logs to MD 2200 and a common 200-ft lateral denominator. Independent
  comparison remained disabled, including after the parent's separate evaluation
  had been saved.
- Four actual steering submissions completed the child. Paired evaluation then
  used 600 ft for both runs. The fixture returned 100% parent and 69.8836777%
  child in zone, with the displayed right-minus-left difference −30.1163223 pp.
  These numbers verify the workflow only; they do not extend the study results.
- The selected child remained selected through Evaluation → Report Export.
  Its actual PDF download contained its run ID and independent score (five pages,
  six embedded figures). All 32 original parent files remained byte-identical;
  explicitly requested evaluations added separate result artifacts.
- Desktop, half-width and narrow checks used 1440×1000, 900×900 and 390×844
  viewports. Metric cards remained readable, legends did not overlap axes and
  document/main widths stayed within their viewports. Final browser console:
  zero errors and zero warnings.

Review corrected selected-family navigation, aligned the DLS scoring line with
the evaluator contract, and removed a spurious missing-file warning for a normal
completed-but-unevaluated run. Regressions cover all three cases. Validation is
limited to the local Windows/Chrome profile; physical mobile devices and other
browsers were not tested. No commit, push or deployment was performed.

Task-local logs and fixtures are under `output/verification-gs04-2026-11-07/`;
browser captures and downloads use `output/playwright/gs04-*`.

## Proposed repository rules and workflow

No AGENTS.md was created or modified. Suggested additions from review:

- Pass explicit selected-run context when navigating to multi-run views;
  preserve manual comparison selections on ordinary reruns.
- Label scoring thresholds separately from command bounds when their contracts
  differ; a plotted bound must match the reported violation count.
- `read_json(..., default=None)` does not treat a missing file as an empty
  optional result. Check existence when missing is a normal workflow state.

This repeats the source-freeze, test, build, artifact and UI acceptance sequence
from GS03. A reusable local acceptance command/skill would reduce repeated setup
while retaining explicit snapshot identities and browser evidence. None was
installed or scheduled as part of this increment.
