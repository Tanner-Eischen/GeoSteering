from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.io.project_store import load_project, read_json, well_paths
from app.model.schemas import Project, Well


def load_project_and_wells(project_root: str | Path) -> tuple[Project, list[Well]]:
    root = Path(project_root)
    project = load_project(root)
    wells: list[Well] = []
    for ref in project.wells:
        paths = well_paths(root, ref.well_id)
        well_json = read_json(paths["well_json"])
        wells.append(Well.model_validate(well_json))
    return project, wells


def load_well_frames(project_root: str | Path, well_id: str) -> dict[str, Any]:
    root = Path(project_root)
    paths = well_paths(root, well_id)
    survey = pd.read_parquet(paths["survey"])
    trajectory = pd.read_parquet(paths["trajectory"])
    logs = pd.read_parquet(paths["logs"])
    markers = []
    if paths["markers"].exists():
        markers = read_json(paths["markers"], default=[])
    return {"survey": survey, "trajectory": trajectory, "logs": logs, "markers": markers}


def load_simulation_revealed_md(project_root: str | Path) -> float | None:
    root = Path(project_root)
    state_path = root / "simulations" / "simulation_state.json"
    if not state_path.exists():
        return None
    state = read_json(state_path, default={})
    revealed = state.get("revealed_md_ft")
    return float(revealed) if revealed is not None else None

