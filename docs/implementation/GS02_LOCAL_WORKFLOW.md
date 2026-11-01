# GS-01/GS-02 backend release validation

Prepared November 1, 2026. Non-UI validation completed in the new, local-only
`reports/gs02-local-workflow-2026-11-01/` directory. GS-02's interactive acceptance
remains open. No source/data/old evidence was changed and nothing was published.

## Plan and affected files

Reuse the existing installed `tools.run_case_study`, `tools.release_verify`,
`tools.release_install_probe` and `tools.export_report` drivers. Avoid another
simulator. Add a small read-only midpoint scoring witness in
`scripts/verify_guided_workflow.py` and eleven abrupt-process recovery tests in
`tests/test_guided_workflow_resilience.py`. Keep every reproduction, mutation
fixture, log and proof in a new versioned output directory. Existing app/tools
source, data, release locks, dirty work and the earlier GS-01 packet are preserved.

Main risks were accidentally importing the checkout rather than the installed
wheel, confusing replay history with causal steering, leaking current marker
edits into older reports, and mistaking a recoverable exception for actual
process-interruption recovery. The checks below address those boundaries.

## Actual results and provenance

Used the existing noneditable 0.2.0 wheel in the patched Windows CPython 3.12.14
environment. The new `installed-source-proof.json` confirms all 77 installed
app/tools Python files match the current checkout and wheel; all 61 locked
distributions match and `pip check` passes. This re-attests an existing installed
environment, not a fresh installation.

Base source ancestry is `14ffc90dfd547cfc1217d1ce3a059b4928639dc2`; exact tested
dirty snapshot fingerprint is
`fb22d15aaf2b509230b2edf927c29cd43466c0f56c361e5659dd94cf59cbc2a0`.
There is no new result commit. Installed runtime Git is absent, as expected.
The test/witness harness is separate from the unchanged packaged app/tools and
has its own hashes in `execution-summary.json`.

Two fresh installed-driver executions of `structural_dip_01-v1`, seed 123,
produced identical numerical summaries, including all 100 historical replay
rows. Summary SHA-256 is
`be1028dc40bde6feebdfa8696e58679c7a31ffcb81dc6a86a6be70a28a90333a`.
The results also equal the previous release's causal metrics exactly:

| Synthetic causal result | HOLD | Guided |
| --- | ---: | ---: |
| In-zone percentage | 38.07162079659706% | 97.17426567844367% |
| In-zone length | 1903.5810398298531 ft | 4858.713283922184 ft |
| Evaluated lateral length | 5000 ft | 5000 ft |
| Mean center distance | 27.52464829587919 ft | 1.074120655634311 ft |
| Lateral DLS violations | 0 | 0 |

The evaluated MD interval is 2,000-7,000 ft. Lateral DLS is 3 degrees/100 ft;
landing uses a separate 6 degrees/100 ft limit. The guided strategy knows a
signed GR calibration (80 API center, 2 API/ft gradient, 0.6 API Gaussian noise,
clipping at 20-160 API). One idealized 2D scenario and one seed do not establish
generalization, operational drilling fitness, real-field performance or a
statistically calibrated uncertainty interval.

The fresh report contains **13 pages and seven actual figures**. It differs
from the earlier 14-page owner report in metadata/layout; PDF byte equality is
not a reproduction gate. Fresh PDF SHA-256 is
`9dc340594f8dff06ced868f90817536d49efac6eac4b67e5fab85b0de2cf4819`.
Fresh run ID is `a9991c26-cbd2-4f35-a1b0-966157b083b4`; plan ID is
`615d5570-b6fa-4bde-9d58-fe08707407b0`.

## Checks executed

- Existing saved-case verifier passed for both fresh runs. It recomputed
  replay truth evaluation and 600 estimated KPI values, checked 1,500 decision
  CSV fields, 1,001 plan values, all 100 PDF KPI rows, seven embedded images,
  required numerical/method/provenance text, frozen causal references within
  1e-6 percentage points, and analytic geometry/integration controls.
- A separate 0.1-ft midpoint witness sampled each saved causal trajectory at
  50,000 lateral positions. HOLD was 38.072% and guided 97.174%; differences
  from production integration were 0.000379 and -0.000266 percentage points,
  respectively, within the declared 0.01 percentage-point tolerance. Mean
  center distances agreed within 0.01 ft. This witness shares the declared
  geological truth-field function; it is a separate integrator, not independent
  field validation. It also checks 100 decisions per strategy, observation
  depths, contiguous steps, shared landing and stored lateral DLS.
