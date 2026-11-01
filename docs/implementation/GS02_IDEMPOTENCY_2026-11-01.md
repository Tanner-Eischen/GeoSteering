# GS-02 guarded advance requests

Prepared November 1, 2026. This is a bounded backend persistence change for the
0.2.1 source snapshot. It does not establish browser behavior, multi-process
locking, operational drilling performance or a published release.

## Contract and compatibility

`advance_run` now accepts three optional keyword-only guards. Supply all three
for the durable contract:

```python
result = advance_run(
    project_root, "HOLD", "Acquired log supports current inclination",
    run_id=selected_run_id,
    expected_step_index=observed_step,
    request_id="caller-generated-stable-request-id",
)
```

The selected run is explicit and may differ from the project's active pointer.
Every service call inside the operation resolves that selected run through a
scoped context. `active_run.json` is never switched to perform the advance.
The stored config/state must agree with the requested run identity. Missing or
invalid run selection fails without advancing another run.

The acquired step must be a nonnegative Python integer; booleans and fractional
values, including integral floats, are rejected. Request IDs contain 1-128
ASCII letters/digits or `_.:-`, beginning with a letter/digit. Supplying only
some guards is an error. Legacy calls supplying none retain their previous
single-writer behavior and do not acquire an idempotency guarantee implicitly.

New guarded requests compare the expected step with the persisted current step
before writes. A successful request appends one receipt to the selected run's
`step_requests.json`: request identity, expected step, canonical command-payload
SHA-256 and the exact returned `SimulationState`. All command fields, including
evidence, rationale, interpretation controls and requested inclination, bind the
payload. Changing a payload or expected step under an existing identity fails
before command writes.

A retry with the same identity/step/payload returns the original receipt. It
does not re-evaluate the command or return the current state in place of the
original acknowledgment. This remains true after later steps, completion,
marker edits, active-run changes and process restart. Reload the selected run
explicitly when the latest state is needed. Request identities are per run;
forks preserve acquired history but start a new request namespace. Parent
receipts and documents are not altered.

Receipts are included in the existing recoverable step journal. An interruption
before the commit marker restores both history and receipts. After the durable
commit marker, reopening retains both. A per-run in-process lock serializes
overlapping guarded/legacy advances in one process. Cross-process/multi-writer
locking, concurrent-reader snapshot isolation and power-loss durability are
not claimed; this remains a local single-writer workbench. Recovery may first
restore a previous interrupted transaction before validating a new request.

## Call sites and affected files

The case-study CLI now provides an explicit run, observed step and stable
request identity for every interval. The steering form uses a run/step-specific
form key and passes the same guards. These are source changes only: no browser,
Streamlit interaction or duplicate-button experiment was performed.

Affected code is `app/services/run_paths.py`,
`app/services/run_transactions.py`, `app/services/runs.py`,
`app/pages/steering_console.py` and `tools/run_case_study.py`.
No scientific observation model, geology, policy, numeric scoring or existing
history format was changed. The optional new receipt document needs no migration
for legacy runs. Existing pending journal records remain readable.

## New source identity and validation

The current snapshot is version 0.2.1, based on commit
`830a84ea00cf29fb344312c3322679af05eb9e27` plus this new dirty delta, with source
fingerprint
`9f96eaa8a2848fb86685adc76b69c1db7e91ec8cededb983ad7de4e6b4923621`.
Its frozen source manifest is new. Original 0.2.0 packets and fingerprints remain
historical and unchanged; a later commit does not retrospectively make these
pre-commit results a pristine-commit test.

A new local 0.2.1 wheel was built and installed into a separate temporary
runtime. That runtime reuses the previous environment's 61 locked dependency
distributions; it is not an independent clean installation. The new installed
wheel and current checkout match all 77 packaged Python files and the manifest.
The original 0.2.0 runtime was not modified.

Twenty new tests cover replay/causal retries after later steps and marker/active
pointer edits; boolean/fractional/negative step rejection; conflicting action,
evidence, inclination and rationale; partial guards and stale steps; explicit
non-active target; overlapping same-process retries; fork namespace separation;
legacy calls; and four receipt/commit-marker process-exit/restart cases. Together
with existing history/transaction controls, all 31 targeted tests passed.
The complete suite then passed 129 tests with zero failures, errors or skips
in 303.109 seconds. Lint and the local wheel/source-distribution build passed.

The fresh installed guarded seed-123 case persisted 100 unique receipts. Its
complete numerical summary equals the prior 0.2.0 reference byte-for-byte:
`be1028dc40bde6feebdfa8696e58679c7a31ffcb81dc6a86a6be70a28a90333a`.
The same single synthetic scenario, signed calibrated sensor and 5,000-ft
denominator still apply; this is not a new scientific-performance claim.
The installed read-only release verifier passed its history, PDF, provenance,
frozen-reference and analytic-control checks.

After completing all 100 intervals, retrying the first exact CLI request returned
its original step-1/incomplete acknowledgment. All 69 saved project file hashes
remained unchanged. Raw reproduction, build/install, targeted/full test and
comparison records are kept locally under
`output/gs02-idempotency-2026-11-01/`; generated workspaces and environments are
excluded from the source commit. Original packet checksums were checked again
without changing their provenance or content.

## Reproduction and rollback

Install the current source with its test/dev dependencies, freeze its source
manifest after source edits, and run:

```powershell
python -m ruff check app tools tests scripts app.py
python -m pytest
python -m build --no-isolation --outdir output/new-guarded-dist
python -m tools.run_case_study --out output/new-guarded-reference --seed 123
python -m tools.release_verify output/new-guarded-reference/project --write output/new-guarded-proof.json
```

Use an installed wheel outside the checkout plus `--require-packaged` for the
installed-source gate. The tests' subprocess checks also require that the same
current application source is installed in the interpreter being tested.
Do not point a new run at an old populated output directory.

Rollback the new source and release manifest together, retaining every existing
history and receipt document. Older code ignores the new receipt file and does
not provide guarded retry behavior. Do not remove receipts to force an existing
request to execute again. Browser/operator acceptance and publication remain
open; no sensor research, paid call or external action occurred.
