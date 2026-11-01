# GS-01 local evidence handoff

Prepared November 1, 2026. The compact reference packet is ready for owner review
at `reports/portfolio-evidence-2026-11-01/`. It has not been published.

The packet preserves the existing reference rather than rerunning or changing
the simulation. Its synthetic causal comparison is 38.07162079659706% HOLD and
97.17426567844367% guided over the same 5,000-ft lateral, with zero lateral DLS
violations. The signed synthetic GR calibration, one scenario/seed, assumed
uncertainty and lack of field validation accompany these results.

## Identity and contents

- Base source revision: `14ffc90dfd547cfc1217d1ce3a059b4928639dc2`.
- Tested snapshot fingerprint:
  `fb22d15aaf2b509230b2edf927c29cd43466c0f56c361e5659dd94cf59cbc2a0`.
- The snapshot is dirty relative to that revision. There is no result commit;
  the base revision denotes ancestry, not identical tested bytes.
- Scenario: `structural_dip_01-v1`, seed 123, local east/north feet and positive
  downward TVD. Evaluated MD 2,000-7,000 ft; lateral DLS 3 degrees/100 ft, separate
  landing DLS 6 degrees/100 ft.
- Run: `4eb607b4-68a4-48fa-b0ea-8af5a5fb8f30`.
- Plan: `f2de74a6-68cf-48a9-9fb0-1490f423444d`.
- Report SHA-256:
  `01258804d34ae91551fe0834c78fc9a5852e4bf2b745544c20f80a5571a6ef46`.

`portfolio-evidence.json` records claim scope, source lineage, access state,
limitations and asset hashes. `summary.json`, `run-manifest.json`,
`replay-decisions.csv`, `report.pdf`, all seven `figures/*.png`, methods,
limitations and MIT license form the review packet. The decision CSV is the
fixed-path replay history, not the causal guided history. `SHA256SUMS` covers
all 17 other files. No raw Volve files, credentials or local filesystem paths
are included in the public-safe text/PDF assets.

## Verification actually executed

Executed in the existing patched CPython 3.12.14 environment:

```powershell
python -m ruff check scripts/export_portfolio_handoff.py
python scripts/export_portfolio_handoff.py --release <existing-owner-release> --out reports/portfolio-evidence-2026-11-01
```

The exporter called the existing read-only `tools.release_verify` against the
saved release case. Its new result is in `verification.json`: 100 decision rows,
1,500 decision CSV fields, 1,001 plan CSV values, 600 recomputed KPI values,
100 PDF KPI rows, independent analytic geometry/integration controls, and a
14-page PDF containing seven images passed. Saved replay truth evaluation was
recomputed; causal results were checked against saved comparison artifacts and
the frozen reference, rather than newly simulated.

All 269 owner release files and 77 current packaged Python source files passed
hash validation. A separate packet check validated all 17 payload hashes,
metric/length arithmetic, 100 replay rows, PNG headers/dimensions, the manifest
asset hashes, and absence of owner paths in text assets. PDF text path checks
are part of the existing verifier. These checks do not constitute fresh visual
inspection of the PDF or an interactive application walkthrough.

The initial exporter reached its final text check and falsely matched `https:`
as a Windows drive. The drive-pattern boundary was corrected. The already
created packet was then independently checked and its complete SHA-256 manifest
written. Final lint passed. No existing source, report or prior evidence was
overwritten. The exporter refuses any existing output directory.

## Remaining gates and next dependency

Historical owner-release records describe 98 passing tests, Windows clean
installation and earlier PDF visual review. Those checks were not rerun here.
A fresh simulation reproduction, fresh clean install, full suite, Linux run,
browser/operator walkthrough, signed-out source access and publication remain
unexecuted. GS-01's public-access acceptance and GS-02 are therefore open.

PF-02 can use this packet as locally verified, unpublished evidence with the
explicit access limitation. A public base-source link must disclose that the
exact tested dirty snapshot is not yet publicly released. No source visibility
change, commit, push, deployment or paid call occurred.

## Regeneration and rollback

Run the exporter with an existing owner release and a new output directory.
It reuses the existing saved-case verifier and copies an allowlisted set of
synthetic artifacts; no scientific engine or source data changes are involved.
Never overwrite the original reference or reinterpret a previous run under
new assumptions. Retaining or removing this new packet and exporter has no
effect on the original release or application. Existing dirty changes remain
untouched.
