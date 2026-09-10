# Geosteering Workbench

[![CI](https://github.com/Tanner-Eischen/GeoSteering/actions/workflows/ci.yml/badge.svg)](https://github.com/Tanner-Eischen/GeoSteering/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Geosteering Workbench is a local Streamlit application for practicing a geosteering workflow with synthetic well data. It imports LAS logs and survey CSV files, checks the inputs, supports marker correlation and target planning, steps through a simulated active well, records steering decisions, and exports a PDF report.

This is a training and portfolio project. It has no live data feed, WITSML support, or operational safety controls, and it is not validated for use on a well.

## Setup

Python 3.11 or newer is required.

```bash
git clone https://github.com/Tanner-Eischen/GeoSteering.git
cd GeoSteering
python -m venv .venv
```

Activate the environment, then install the application and development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[test,dev]"
```

## Build the demo project

The repository includes four deterministic synthetic wells under `data/sample_project`. The bootstrap command imports those files and creates a working project:

```bash
python -m tools.bootstrap_demo_project \
  --project-root data/demo_project \
  --sample-root data/sample_project \
  --steps 10
```

On PowerShell, enter the command on one line or use PowerShell continuation characters instead of the backslashes.

## Run the application

```bash
streamlit run streamlit_app.py
```

In the sidebar, enter `data/demo_project` under **Open project root**, then select **Open Project**.

The pages cover data quality, individual log tracks, multiwell correlation, target planning, the steering simulation, and report export. Project state is stored as JSON, CSV, Parquet, and PDF files under the selected project directory.

## Command-line utilities

```bash
# Regenerate the checked-in sample inputs
python -m tools.generate_sample_data --out data/sample_project --seed 123

# Create an empty project
python -m tools.create_project data/my_project --name "My project"

# Import one well folder
python -m tools.import_well \
  --project-root data/my_project \
  --well-folder data/sample_project/wells/offset_01 \
  --well-name offset_01

# Export a report from a populated project
python -m tools.export_report data/demo_project
```

## Architecture

```text
streamlit_app.py     Page selection and project controls
app/io/              LAS, survey, and project persistence
app/qc/              Input validation and coverage checks
app/alg/             Trajectory, interpretation, and KPI calculations
app/plan/            Target plan generation and CSV export
app/sim/             Deterministic steering simulation
app/services/        Marker, interpretation, and decision state
app/plot/            Plotly figures used by the UI and reports
app/report/          PDF report assembly
tools/               Project, import, demo, and export commands
tests/               Unit and end-to-end tests
```

The numerical core is separate from Streamlit, so trajectory, planning, persistence, and report behavior can be tested without launching the UI.

## Checks

```bash
python -m ruff check . --select E9,F63,F7,F82
python -m pytest
python -m build
```

GitHub Actions runs these commands on Python 3.11.

## License

This project is available under the [MIT License](LICENSE).
