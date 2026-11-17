from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.io.project_store import load_project, read_json, well_paths
from app.model.schemas import Project, Well
from app.services.run_inputs import input_paths
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run


def load_project_and_wells(project_root: str | Path) -> tuple[Project, list[Well]]:
    root = Path(project_root)
    project = load_project(root)
    current_config = read_json(run_root(root) / "simulations" / "simulation_config.json", default={})
    if current_config.get("active_well_id"):
        project.active_well_id = current_config["active_well_id"]
    wells: list[Well] = []
    for ref in project.wells:
        paths = well_paths(root, ref.well_id)
        well_json = read_json(paths["well_json"])
        wells.append(Well.model_validate(well_json))
    return project, wells


def load_well_frames(
    project_root: str | Path,
    well_id: str,
    *,
    include_unrevealed: bool = False,
    run_id: str | None = None,
    source_project_inputs: bool = False,
) -> dict[str, Any]:
    """Operator view of well data; future active records are removed at this boundary.

    ``include_unrevealed`` is reserved for replay ingestion and completed evaluation.
    Pages and report services consume the default view, including scaling statistics.
    Partial survey intervals reveal only recorded stations already acquired; the
    loader never interpolates against a future station.
    """
    root = Path(project_root)
    if source_project_inputs and not include_unrevealed:
        raise ValueError("Raw project inputs are restricted to run initialization and offset estimation.")
    scope = run_root(root, run_id)
    recover_run(scope)
    paths = well_paths(root, well_id) if source_project_inputs else input_paths(root, scope, well_id)
    config = read_json(scope / "simulations" / "simulation_config.json", default={})
    if not include_unrevealed and config.get("mode") == "causal" and config.get("active_well_id") == well_id:
        from app.sim.environment import load_environment_frames
        frames = load_environment_frames(scope)
        if not include_unrevealed:
            state = read_json(scope / "simulations" / "simulation_state.json", default={})
            revealed = float(state.get("revealed_md_ft", config["start_md_ft"]))
            for name in ("trajectory", "survey", "logs"):
                frames[name] = frames[name][frames[name]["md_ft"] <= revealed].copy()
        return frames
    survey = pd.read_parquet(paths["survey"])
    trajectory = pd.read_parquet(paths["trajectory"])
    logs = pd.read_parquet(paths["logs"])
    markers = []
    # Interactive marker edits remain current observations; reports separately
    # use the frozen pre-job picks stored with the run input snapshot.
    current_marker_path = well_paths(root, well_id)["markers"]
    if current_marker_path.exists():
        markers = read_json(current_marker_path, default=[])
    if not include_unrevealed:
        state = read_json(scope / "simulations" / "simulation_state.json", default={})
        if config.get("active_well_id") == well_id and "revealed_md_ft" in state:
            revealed = float(state["revealed_md_ft"])
            survey = survey[survey["md_ft"] <= revealed].copy()
            trajectory = trajectory[trajectory["md_ft"] <= revealed].copy()
            logs = logs[logs["md_ft"] <= revealed].copy()
            markers = [m for m in markers if float(m["md_ft"]) <= revealed]
    return {"survey": survey, "trajectory": trajectory, "logs": logs, "markers": markers}


def load_simulation_revealed_md(project_root: str | Path, run_id: str | None = None) -> float | None:
    root = run_root(project_root, run_id)
    state_path = root / "simulations" / "simulation_state.json"
    if not state_path.exists():
        return None
    state = read_json(state_path, default={})
    revealed = state.get("revealed_md_ft")
    return float(revealed) if revealed is not None else None

