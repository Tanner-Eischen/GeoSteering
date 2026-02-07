from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.alg.kpi import compute_kpis
from app.io.project_store import create_project, load_project
from app.io.well_import import import_well_folder
from app.model.schemas import ControlPoint
from app.services.decisions import create_decision, load_decisions
from app.services.interpretations import (
    create_baseline_interpretation,
    create_interpretation_version,
    get_latest_interpretation,
)
from app.services.project_data import load_well_frames
from app.sim.engine import initial_state, step_forward
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import (
    load_simulation_config,
    load_simulation_state,
    save_simulation_config,
    save_simulation_state,
)
from tools.generate_sample_data import generate_sample_data


def _setup_project(tmp_path: Path) -> tuple[Path, dict]:
    sample_root = tmp_path / "sample"
    generate_sample_data(sample_root, seed=123)
    truth = json.loads((sample_root / "truth.json").read_text(encoding="utf-8"))

    project_root = tmp_path / "project"
    create_project(project_root, "Sim")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(project_root, sample_root / "wells" / name, name)
    return project_root, truth


def test_e1_deterministic_stepping(tmp_path: Path) -> None:
    project_root, _ = _setup_project(tmp_path)
    project = load_project(project_root)
    active_id = next(w.well_id for w in project.wells if w.name == "active_01")
    active_logs = load_well_frames(project_root, active_id)["logs"]

    config = SimulationConfig(
        active_well_id=active_id,
        offset_well_ids=[],
        curves_used=["GR", "RES"],
        step_size_ft=100.0,
        window_size_ft=500.0,
        start_md_ft=float(active_logs["md_ft"].min()),
        end_md_ft=float(active_logs["md_ft"].max()),
    )
    save_simulation_config(project_root, config)
    state = initial_state(config)
    save_simulation_state(project_root, state)

    for _ in range(5):
        state = step_forward(state, config)
    save_simulation_state(project_root, state)

    reloaded_config = load_simulation_config(project_root)
    reloaded_state = load_simulation_state(project_root)
    assert reloaded_config.model_dump() == config.model_dump()
    assert reloaded_state.revealed_md_ft == state.revealed_md_ft
    assert reloaded_state.step_index == 5


def test_e2_interpretation_version_creation(tmp_path: Path) -> None:
    project_root, _ = _setup_project(tmp_path)
    project = load_project(project_root)
    active_id = next(w.well_id for w in project.wells if w.name == "active_01")
    trajectory = load_well_frames(project_root, active_id)["trajectory"]
    md_min, md_max = float(trajectory["md_ft"].min()), float(trajectory["md_ft"].max())
    center = [
        float(trajectory["tvd_ft"].iloc[0]),
        float(trajectory["tvd_ft"].iloc[-1]),
    ]
    baseline = create_baseline_interpretation(
        project_root,
        top_control_points=[ControlPoint(md_ft=md_min, tvd_ft=center[0] - 10), ControlPoint(md_ft=md_max, tvd_ft=center[1] - 10)],
        base_control_points=[ControlPoint(md_ft=md_min, tvd_ft=center[0] + 10), ControlPoint(md_ft=md_max, tvd_ft=center[1] + 10)],
    )
    new_version = create_interpretation_version(
        project_root,
        step_index=1,
        rationale="Adjusted top based on GR shift",
        top_control_points=baseline.top_control_points,
        base_control_points=baseline.base_control_points,
    )
    assert new_version.derived_from_version_id == baseline.version_id
    assert new_version.rationale


def test_e3_decision_links_interpretation_version(tmp_path: Path) -> None:
    project_root, _ = _setup_project(tmp_path)
    project = load_project(project_root)
    active_id = next(w.well_id for w in project.wells if w.name == "active_01")
    trajectory = load_well_frames(project_root, active_id)["trajectory"]
    md_min, md_max = float(trajectory["md_ft"].min()), float(trajectory["md_ft"].max())
    baseline = create_baseline_interpretation(
        project_root,
        top_control_points=[ControlPoint(md_ft=md_min, tvd_ft=1250.0), ControlPoint(md_ft=md_max, tvd_ft=1250.0)],
        base_control_points=[ControlPoint(md_ft=md_min, tvd_ft=1270.0), ControlPoint(md_ft=md_max, tvd_ft=1270.0)],
    )
    decision = create_decision(
        project_root,
        step_index=1,
        md_from_ft=1000.0,
        md_to_ft=1100.0,
        interpretation_version_id=baseline.version_id,
        observations="Hold angle",
        action="HOLD",
    )
    decisions = load_decisions(project_root)
    assert any(d.decision_id == decision.decision_id for d in decisions)
    assert decisions[-1].interpretation_version_id == baseline.version_id


def test_e4_kpi_against_synthetic_truth(tmp_path: Path) -> None:
    project_root, truth = _setup_project(tmp_path)
    project = load_project(project_root)
    active_id = next(w.well_id for w in project.wells if w.name == "active_01")
    trajectory = load_well_frames(project_root, active_id)["trajectory"]

    top_points = [ControlPoint.model_validate(cp) for cp in truth["zone_model"]["top_control_points"]]
    base_points = [ControlPoint.model_validate(cp) for cp in truth["zone_model"]["base_control_points"]]
    kpi = compute_kpis(
        trajectory_df=trajectory,
        top_control_points=top_points,
        base_control_points=base_points,
        md_from_ft=float(trajectory["md_ft"].min()),
        md_to_ft=float(trajectory["md_ft"].max()),
        step_ft=0.5,
    )
    expected = float(truth["expected_baseline_kpis"]["active_01"]["percent_in_zone"])
    assert abs(kpi.percent_in_zone - expected) < 2.0


def test_can_complete_10_step_run_with_versions_and_decisions(tmp_path: Path) -> None:
    project_root, _ = _setup_project(tmp_path)
    project = load_project(project_root)
    active_id = next(w.well_id for w in project.wells if w.name == "active_01")
    active_logs = load_well_frames(project_root, active_id)["logs"]
    trajectory = load_well_frames(project_root, active_id)["trajectory"]
    md_min, md_max = float(trajectory["md_ft"].min()), float(trajectory["md_ft"].max())

    baseline = create_baseline_interpretation(
        project_root,
        top_control_points=[ControlPoint(md_ft=md_min, tvd_ft=1250.0), ControlPoint(md_ft=md_max, tvd_ft=1250.0)],
        base_control_points=[ControlPoint(md_ft=md_min, tvd_ft=1270.0), ControlPoint(md_ft=md_max, tvd_ft=1270.0)],
    )
    config = SimulationConfig(
        active_well_id=active_id,
        offset_well_ids=[],
        curves_used=["GR", "RES"],
        step_size_ft=100.0,
        window_size_ft=500.0,
        start_md_ft=float(active_logs["md_ft"].min()),
        end_md_ft=float(active_logs["md_ft"].max()),
    )
    state = initial_state(config)
    for step in range(10):
        state = step_forward(state, config)
        v = create_interpretation_version(
            project_root,
            step_index=step + 1,
            rationale=f"step {step + 1} update",
            top_control_points=baseline.top_control_points,
            base_control_points=baseline.base_control_points,
        )
        create_decision(
            project_root,
            step_index=step + 1,
            md_from_ft=max(config.start_md_ft, state.revealed_md_ft - config.step_size_ft),
            md_to_ft=state.revealed_md_ft,
            interpretation_version_id=v.version_id,
            observations="demo step",
            action="HOLD",
        )
    assert state.step_index == 10
    assert len(load_decisions(project_root)) == 10
