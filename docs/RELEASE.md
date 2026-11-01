# GeoSteering 0.2.0 release

This is a local synthetic training and research workbench. The supported release
is the `structural_dip_01-v1` seed-123 scenario, LAS/survey ingestion, constrained
planning, interpretation replay, bounded causal comparison, local persistence,
and JSON/CSV/PNG/PDF export. Browser interaction is unverified. Volve field data
is retained separately and is excluded from the release evidence archive.

## Install the frozen environment

Use CPython 3.12. The release contains platform-specific, hash-checked locks,
including patched pip, setuptools and wheel bootstrap tools. Python 3.10 is not
supported by the patched Pillow and current Streamlit versions. The source package requires
Python 3.11 or newer; the release locks and verification target Python 3.12.
The verified installer is the free `uv` CLI. From a new directory with the
downloaded release files and CPython 3.12 available:

```powershell
python -m venv --without-pip .venv
uv pip sync --python .venv/Scripts/python.exe --require-hashes --only-binary :all: requirements-release-windows.lock
uv pip install --python .venv/Scripts/python.exe --no-deps dist/geosteering_workbench-0.2.0-py3-none-any.whl
.venv\Scripts\python -m pip check
.venv\Scripts\python -m tools.run_case_study --out my-case --seed 123
.venv\Scripts\python -m tools.release_verify my-case/project --require-packaged --write my-proof.json
```

On Linux use `.venv/bin/python` and `requirements-release-linux.lock`. The Linux
lock is supplied for reproducibility; the evidence record states which platform
was actually executed. Choose unused output paths. No credentials or paid API is
needed. `--require-packaged` must run outside a source Git checkout.

The security repair preserves numerical dependencies where compatible, raises
Pillow to 13 and pypdf to 6.21.4, and uses Streamlit 1.66.1 because the older
Streamlit constrained Pillow below its patched version. Streamlit's obsolete
GitPython/Tornado dependency chain is no longer installed. The lock also fixes
certificate, HTTP, test and bootstrap package advisories. Actual audit JSON
records distinguish all third-party distributions from the local unpublished
project, which cannot be looked up in the PyPI vulnerability feed.

The PDF and exports are in `my-case/project/exports`. `artifacts.json` identifies
the exact run, plan, report and figures. Reopen a saved or relocated project by
passing that project's root to `tools.release_verify` or `tools.export_report`.
Captured truth paths are relative to their owning run; reopening must not read
the original copy's environment. Explicit run and plan selection is supported by
`python -m tools.export_report --help`.

## Source and build identity

The wheel includes `app/_release_source.json`, containing hashes of every Python
module under `app` and `tools`. Runtime verification checks those exact bytes.
A dirty source snapshot records its base Git revision and dirty status; that
revision does not imply the snapshot equals the committed tree. Installed wheels
report absent runtime Git as unknown, while retaining verified build provenance.

To build a new source snapshot, regenerate its manifest after all source edits:

```powershell
python -m tools.release_provenance --write
python -m ruff check app tools tests app.py
python -m pytest
python -m build --outdir output/release-dist
```

Changing packaged source without regenerating the manifest fails provenance
validation. The archive has a complete SHA-256 file manifest. The owner release
contains source, wheel, source distribution, locks, current run and independent
verification. Real-well data, environments, caches and credentials are excluded.

## Meaning of the results

HOLD and observation-guided runs share fixed geology, seed, landing state and a
5,000-ft lateral denominator. Their in-zone results are approximately 38.1% and
97.2%, with zero violations of the separate 3 degrees/100 ft lateral DLS bound.
Landing uses a distinct 6 degrees/100 ft bound. Exact values are checked against
frozen references, and the report binds values to its run and plan.

The operator receives a known signed synthetic GR calibration. That assumption,
one idealized 2D scenario, sensor saturation, simplified kinematics and assumed
uncertainty limit the interpretation. The replay path is fixed: recommendations
do not change placement. The comparison is a software experiment, not evidence
of operational drilling performance. Independent numerical tolerances describe
ideal arithmetic, not survey accuracy. See `methods.md` and `limitations.md`.
