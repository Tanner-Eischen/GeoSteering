from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.alg.interpretation_model import add_or_update_control_point
from app.alg.kpi import compute_kpis
from app.io.project_store import create_project
from app.io.well_import import import_well_folder
from app.model.schemas import ControlPoint, PlanParameters
from app.plan.plan_export import export_plan_csv
from app.plan.plan_generator import generate_plan
from app.plan.plan_store import save_plan
from app.report.report_builder import build_report
from app.services.decisions import create_decision, export_decision_log_csv
from app.services.interpretations import (
    create_baseline_interpretation,
    create_interpretation_version,
    get_latest_interpretation,
)
from app.services.project_data import load_project_and_wells, load_well_frames
from app.sim.engine import initial_state, step_forward
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import save_simulation_config, save_simulation_state
from tools.generate_sample_data import generate_sample_data


def bootstrap_demo_project(project_root: Path, sample_root: Path, steps: int = 10) -> Path:
    if not (sample_root / "wells").exists():
        generate_sample_data(sample_root, seed=123)

    create_project(project_root, name="GeoSteering Demo")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(project_root, sample_root / "wells" / name, name)

    project, _ = load_project_and_wells(project_root)
    active_id = project.active_well_id
    active_frames = load_well_frames(project_root, active_id)
    trajectory = active_frames["trajectory"]
    logs = active_frames["logs"]

    plan_params = PlanParameters(
        kickoff_md_ft=1000.0,
        landing_md_ft=3000.0,
        lateral_length_ft=5000.0,
        planned_azi_deg=90.0,
        step_ft=100.0,
    )
    plan_result = generate_plan(plan_params, dls_max_deg_per_100ft=3.0)
    save_plan(
        project_root,
        name="DemoPlan",
        parameters=plan_params,
        stations=plan_result.stations,
        dls_max_deg_per_100ft=3.0,
        exceedances=plan_result.exceedances,
    )
    export_plan_csv(plan_result.stations, project_root / "exports" / "plan_demo.csv")

    truth_path = sample_root / "truth.json"
    if truth_path.exists():
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        top_points = [ControlPoint.model_validate(cp) for cp in truth["zone_model"]["top_control_points"]]
        base_points = [ControlPoint.model_validate(cp) for cp in truth["zone_model"]["base_control_points"]]
    else:
        md_min, md_max = float(trajectory["md_ft"].min()), float(trajectory["md_ft"].max())
        center_start = float(trajectory["tvd_ft"].iloc[0])
        center_end = float(trajectory["tvd_ft"].iloc[-1])
        top_points = [ControlPoint(md_ft=md_min, tvd_ft=center_start - 10), ControlPoint(md_ft=md_max, tvd_ft=center_end - 10)]
        base_points = [ControlPoint(md_ft=md_min, tvd_ft=center_start + 10), ControlPoint(md_ft=md_max, tvd_ft=center_end + 10)]

    create_baseline_interpretation(project_root, top_control_points=top_points, base_control_points=base_points)

    config = SimulationConfig(
        active_well_id=active_id,
        offset_well_ids=[w.well_id for w in project.wells if w.well_id != active_id],
        curves_used=["GR", "RES"],
        step_size_ft=100.0,
        window_size_ft=500.0,
        start_md_ft=float(logs["md_ft"].min()),
        end_md_ft=float(logs["md_ft"].max()),
    )
    save_simulation_config(project_root, config)
    state = initial_state(config)

    for i in range(steps):
        state = step_forward(state, config)
        latest = get_latest_interpretation(project_root)
        cp_md = float(state.revealed_md_ft)
        top_tvd = float(trajectory["tvd_ft"].iloc[min(len(trajectory) - 1, int(cp_md / 100.0))] - 10.0)
        base_tvd = top_tvd + 20.0
        new_top = add_or_update_control_point(latest.top_control_points, md_ft=cp_md, tvd_ft=top_tvd)
        new_base = add_or_update_control_point(latest.base_control_points, md_ft=cp_md, tvd_ft=base_tvd)
        version = create_interpretation_version(
            project_root,
            step_index=state.step_index,
            rationale=f"Demo update step {i + 1}",
            top_control_points=new_top,
            base_control_points=new_base,
        )
        create_decision(
            project_root,
            step_index=state.step_index,
            md_from_ft=max(config.start_md_ft, state.revealed_md_ft - config.step_size_ft),
            md_to_ft=state.revealed_md_ft,
            interpretation_version_id=version.version_id,
            observations=f"Demo observation step {i + 1}",
            action="HOLD",
            risk_note="Demo run",
        )

    save_simulation_state(project_root, state)
    export_decision_log_csv(
        project_root,
        project_root / "exports" / "decision_log.csv",
        revealed_md_ft=state.revealed_md_ft,
        curves_used=config.curves_used,
        offsets_used=[w.name for w in project.wells if w.well_id != active_id],
        interpretation_delta_summary="Demo auto updates",
    )
    report_path = build_report(project_root)

    latest = get_latest_interpretation(project_root)
    kpi = compute_kpis(
        trajectory_df=trajectory,
        top_control_points=latest.top_control_points,
        base_control_points=latest.base_control_points,
        md_from_ft=config.start_md_ft,
        md_to_ft=state.revealed_md_ft,
        step_ft=1.0,
    )
    kpi_json = {
        "percent_in_zone": kpi.percent_in_zone,
        "avg_center_distance": kpi.avg_center_distance,
        "last_step_in_zone": kpi.last_step_in_zone,
    }
    (project_root / "exports" / "kpi_summary.json").write_text(json.dumps(kpi_json, indent=2), encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap a full end-to-end demo project and artifacts.")
    parser.add_argument("--project-root", type=Path, default=Path("data/demo_project"))
    parser.add_argument("--sample-root", type=Path, default=Path("data/sample_project"))
    parser.add_argument("--steps", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = bootstrap_demo_project(args.project_root, args.sample_root, steps=args.steps)
    print(f"Demo bootstrap complete. Report: {report}")


if __name__ == "__main__":
    main()

