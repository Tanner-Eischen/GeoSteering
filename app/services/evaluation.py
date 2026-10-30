"""Explicit retrospective evaluation; no operator service imports hidden geology."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import read_json
from app.services.interpretations import get_latest_interpretation, load_interpretations
from app.services.project_data import load_well_frames
from app.sim.sim_store import load_simulation_config, load_simulation_state

if TYPE_CHECKING:
    from app.geo.formation import Scenario


def load_completed_scenario(project_root: str | Path, run_id: str | None = None) -> Scenario:
    """Resolve the captured field after completion, for scoring and comparisons."""
    config = load_simulation_config(project_root, run_id)
    if not load_simulation_state(project_root, run_id).complete:
        raise ValueError("Complete the run before revealing geological truth")
    from app.geo.formation import Scenario
    from app.services.run_paths import run_root
    if config.mode == "causal":
        from app.sim.environment import load_private_scenario
        captured = load_private_scenario(run_root(project_root, run_id))
    elif config.hidden_truth_path:
        truth_bytes = Path(config.hidden_truth_path).read_bytes()
        provenance = read_json(run_root(project_root, run_id) / "environment" / "provenance.json", default={})
        expected = provenance.get("source_truth_sha256")
        if expected is None or hashlib.sha256(truth_bytes).hexdigest() != expected:
            raise ValueError("Captured replay truth is missing provenance or has been modified")
        payload = json.loads(truth_bytes)
        captured = Scenario.model_validate(payload.get("scenario", payload))
    else:
        raise ValueError("Run has no captured evaluation scenario; a version label cannot substitute for truth")
    if config.scenario_version not in {"unspecified", captured.version}:
        raise ValueError("Evaluation scenario version does not match the run")
    return captured


def evaluate_completed_run(
    project_root: str | Path, scenario: Scenario | None = None, run_id: str | None = None,
) -> dict:
    """Reveal independent truth metrics only after the chosen run is complete."""
    config = load_simulation_config(project_root, run_id)
    captured = load_completed_scenario(project_root, run_id)
    if scenario is not None and scenario != captured:
        raise ValueError("Supplied evaluation field differs from the frozen run environment")
    scenario = captured
    from app.geo.evaluation import evaluate_trajectory
    from app.geo.formation import formation_top_base
    truth_hash = hashlib.sha256(Path(config.hidden_truth_path).read_bytes()).hexdigest() if config.hidden_truth_path else None
    frames = load_well_frames(project_root, config.active_well_id, run_id=run_id)
    trajectory = frames["trajectory"]
    metrics = evaluate_trajectory(trajectory, scenario)
    lateral = trajectory[trajectory.md_ft >= max(config.lateral_start_md_ft, scenario.lateral_start_md_ft)]
    xcol = "x_ft" if "x_ft" in lateral else "east_ft"
    x = lateral[xcol].to_numpy(dtype=float)
    top, base = formation_top_base(x, scenario)
    truth_center = (top + base) / 2.0
    versions = load_interpretations(project_root, run_id)
    latest = get_latest_interpretation(project_root, run_id)
    errors = {}
    for label, interpretation in [("baseline", versions[0]), ("final", latest)]:
        estimate_top = evaluate_piecewise_linear(interpretation.top_control_points, x)
        estimate_base = evaluate_piecewise_linear(interpretation.base_control_points, x)
        errors[f"{label}_interpretation_mean_absolute_error_ft"] = float(
            np.mean(np.abs((estimate_top + estimate_base) / 2.0 - truth_center))
        )
    return {
        "run_id": config.run_id, "mode": config.mode, "metric_basis": "withheld_truth",
        "scenario_version": scenario.version, "seed": scenario.seed,
        "truth_sha256": truth_hash,
        "lateral_start_md_ft": max(config.lateral_start_md_ft, scenario.lateral_start_md_ft),
        "metrics": metrics, "interpretation_error": errors,
        "limitation": "Recommendations did not change this fixed recorded trajectory" if config.mode == "replay" else "Simplified kinematics and synthetic sensors; not operational drilling software",
    }
