# GS-02 selected-run operator and report bridge

Prepared November 1, 2026. The actual form handlers now have executable non-UI
acceptance coverage. Browser/Streamlit widget behavior remains unverified.

## Root causes and bounded change

The steering page previously read configuration, state, interpretation, frames,
metrics and evaluation through the mutable project active-run pointer at
different points. Its guarded advance could therefore be assembled from a
different run's displayed data. Report selections also lacked per-run widget
namespaces, and completed-but-unevaluated reports incorrectly described
themselves as partial and waiting for completion.

`app/services/operator_workflow.py` contains the actual functions imported and
called by the steering/report pages. `load_operator_view` reads one explicit
run's config, acquired state, interpretation, frames and metrics. Same-process
views/exports share the existing per-run access lock with advances, preventing
a view/report from observing a half-written advance. This is cooperative
in-process serialization, not multi-process locking or general snapshot
isolation against arbitrary external writers.

`submit_steering` binds the displayed run, acquired step and historical
interpretation version. An edited retry reconstructs its controls from that
same captured version instead of whichever interpretation is newest later.
The existing durable request guard remains the persistence boundary. A late
acknowledgment is not assigned over current application state; the source page
requests a rerender and reloads the explicit selected view.

Steering now selects an explicit saved run. Initialization/fork selection is
deferred to the next render before assigning the selector key. Steering-to-report
navigation carries the selected run and project. Report run/plan/well/step
controls have project/run-specific keys. The report handler requires an explicit
saved run; legacy CLI report export remains available separately. Completed
reports without saved independent evaluation now state that the selected run's
final truth-scored performance is unavailable, while incomplete reports retain
their partial/estimated-only language.

Local PDF review also found that a single recorded decision produced an empty
step-line timeline. A point marker now makes that actual decision visible.
No scientific inputs, metrics, policy, sensor model or original reports were
changed for presentation.

## Executable acceptance and observed results

The new driver calls the same handlers imported by the pages, through a current
installed backend. It does not emulate widgets, synthesize UI events, run
Streamlit or open a browser:

```powershell
python <checkout>/scripts/verify_operator_workflow.py --out new-handler-acceptance
```

Run it outside the checkout with the current installed wheel. It refuses an
existing output. The real service chain is:

1. Existing seed-123 bootstrap and offset-derived landing/interpretation.
2. Explicit acquired view and an edited form submitted to guarded persistence.
3. Partial report with no final withheld-truth score.
4. Completion over the full 5,000-ft reference domain, followed by an explicitly
   completed-but-unevaluated report.
5. A separate active run, a late retry of the original edited form, and no
   changes to any of 122 saved project file hashes.
6. Actual independent retrospective evaluation of the selected completed replay,
   selected-run report export, project relocation and fresh-process reopen/export.

This bridge uses two manual HOLD requests to reveal a fixed recorded path. It
is application integration evidence, not a new guided-policy performance study.
The source pages call these tested handlers, but actual widget event delivery,
navigation and duplicate-button behavior remain separate unrun checks.

On the final source, all **16 targeted checks** passed: seven new handler/view
cases plus nine relevant existing concurrency, plan-pinning, marker-freeze,
partial-report and explicit report-selection controls. Zero failures/errors/
skips were recorded. The prior 129-test suite is historical to 0.2.1 and was
not rerun unchanged for this bounded application/report delta.

The final installed-source probe matches all 78 packaged Python files to the
checkout/wheel and re-attests 61 locked dependency distributions. A separate
local runtime reuses those dependencies; this is not a fresh independent clean
installation. The final wheel/source-distribution build and Ruff passed.

A fresh installed final-source seed-123 reference passed the existing read-only
release verifier. Its entire numerical summary is byte-identical to the prior
reference, SHA-256
`be1028dc40bde6feebdfa8696e58679c7a31ffcb81dc6a86a6be70a28a90333a`.
The known signed synthetic GR calibration, single 2D scenario/seed and 5,000-ft
denominator still limit the scientific claim.

## Local PDF artifact review

Following the PDF skill, Poppler rendered all pages at 110 dpi. Every resulting
local page image was individually inspected without any browser/app operation:

| Acceptance report | Pages | Embedded figures | Observed result |
| --- | ---: | ---: | --- |
| Partial | 4 | 6 | Estimated-only evaluation statement; visible single HOLD point |
| Complete, unevaluated | 4 | 6 | Complete status and explicit missing selected-run evaluation |
| Complete, evaluated | 5 | 6 | Actual saved retrospective metrics and scientific limitations |

All 13 pages had readable text, table cells, chart axes/legends and footers,
without observed clipping, overlaps or missing glyphs. Poppler emitted fallback
display-font messages, but the inspected content rendered legibly. These manual
workflow reports omit the separate causal-comparison figure because the driver
does not run that comparison. The ordinary fresh reference separately passed
its seven-figure verifier; its entire PDF was not visually reviewed here.

The three final acceptance PDF hashes are recorded in the driver proof and
`pdf-artifact-qa.json`, together with all rendered page hashes. No original
packet or original PDF was overwritten.

## Identity, commands and retained evidence

This is the new 0.2.2 dirty snapshot based on
`9985f5dea635c53dac8fdab1ac579b73b1ecdf66`, source fingerprint
`a4efbdb1e90db4aad0c187a65555f07733ef65234cf58be2215cae42dbac8c87`.
Historical 0.2.0/0.2.1 source identities remain unchanged. A later local commit
does not relabel these pre-commit records as a pristine-commit test.

```powershell
python -m ruff check app tools tests scripts app.py
python -m pytest tests/test_operator_workflow.py
python -m pytest tests/test_step_idempotency.py::test_overlapping_same_process_retries_append_only_one_step tests/test_report_plan_pinning.py tests/test_report_marker_freeze.py tests/test_report_scientific_content.py::test_report_uses_selected_runs_active_well_and_reveal_bound tests/test_report_scientific_content.py::test_midrun_report_withholds_truth_and_applies_selection
python -m tools.run_case_study --out new-reference --seed 123
python -m tools.release_verify new-reference/project --require-packaged --write new-reference-proof.json
```

The installed gate must run outside the checkout. Raw outputs and proofs remain
local under `output/gs02-operator-workflow-2026-11-01/`, especially
`final-handler-acceptance/proof.json`, `final-installed-source-proof.json`,
`final-fresh-verification.json`, `numeric-reference-comparison.json` and
`pdf-artifact-qa.json`. Final JUnit records are
`output/final-operator-workflow-tests.xml` and
`output/final-operator-regression-tests.xml`. Build/runtime/workspace/PDF/PNG
outputs stay outside the source commit.

No browser/Streamlit interaction, multi-process writer test, container work,
deployment, publication, paid call, sensor research or robustness study occurred
in this delta. GS-02's interactive acceptance remains open. Rollback is the
bounded handler/page/report delta plus its source manifest/version; preserve
every existing run, receipt and historical evidence packet.
