# Local release commit scope and next gate

Prepared November 1, 2026. This change records the existing release prerequisites
and GS-01/GS-02 backend validation in a coherent local checkout. No push,
publication, source visibility change, browser action or paid call is included.

## Included scope

The source changes combine the existing 0.2.0 release prerequisites with the
new workflow controls: exact packaged-source provenance, dependency locks,
portable captured-truth paths, stable tiny-angle minimum-curvature arithmetic,
report heading layout, read-only release/export verifiers and abrupt-process
recovery regressions. The package metadata, manifests and related release tests
are included because the case-study and input snapshot services import those
release modules directly. Uncommitted unrelated work is not discarded.

`reports/portfolio-evidence-2026-11-01/` is the original compact GS-01 packet.
`reports/gs02-compact-evidence-2026-11-01/` is a compact copy of the newer executed
backend validation: the fresh report, all seven figures, summary, immutable
replay decisions, run/input manifest, relevant proofs and sanitized JUnit cases.
Both packets have complete SHA-256 manifests. The full generated run/test
workspaces, caches, raw field data, environments, wheels and source archives
are deliberately not committed. The full local GS-02 workspace remains intact.

## Byte identity and historical provenance

Historical results retain base ancestry
`14ffc90dfd547cfc1217d1ce3a059b4928639dc2`, a dirty-source flag, and exact tested
Python fingerprint
`fb22d15aaf2b509230b2edf927c29cd43466c0f56c361e5659dd94cf59cbc2a0`.
Creating a later commit does not retroactively make those results a test of a
pristine new commit. The verification harness hashes are separately recorded.

The tested snapshot contains both CRLF and LF source files. Git's automatic
newline conversion would otherwise change exact bytes on clean checkout and
invalidate the frozen provenance manifest. `.gitattributes` therefore preserves
the app/tools Python and evidence bytes explicitly. Existing unchanged modules
have line-ending-only Git deltas; inspect semantic source changes with
`git diff --ignore-space-at-eol`. This preserves the tested bytes rather than
silently regenerating a different source identity. Intentional CRLF is allowed
by the matching whitespace attributes; ordinary trailing whitespace is still
checked. Both staged checkouts (`core.autocrlf=true` and `false`) were checked
against all 77 frozen source hashes.

The local build also produced a wheel containing those same 77 exact Python
files and source manifest. Its source distribution excludes raw Volve data,
credentials, environments, caches and generated outputs. Build products stay
outside the commit. Lint, tests, staged whitespace/size/path checks and artifact
hash checks are required before the local commit; their actual outcomes are
reported with the commit handoff.

## Next bounded local release gap

GS-02 still lacks an established duplicate-submit/idempotency contract.
`advance_run` has no expected run/step or request identity parameter; transaction
recovery alone cannot show that a repeated UI event produces one intended action.
The next local work package should first define and test a backend request
contract, without opening a browser or adding sensor research.

Proposed affected files are `app/services/runs.py`,
`app/services/run_transactions.py`, the persisted run state/schema, current CLI
call sites and `app/pages/steering_console.py`, with targeted service tests.
A request should identify its intended run, acquired step and unique request;
repeating the same committed request should return its prior result, while a
stale/different step or run fails before writes. Persistence must retain request
identity across interruption and reopening. Existing numerical reference and
immutable-history semantics must remain unchanged.

Verification should cover repeated request before/after process restart,
interruption before/after commit, stale step, changed active-run pointer,
different payload under a reused request identity, and unchanged parent/fork
history. Compatibility with existing CLI/service callers needs an explicit
decision before coding. UI/browser duplicate-button behavior would remain
unverified until separately authorized; a passing backend test is not that UI
result. No optional sensor profile or robustness research is part of this step.
