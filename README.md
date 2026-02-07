# Geosteering Workbench MVP

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[test,dev]
```

## Generate sample data

```powershell
python -m tools.generate_sample_data --out data/sample_project --seed 123
```

## Create and populate a demo project

```powershell
python -m tools.create_project data/demo_project --name "GeoSteering Demo"
Get-ChildItem data/sample_project/wells -Directory | ForEach-Object {
  python -m tools.import_well --project-root data/demo_project --well-folder $_.FullName --well-name $_.Name
}
```

## Run app

```powershell
streamlit run streamlit_app.py
```

## Headless end-to-end bootstrap

```powershell
python -m tools.bootstrap_demo_project --project-root data/demo_project --sample-root data/sample_project --steps 10
```

## Export report

```powershell
python -m tools.export_report data/demo_project
```

## Test suite

```powershell
python -c "import app"
pytest
```

## Demo checklist

- Open project and verify all four wells are loaded.
- Confirm Data QC table shows valid wells and curve coverage.
- Open Correlation Panel and add or edit markers on at least one offset well.
- Open Planning, generate plan preview, verify DLS warnings table, save and export CSV.
- Open Steering Console, initialize simulation, step forward at least 10 steps, create interpretation updates with rationale, log decisions.
- Open Report Export and generate PDF.
- Verify artifacts:
  - `exports/plan_demo.csv`
  - `exports/decision_log.csv`
  - `exports/report_<project>.pdf`
  - `exports/kpi_summary.json`

## Notes

- The app is a training and portfolio tool, not for live operations.
- Plot snapshots in report generation are disabled by default in automated environments.
- To enable Plotly PNG snapshots, set `GEOSTEERING_ENABLE_SNAPSHOTS=1`.

```powershell
$env:GEOSTEERING_ENABLE_SNAPSHOTS = "1"
python -m tools.export_report data/demo_project
```
