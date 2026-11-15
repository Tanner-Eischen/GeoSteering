"""Run-bound evaluation presentation with completion and saved-result checks."""

from __future__ import annotations

import numpy as np

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import atomic_write_json, read_json
from app.services.evaluation import evaluate_completed_run, load_completed_scenario
from app.services.operator_workflow import load_operator_view
from app.services.run_paths import run_root
from app.services.run_transactions import run_access_lock

_RESULT_FIELDS = (
    "run_id", "mode", "scenario_version", "seed", "truth_sha256",
    "lateral_start_md_ft", "metrics", "interpretation_error",
)


def evaluate_and_save(project_root, run_id):
    """Evaluate this explicit completed run and save the standard report artifact."""
    if not run_id:
        raise ValueError("Select a saved run before evaluating")
    scope = run_root(project_root, run_id)
    with run_access_lock(scope):
        evaluation = evaluate_completed_run(project_root, run_id=run_id)
        atomic_write_json(scope / "evaluation" / "replay.json", evaluation)
        return evaluation


def load_evaluation_view(project_root, run_id):
    """Read current diagnostics; independently validate completed saved outcomes.

    No truth loader or saved outcome file is read for unfinished runs. Loading an
    unevaluated completed run also leaves truth hidden until explicit evaluation.
    """
    if not run_id:
        raise ValueError("Select a saved run before opening evaluation")
    with run_access_lock(run_root(project_root, run_id)):
        view = load_operator_view(project_root, run_id)
        view.update({"evaluation": None, "profile": None, "evaluation_error": None})
        if not view["state"].complete:
            return view
        try:
            saved_path = view["scope"] / "evaluation" / "replay.json"
            if not saved_path.is_file():
                return view
            saved = read_json(saved_path)
            current = evaluate_completed_run(project_root, run_id=run_id)
            if not isinstance(saved, dict) or any(saved.get(key) != current[key] for key in _RESULT_FIELDS):
                raise ValueError("Saved evaluation does not match this run's captured evidence. Evaluate the completed run again.")
            scenario = load_completed_scenario(project_root, run_id=run_id)
            from app.geo.formation import formation_top_base

            trajectory = view["frames"]["trajectory"]
            start = current["lateral_start_md_ft"]
            end = float(trajectory.md_ft.max())
            md = np.linspace(start, end, 1001)
            xcol = "x_ft" if "x_ft" in trajectory else "east_ft"
            x = np.interp(md, trajectory.md_ft, trajectory[xcol])
            tvd = np.interp(md, trajectory.md_ft, trajectory.tvd_ft)
            top, base = formation_top_base(x, scenario)
            interpretation = view["interpretation"]
            estimated_x = sorted({float(x.min()), float(x.max()), *(
                float(point.x_ft) for point in [*interpretation.top_control_points, *interpretation.base_control_points]
                if x.min() <= point.x_ft <= x.max()
            )})
            estimated_top = evaluate_piecewise_linear(interpretation.top_control_points, estimated_x)
            estimated_base = evaluate_piecewise_linear(interpretation.base_control_points, estimated_x)
            view["profile"] = {
                "md_ft": md.tolist(), "x_ft": x.tolist(), "tvd_ft": tvd.tolist(),
                "true_top_tvd_ft": top.tolist(), "true_base_tvd_ft": base.tolist(),
                "estimated_x_ft": estimated_x,
                "estimated_top_tvd_ft": estimated_top.tolist(), "estimated_base_tvd_ft": estimated_base.tolist(),
                "lateral_dls_limit": scenario.max_dls_deg_per_100ft,
                "command_dls_limit": (min(view["config"].max_dls_deg_per_100ft, scenario.max_dls_deg_per_100ft)
                                      if view["config"].mode == "causal" else None),
            }
            view["evaluation"] = saved
        except (OSError, ValueError, KeyError, TypeError) as exc:
            view["evaluation_error"] = str(exc)
        return view
