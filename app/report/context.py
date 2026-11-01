"""Explicit, bounded report inputs shared by text and figure rendering."""

from __future__ import annotations

from pathlib import Path

from app.io.project_store import read_json
from app.model.schemas import Marker
from app.services.markers import load_markers
from app.services.project_data import load_project_and_wells
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run


def report_markers(context: dict, well_id: str) -> list[Marker]:
    """Use formation picks captured with the run, including an empty snapshot."""
    snapshot = context["scope"] / "inputs" / "wells" / well_id / "markers.json"
    if snapshot.exists():
        return [Marker.model_validate(row) for row in read_json(snapshot)]
    return load_markers(context["root"], well_id)


def report_context(project_root, *, run_id=None, plan_id=None, include_wells=None, include_steps=None):
    root = Path(project_root)
    project, wells = load_project_and_wells(root)
    active = read_json(root / "active_run.json", default={})
    selected_run = run_id or active.get("run_id")
    scope = run_root(root, selected_run)
    recover_run(scope)
    if selected_run and not scope.is_dir():
        raise ValueError(f"Unknown run: {selected_run}")
    state = read_json(scope / "simulations" / "simulation_state.json", default={})
    config = read_json(scope / "simulations" / "simulation_config.json", default={})
    if selected_run and (not state or not config):
        raise ValueError(f"Run has no complete saved configuration/state: {selected_run}")
    if not state:
        state = read_json(root / "simulations" / "simulation_state.json", default={})
    revealed = state.get("revealed_md_ft")
    allowed = None if include_wells is None else set(include_wells)
    wells = [w for w in wells if allowed is None or w.well_id in allowed or w.name in allowed]
    plans = [read_json(p) for p in (root / "plans").glob("*.json")]
    if plan_id:
        plan = next((p for p in plans if p["plan_id"] == plan_id), None)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_id}")
    else:
        manifest = read_json(scope / "manifest.json", default={})
        pinned = manifest.get("plan_id") or config.get("plan_id")
        plan = next((p for p in plans if p["plan_id"] == pinned), None)
        if selected_run and pinned and plan is None:
            raise ValueError(f"Pinned plan is missing for run {selected_run}: {pinned}")
        if plan is None and selected_run is None:
            plan = max(plans, key=lambda p: p["created_at"], default=None)
    return {
        "root": root,
        "scope": scope,
        "project": project,
        "wells": wells,
        "run_id": selected_run,
        "state": state,
        "config": config,
        "active_well_id": config.get("active_well_id", project.active_well_id),
        "revealed_md_ft": revealed,
        "plan": plan,
        "include_steps": include_steps,
    }
