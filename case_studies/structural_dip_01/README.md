# Geosteering under structural uncertainty

Build the complete synthetic case study from the repository root:

```powershell
python -m pip install -e ".[test,dev]"
python -m tools.run_case_study --out data/structural_dip_run_01 --seed 123
```

Choose a new output directory for each build. The command generates four wells, imports and validates observations, estimates the baseline from three offset marker sets, plans a landing and lateral, and completes 100 replay steps. Each recommendation uses only currently revealed observations. The fixed replay path never responds to recommendations. Only after completion does the command evaluate withheld truth and compare independent causal HOLD and observation-guided strategies.

Outputs are in `project/exports`: `summary.json` is the reproducible numerical result, `artifacts.json` identifies the selected run/plan/PDF/figures, and the PDF contains actual browser-free Matplotlib figures, methods, limitations, provenance hashes and step history. Run histories live in `project/runs/<run-id>`. IDs, timestamps and code revision metadata are separate from deterministic numerical results.

An explicit `--steps 10` creates a partial report and withholds geological truth evaluation. It is not a completed case study. Existing populated project outputs are rejected to protect previous histories.

The experiment uses one idealized two-dimensional formation, a 24 ft target, shared eastward x and positive-down local TVD, and a localized downward structural change. Offset wells occupy x=0, 500 and 900 ft. Sensor inversion uses a disclosed synthetic GR calibration, not a method for interpreting real gamma-ray logs. The uncertainty band is assumed and is not statistically calibrated.

`expected.json` contains independent numerical reference values for seed 123. HOLD and guided trials use the same geology, initial state, noise seed, 5,000 ft lateral denominator and lateral DLS bound of 3 degrees/100 ft. The landing build uses a separate bound of 6 degrees/100 ft. Results describe this synthetic experiment only and do not establish operational drilling fitness.

Verify with `python -m pytest` and `python -m ruff check .`. Figure generation uses Matplotlib Agg and requires no browser or paid API. Required figures fail the strict case-study build if missing; tests inspect PDF images and figure dimensions without opening a UI.