- A fresh process reopened the original project with an identical verifier
  record. Copying it to `relocated-project/` and reopening also returned an
  identical record, without using the original project's truth path.
- In the isolated relocated copy, edited a current offset marker and exported
  via the actual installed CLI with explicit run/plan IDs. The old report kept
  its original markers. All seven figure hashes and four immutable history
  document hashes stayed unchanged; post-export saved-case verification passed.
- **28 existing targeted tests passed**, with zero skips/errors/failures. They
  cover run isolation, immutable metrics, evidence validation, persisted causal
  consequences, forked prefixes, transaction rollback, future/truth isolation,
  marker freezing, pinned/explicit report selection, partial reports withholding
  final truth scores, and four corrupted-export rejection cases.
- **11 new tests passed**, with zero skips/errors/failures. Installed-backend
  child processes exited abruptly after actual interpretation, decision, metric,
  environment and simulation-state writes (nine replay/causal stage cases).
  Reopening restored every prior JSON document byte-for-byte. Two more cases
  exited after the durable commit marker and preserved exactly one step over
  repeated reopening.
- Ruff passed for the new script/tests; `git diff --check` passed. Original
  GS-01 packet and current packaged source hashes were checked again unchanged.

The ordinary history/negative tests run against checkout source. Their installed
counterpart is byte-matched by the new wheel probe. The abrupt-exit child
processes and fresh/reopen/export CLIs run outside the checkout import path
against the installed package. No UI was opened.

## Repeatable commands

Use the installed release environment's Python, run outside the repository,
and choose new output/proof paths:

```powershell
python -m tools.release_install_probe --wheel <release-wheel> --source <checkout> --write installed-source-proof.json
python -m tools.run_case_study --out fresh-reference --seed 123
python -m tools.release_verify fresh-reference/project --require-packaged --write fresh-verification.json
python -m tools.run_case_study --out repeat-reference --seed 123
python -m tools.release_verify repeat-reference/project --require-packaged --write repeat-verification.json
python <checkout>/scripts/verify_guided_workflow.py --project fresh-reference/project --write independent-workflow-verification.json
python -m tools.release_verify fresh-reference/project --require-packaged --write reopened-verification.json
python -m tools.export_report <isolated-project-copy> --run-id <saved-run-id> --plan-id <saved-plan-id> --strict
```

In the checkout, with the same environment:

```powershell
python -m ruff check scripts/verify_guided_workflow.py tests/test_guided_workflow_resilience.py
python -m pytest -q tests/test_run_history.py tests/test_run_transactions.py tests/test_truth_isolation.py tests/test_report_marker_freeze.py tests/test_report_plan_pinning.py tests/test_report_scientific_content.py::test_midrun_report_withholds_truth_and_applies_selection tests/test_report_scientific_content.py::test_report_uses_selected_runs_active_well_and_reveal_bound tests/test_release_evidence.py::test_export_mutants_are_rejected
python -m pytest -q tests/test_guided_workflow_resilience.py
```

Actual executions additionally used unused versioned `--basetemp`, JUnit XML,
cache and log paths, preserved in the output directory. An existing output is
never a valid fresh reproduction target. The complete full-suite run was not
repeated; the 39 tests above are the declared local workflow scope.

## Remaining release gates

Browser/dashboard navigation, human-readable run labels, enabled/disabled UI
guidance, UI stale-state behavior, keyboard interaction, duplicate button
submissions and visual PDF layout have not been exercised. The backend
`advance_run` API has no request-identity/expected-step parameter; a browser
retry/idempotency guarantee cannot be inferred from atomic single-writer
recovery. No concurrency or multi-user guarantee is claimed.

No new clean installation, Linux execution, paid/model call, deployment,
visibility change, signed-out access check or publication occurred. GS-01's
public-evidence gate and GS-02's interactive gate remain open. The portfolio may
upgrade its **local backend reproduction** evidence using these new records,
while keeping published/source-access and browser states explicitly unverified.

Rollback is limited to retaining/removing the newly added witness/tests/docs
and versioned outputs. Existing app/tools, historical metrics and original
packets require no migration or rollback.
