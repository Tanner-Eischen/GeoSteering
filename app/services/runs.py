"""Run-scoped, evidence-backed replay orchestration.

Recommendations are recorded before revealing the following interval. They never
change the recorded trajectory. Geological truth is absent from this module.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.alg.kpi import compute_kpis
from app.io.project_store import atomic_write_json
from app.model.schemas import ControlPoint, Recommendation, UncertaintyModel
from app.services.decisions import create_decision
from app.services.interpretations import (
    create_baseline_interpretation,
    create_interpretation_version,
    get_latest_interpretation,
)
from app.services.project_data import load_project_and_wells, load_well_frames
from app.services.run_inputs import describe_run_inputs, snapshot_run_inputs
from app.services.run_metrics import save_metric_snapshot
from app.services.run_paths import active_run_id, run_root
from app.services.run_transactions import atomic_run_step
from app.sim.engine import initial_state, step_forward
from app.sim.sim_models import SimulationConfig, SimulationState
from app.sim.sim_store import (
    load_simulation_config,
    load_simulation_state,
    save_simulation_config,
    save_simulation_state,
)

__all__ = ["active_run_id", "advance_run", "fork_run", "initialize_run", "run_root"]


def initialize_run(
    project_root: str | Path,
    config: SimulationConfig,
    top_control_points: Sequence[ControlPoint],
    base_control_points: Sequence[ControlPoint],
    uncertainty_band_tvd_ft: float = 5.0,
    hidden_truth_path: str | Path | None = None,
) -> SimulationState:
    """Create a new history, preserving every prior run and its interpretation."""
    root = Path(project_root)
    if not (root / "project.json").exists():
        raise ValueError("Create a project before initializing a replay")
    _, wells = load_project_and_wells(root)
    by_id = {well.well_id: well for well in wells}
    selected_ids = [config.active_well_id, *config.offset_well_ids]
    if any(well_id not in by_id or by_id[well_id].reference is None for well_id in selected_ids):
        raise ValueError("All run wells require explicit spatial coordinate references.")
    references = [by_id[well_id].reference for well_id in selected_ids]
    if len({(ref.coordinate_system, ref.vertical_datum) for ref in references}) != 1 or any(abs(ref.origin_north_ft) > 1e-8 for ref in references):
        raise ValueError("Run wells must share one datum and the same 2D section.")
    if len(top_control_points) < 2 or len(base_control_points) < 2:
        raise ValueError("At least two offset-derived top/base points are required")
    if not all(cp.x_ft is not None for cp in [*top_control_points, *base_control_points]):
        raise ValueError("New runs require shared-x interpretations; legacy MD models must be migrated")
    knots = sorted({cp.x_ft for cp in [*top_control_points, *base_control_points]})
    top_at_knots = evaluate_piecewise_linear(top_control_points, knots)
    base_at_knots = evaluate_piecewise_linear(base_control_points, knots)
    if any(base <= top for top, base in zip(top_at_knots, base_at_knots)):
        raise ValueError("Interpreted base must be strictly below top throughout the model")
    UncertaintyModel(band_tvd_ft=uncertainty_band_tvd_ft)
    run_id = str(uuid4())
    scope = root / "runs" / run_id
    updates = {"run_id": run_id}
    if hidden_truth_path is not None:
        updates["hidden_truth_path"] = str(Path(hidden_truth_path).resolve())
    run_config = config.model_copy(update=updates, deep=True)
    frames = load_well_frames(root, config.active_well_id, include_unrevealed=True, source_project_inputs=True)
    if frames["logs"].empty or frames["trajectory"].empty:
        raise ValueError("Active well requires logs and a trajectory")
    if config.start_md_ft < max(float(frames["logs"].md_ft.min()), float(frames["trajectory"].md_ft.min())):
        raise ValueError("Run starts before available active measurements")
    if config.end_md_ft > min(float(frames["logs"].md_ft.max()), float(frames["trajectory"].md_ft.max())):
        raise ValueError("Run ends beyond available active measurements")
    if config.mode == "causal" and not run_config.hidden_truth_path and not config.use_default_synthetic_scenario:
        raise ValueError("A causal run requires captured truth or explicit selection of the bundled synthetic environment")
    scope.mkdir(parents=True, exist_ok=False)
    snapshot_run_inputs(root, scope, [config.active_well_id, *config.offset_well_ids])
    # Populate the isolated scope before publishing it as the active run.
    if config.mode == "causal":
        from app.sim.environment import initialize_environment
        initialize_environment(scope, run_config, frames, run_config.hidden_truth_path)
        run_config = run_config.model_copy(update={"hidden_truth_path": str((scope / "environment" / "scenario.json").resolve())})
    elif run_config.hidden_truth_path:
        from app.sim.environment import snapshot_replay_truth
        pinned = snapshot_replay_truth(scope, run_config.hidden_truth_path)
        run_config = run_config.model_copy(update={"hidden_truth_path": str(pinned)})
    save_simulation_config(scope, run_config)
    state = initial_state(run_config)
    save_simulation_state(scope, state)
    baseline = create_baseline_interpretation(
        scope,
        top_control_points=top_control_points,
        base_control_points=base_control_points,
        uncertainty_band_tvd_ft=uncertainty_band_tvd_ft,
        rationale="Pre-job regional model fitted to offset formation picks only; uncertainty is scenario-assumed",
    )
    state.version_id_by_step = [baseline.version_id]
    state.decision_id_by_step = [None]
    save_simulation_state(scope, state)
    atomic_write_json(scope / "manifest.json", describe_run_inputs(scope, run_config))
    atomic_write_json(root / "active_run.json", {"run_id": run_id})
    return state


def fork_run(project_root: str | Path, run_id: str | None = None) -> SimulationState:
    """Copy an acquired prefix into a new run for command counterfactuals."""
    root = Path(project_root)
    source = run_root(root, run_id)
    config = load_simulation_config(root, run_id)
    state = load_simulation_state(root, run_id)
    if config.run_id is None:
        raise ValueError("Legacy unscoped simulations must be initialized as a new spatial run")
    if state.complete:
        raise ValueError("Fork an unfinished run; initialize a new run to reset a completed experiment")
    new_id = str(uuid4())
    destination = root / "runs" / new_id
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("exports", "evaluation", "figures", "report_snapshots"))
    payload = config.model_dump(mode="json")
    payload["run_id"] = new_id
    if config.hidden_truth_path:
        captured = Path(config.hidden_truth_path)
        if captured.is_relative_to(source.resolve()):
            payload["hidden_truth_path"] = str((destination.resolve() / captured.relative_to(source.resolve())).resolve())
    atomic_write_json(destination / "simulations" / "simulation_config.json", payload)
    new_state = state.model_copy(update={"run_id": new_id}, deep=True)
    atomic_write_json(destination / "simulations" / "simulation_state.json", new_state.model_dump(mode="json"))
    from app.io.project_store import read_json
    manifest = read_json(destination / "manifest.json", default={})
    manifest.update({"run_id": new_id, "parent_run_id": config.run_id, "forked_at_step": state.step_index})
    atomic_write_json(destination / "manifest.json", manifest)
    atomic_write_json(root / "active_run.json", {"run_id": new_id})
    return new_state


@atomic_run_step
def advance_run(
    project_root: str | Path,
    action: str,
    observations: str,
    rationale: str | None = None,
    top_control_points: Sequence[ControlPoint] | None = None,
    base_control_points: Sequence[ControlPoint] | None = None,
    target_inc_deg: float | None = None,
    uncertainty_band_tvd_ft: float | None = None,
) -> SimulationState:
    """Record a recommendation using current evidence, then reveal the next interval."""
    config = load_simulation_config(project_root)
    state = load_simulation_state(project_root)
    if state.complete:
        raise ValueError("Replay is already complete; initialize a new run to repeat it")
    Recommendation(action=action)
    if not observations.strip():
        raise ValueError("Record supporting observed evidence before revealing another interval")
    latest = get_latest_interpretation(project_root)
    if latest is None:
        raise ValueError("Run has no baseline interpretation")
    next_state = step_forward(state, config)
    top = list(top_control_points) if top_control_points is not None else latest.top_control_points
    base = list(base_control_points) if base_control_points is not None else latest.base_control_points
    # Validate the complete next scoring interval before persisting history.
    response = None
    acquired = None
    if config.mode == "causal":
        from app.sim.environment import preview_environment_step
        acquired, response = preview_environment_step(
            run_root(project_root), config, next_state.revealed_md_ft,
            next_state.step_index, action, target_inc_deg,
        )
        trajectory = acquired["trajectory"]
    else:
        raw = load_well_frames(project_root, config.active_well_id, include_unrevealed=True)
        trajectory = raw["trajectory"][raw["trajectory"]["md_ft"] <= next_state.revealed_md_ft].copy()
    md_from = max(config.start_md_ft, config.lateral_start_md_ft)
    md_to = min(next_state.revealed_md_ft, float(trajectory.md_ft.max()))
    if md_to > md_from:
        metrics = asdict(compute_kpis(trajectory, top, base, md_from, md_to, step_ft=1.0))
    else:
        metrics = {"percent_in_zone": 0.0, "avg_center_distance": 0.0, "last_step_in_zone": 0.0,
                   "in_zone_length_ft": 0.0, "evaluated_length_ft": 0.0, "max_overshoot_ft": 0.0}
    version = create_interpretation_version(
        project_root, step_index=next_state.step_index,
        rationale=rationale or f"Carry forward current interpretation: {observations.strip()}",
        top_control_points=top, base_control_points=base,
        uncertainty_band_tvd_ft=uncertainty_band_tvd_ft if uncertainty_band_tvd_ft is not None else (latest.uncertainty.band_tvd_ft or 5.0),
    )
    decision = create_decision(
        project_root, step_index=next_state.step_index,
        md_from_ft=state.revealed_md_ft, md_to_ft=next_state.revealed_md_ft,
        interpretation_version_id=version.version_id, observations=observations.strip(), action=action,
        target_inc_deg=target_inc_deg,
        risk_note="Replay recommendation; recorded trajectory is unchanged" if config.mode == "replay" else str(response),
    )
    save_metric_snapshot(project_root, {
        "step_index": next_state.step_index, "revealed_md_ft": next_state.revealed_md_ft,
        "decision_time_md_ft": state.revealed_md_ft,
        "interpretation_version_id": version.version_id, "decision_id": decision.decision_id,
        "md_from_ft": md_from, "md_to_ft": md_to, "metric_basis": "estimated_zone",
        "coordinate_basis": "shared_x_ft", "action": action, "command_response": response, **metrics,
        "uncertainty_band_tvd_ft": version.uncertainty.band_tvd_ft,
    })
    next_state.version_id_by_step.append(version.version_id)
    next_state.decision_id_by_step.append(decision.decision_id)
    if acquired is not None:
        from app.sim.environment import commit_environment_step
        commit_environment_step(run_root(project_root), acquired, response)
    save_simulation_state(project_root, next_state)
    return next_state
