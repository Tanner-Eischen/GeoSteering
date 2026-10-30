"""One-command, browser-free scientific case-study build."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import numpy as np

from app.io.project_store import atomic_write_json, create_project, read_json
from app.io.well_import import import_well_folder
from app.model.schemas import ControlPoint
from app.plan.plan_export import export_plan_csv
from app.plan.plan_generator import plan_to_target
from app.plan.plan_store import save_plan
from app.report.report_builder import build_report
from app.services.baseline import estimate_offset_baseline
from app.services.decisions import export_decision_log_csv
from app.services.interpretations import get_latest_interpretation
from app.services.project_data import load_project_and_wells, load_well_frames
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.services.runs import advance_run, initialize_run
from app.sim.sim_models import SimulationConfig
from tools.generate_sample_data import generate_sample_data


def _revision():
    repository = Path(__file__).resolve().parents[1]

    def git(*args):
        result = subprocess.run(["git", *args], cwd=repository, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def _update(points, x, tvd):
    result = [point for point in points if abs(point.x_ft - x) > 1e-8]
    result.append(ControlPoint(md_ft=x, x_ft=x, tvd_ft=tvd))
    return sorted(result, key=lambda point: point.x_ft)


def build_case_study(project_root: Path, sample_root: Path, *, seed=123, steps=None) -> Path:
    """Build a new isolated run. ``steps`` explicitly requests a partial replay."""
    project_root, sample_root = Path(project_root), Path(sample_root)
    if steps is not None and steps < 0:
        raise ValueError("steps must be nonnegative, or omit it for a complete replay")
    if project_root.exists() and any(project_root.iterdir()):
        raise FileExistsError(f"Refusing to overwrite populated project: {project_root}; choose a new output")
    if not (sample_root / "manifest.json").exists():
        generate_sample_data(sample_root, seed=seed)
    public = read_json(sample_root / "manifest.json")
    if public["seed"] != seed or public["scenario_version"] != "structural_dip_01-v1":
        raise ValueError("Sample seed/version does not match the requested flagship scenario")
    create_project(project_root, name="GeoSteering Structural Uncertainty")
    atomic_write_json(project_root / "manifest.json", public)
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(project_root, sample_root / "wells" / name, name)
    project, wells = load_project_and_wells(project_root)
    offsets = [well.well_id for well in wells if well.well_id != project.active_well_id]
    top, base, uncertainty = estimate_offset_baseline(project_root, offsets)
    # Solve the landing from offset geometry, without reading the true horizon.
    params, planned = plan_to_target(top, base, dls_max_deg_per_100ft=6.0)
    plan = save_plan(
        project_root, "Offset-informed landing and lateral", params, planned.stations, 6.0, planned.exceedances
    )
    export_plan_csv(planned.stations, project_root / "exports" / "plan_demo.csv")
    config = SimulationConfig(
        active_well_id=project.active_well_id,
        offset_well_ids=offsets,
        step_size_ft=50.0,
        start_md_ft=public["lateral_start_md_ft"],
        end_md_ft=public["end_md_ft"],
        lateral_start_md_ft=public["lateral_start_md_ft"],
        seed=seed,
        scenario_version=public["scenario_version"],
        plan_id=plan.plan_id,
        hidden_truth_path=str((sample_root / "truth.json").resolve()),
    )
    state = initialize_run(project_root, config, top, base, uncertainty_band_tvd_ft=uncertainty)
    scope = run_root(project_root, state.run_id)
    revision, dirty = _revision()
    hashes = {
        path.relative_to(sample_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(sample_root.rglob("*"))
        if path.is_file() and path.name != "truth.json"
    }
    atomic_write_json(
        scope / "manifest.json",
        {
            "scenario_version": public["scenario_version"],
            "seed": seed,
            "run_id": state.run_id,
            "plan_id": plan.plan_id,
            "mode": "replay",
            "input_hashes": hashes,
            "code_revision": revision,
            "dirty_working_tree": dirty,
            "coordinate_reference": "LOCAL_EAST_NORTH_FT; LOCAL_TVD positive down",
            "sensor_calibration": public["sensor_calibration"],
            "uncertainty_note": public["uncertainty_note"],
        },
    )
    iterations = 0
    while not state.complete and (steps is None or iterations < steps):
        # This loader exposes only measurements already revealed at decision time.
        frames = load_well_frames(project_root, project.active_well_id, run_id=state.run_id)
        logs, trajectory = frames["logs"], frames["trajectory"]
        recent = logs[logs.md_ft >= max(config.start_md_ft, state.revealed_md_ft - 20.0)]
        if recent.empty:
            raise ValueError("No current active measurements available for a recommendation")
        sample_md = recent.md_ft.to_numpy()
        tvd = np.interp(sample_md, trajectory.md_ft, trajectory.tvd_ft)
        x = np.interp(sample_md, trajectory.md_ft, trajectory.x_ft)
        calibration = public["sensor_calibration"]
        gr = recent.GR.to_numpy()
        # Explicitly calibrated synthetic inversion; it is not real-log inversion.
        valid = (gr > 22.0) & (gr < 158.0)
        interpretation = get_latest_interpretation(project_root, state.run_id)
        if valid.any():
            relative = (gr[valid] - calibration["gr_center_api"]) / calibration["gr_gradient_api_per_ft"]
            center = float(np.median(tvd[valid] - relative))
            current_x = float(np.median(x[valid]))
            # Thickness is inferred from offset picks; no horizon truth is read here.
            thickness = float(np.median([b.tvd_ft - a.tvd_ft for a, b in zip(top, base)]))
            revised_top = _update(interpretation.top_control_points, current_x, center - thickness / 2.0)
            revised_base = _update(interpretation.base_control_points, current_x, center + thickness / 2.0)
            offset = float(np.median(relative))
            action = "BUILD" if offset > 2.0 else "DROP" if offset < -2.0 else "HOLD"
            evidence = (
                f"Observed MD {recent.md_ft.min():.1f}-{recent.md_ft.max():.1f} ft; "
                f"median GR {np.median(gr):.3f} API; calibrated center {center:.3f} ft TVD; "
                f"estimated relative position {offset:.3f} ft"
            )
            rationale = "Revised shared-x horizon using revealed calibrated GR and survey only"
        else:
            # Saturation gives direction but no unique center. Preserve the model
            # and explicitly record that the replay cannot resolve this interval.
            revised_top = interpretation.top_control_points
            revised_base = interpretation.base_control_points
            action = "DROP" if float(np.median(gr)) < 80.0 else "BUILD"
            evidence = (
                f"Observed MD {recent.md_ft.min():.1f}-{recent.md_ft.max():.1f} ft; "
                f"median GR {np.median(gr):.3f} API is saturated; center unresolved; "
                "retained last constrained interpretation"
            )
            rationale = "Saturated synthetic GR supplies only a directional bound, not a unique horizon pick"
        assumed_band = (
            max(interpretation.uncertainty.band_tvd_ft or 10.0, 30.0)
            if not valid.any()
            else interpretation.uncertainty.band_tvd_ft
        )
        state = advance_run(
            project_root,
            action,
            evidence,
            rationale=rationale,
            top_control_points=revised_top,
            base_control_points=revised_base,
            uncertainty_band_tvd_ft=assumed_band,
        )
        iterations += 1
    export_decision_log_csv(project_root, project_root / "exports" / "decision_log.csv")
    metrics = load_run_metrics(project_root, state.run_id)
    summary = {
        "scenario_version": public["scenario_version"],
        "seed": seed,
        "mode": "interpretation_replay",
        "complete": state.complete,
        "revealed_md_ft": state.revealed_md_ft,
        "steps": state.step_index,
        "estimated_history": [
            {
                key: value
                for key, value in row.items()
                if key not in {"run_id", "interpretation_version_id", "decision_id"}
            }
            for row in metrics
        ],
    }
    if state.complete:
        # This is the sole transition from operator workflow to retrospective truth.
        from app.geo.formation import Scenario, formation_top_base
        from app.services.evaluation import evaluate_completed_run
        from app.sim.causal import compare_strategies
        from app.sim.sim_store import load_simulation_config

        frozen_config = load_simulation_config(project_root, state.run_id)
        truth_path = Path(frozen_config.hidden_truth_path)
        private_truth = read_json(truth_path)
        scenario = Scenario.model_validate(private_truth["scenario"])
        evaluation = evaluate_completed_run(project_root, run_id=state.run_id)
        evaluation["truth_input_sha256"] = hashlib.sha256(truth_path.read_bytes()).hexdigest()
        comparison = compare_strategies(scenario=scenario, seed=seed)
        atomic_write_json(scope / "evaluation" / "replay.json", evaluation)
        atomic_write_json(scope / "evaluation" / "comparison.json", comparison)
        x = np.linspace(0.0, 6000.0, 301)
        truth_top, truth_base = formation_top_base(x, scenario)
        atomic_write_json(
            scope / "evaluation" / "truth_profile.json",
            {"x_ft": x.tolist(), "top_tvd_ft": truth_top.tolist(), "base_tvd_ft": truth_base.tolist()},
        )
        summary["replay_evaluation"] = {key: value for key, value in evaluation.items() if key != "run_id"}
        summary["causal_comparison"] = {name: run["metrics"] for name, run in comparison["runs"].items()}
    atomic_write_json(project_root / "exports" / "summary.json", summary)
    atomic_write_json(project_root / "exports" / "kpi_summary.json", metrics[-1] if metrics else {})
    report = build_report(project_root, run_id=state.run_id, plan_id=plan.plan_id, strict=steps != 0)
    atomic_write_json(
        project_root / "exports" / "artifacts.json",
        {
            "run_id": state.run_id,
            "plan_id": plan.plan_id,
            "report": str(report.relative_to(project_root)),
            "summary": "exports/summary.json",
            "figure_directory": str((scope / "cache" / "report_snapshots").relative_to(project_root)),
        },
    )
    return report


def run_case_study(out: Path, *, seed=123, steps=None) -> Path:
    out = Path(out)
    return build_case_study(out / "project", out / "sample", seed=seed, steps=steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--steps", type=int, help="Explicitly stop after this many steps (partial report)")
    args = parser.parse_args()
    report = run_case_study(args.out, seed=args.seed, steps=args.steps)
    print(f"Case study complete: {report}")


if __name__ == "__main__":
    main()
