from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.io.project_store import create_project, load_project
from app.io.well_import import import_well_folder
from app.model.schemas import ControlPoint
from app.services.baseline import estimate_offset_baseline
from app.services.interpretations import get_latest_interpretation, load_interpretations
from app.services.project_data import load_well_frames
from app.services.run_metrics import load_run_metrics, save_metric_snapshot
from app.services.run_paths import run_root
from app.services.runs import advance_run, initialize_run
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import load_simulation_config, load_simulation_state
from tools.generate_sample_data import generate_sample_data


def prepare_run(tmp_path: Path, mode: str = "replay") -> tuple[Path, SimulationConfig, list, list]:
    sample = tmp_path / "sample"
    generate_sample_data(sample, seed=123)
    root = tmp_path / "project"
    create_project(root, "Run isolation")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(root, sample / "wells" / name, name)
    project = load_project(root)
    offsets = [well.well_id for well in project.wells if well.well_id != project.active_well_id]
    top, base, uncertainty = estimate_offset_baseline(root, offsets)
    config = SimulationConfig(
        mode=mode, active_well_id=project.active_well_id, offset_well_ids=offsets,
        start_md_ft=2000, end_md_ft=7000, lateral_start_md_ft=2000,
        scenario_version="structural_dip_01-v1", seed=123,
        hidden_truth_path=str((sample / "truth.json").resolve()),
    )
    initialize_run(root, config, top, base, uncertainty, hidden_truth_path=sample / "truth.json")
    return root, config, top, base


def test_new_run_preserves_previous_history_and_uses_own_baseline(tmp_path: Path) -> None:
    root, config, top, base = prepare_run(tmp_path)
    advance_run(root, "HOLD", "Observed landing interval agrees with offset estimate")
    first_id = load_simulation_state(root).run_id
    original = {str(path.relative_to(run_root(root))): path.read_bytes() for path in run_root(root).rglob("*.json")}
    changed_top = [ControlPoint(**{**point.model_dump(), "tvd_ft": point.tvd_ft + 10}) for point in top]
    changed_base = [ControlPoint(**{**point.model_dump(), "tvd_ft": point.tvd_ft + 10}) for point in base]
    second = initialize_run(root, config, changed_top, changed_base)
    assert second.run_id != first_id
    assert len(load_interpretations(root)) == 1
    assert get_latest_interpretation(root).top_control_points[0].tvd_ft == changed_top[0].tvd_ft
    assert len(load_run_metrics(root)) == 0
    assert len(load_run_metrics(root, first_id)) == 1
    for relative, content in original.items():
        assert (run_root(root, first_id) / relative).read_bytes() == content


def test_metrics_keep_original_version_and_value_when_interpretation_changes(tmp_path: Path) -> None:
    root, _, top, base = prepare_run(tmp_path)
    advance_run(root, "HOLD", "Landing log constrains current layer position")
    first = load_run_metrics(root)[0].copy()
    shifted_top = [ControlPoint(**{**point.model_dump(), "tvd_ft": point.tvd_ft + 500}) for point in top]
    shifted_base = [ControlPoint(**{**point.model_dump(), "tvd_ft": point.tvd_ft + 500}) for point in base]
    advance_run(root, "DROP", "Testing an explicitly shifted interpretation", top_control_points=shifted_top, base_control_points=shifted_base)
    metrics = load_run_metrics(root)
    assert metrics[0] == first
    assert metrics[0]["percent_in_zone"] > 99
    assert metrics[1]["percent_in_zone"] == 0
    assert metrics[0]["interpretation_version_id"] != metrics[1]["interpretation_version_id"]
    assert metrics[1]["evaluated_length_ft"] == 200
    with pytest.raises(ValueError, match="already exists"):
        save_metric_snapshot(root, {**first, "percent_in_zone": 5})


def test_advance_requires_evidence_and_validates_before_writing_history(tmp_path: Path) -> None:
    root, _, top, base = prepare_run(tmp_path)
    with pytest.raises(ValueError, match="evidence"):
        advance_run(root, "HOLD", " ")
    with pytest.raises(ValueError):
        advance_run(root, "TURN", "Observed logs")
    with pytest.raises(ValueError):
        advance_run(root, "HOLD", "Observed logs", top_control_points=base, base_control_points=top)
    assert load_simulation_state(root).step_index == 0
    assert len(load_interpretations(root)) == 1
    assert not load_run_metrics(root)


def test_persisted_causal_actions_change_future_positions_and_logs(tmp_path: Path) -> None:
    root, config, top, base = prepare_run(tmp_path, "causal")
    advance_run(root, "BUILD", "Observed layer above current position", target_inc_deg=180)
    build_id = load_simulation_state(root).run_id
    build_frames = load_well_frames(root, config.active_well_id)
    response = load_run_metrics(root)[0]["command_response"]
    assert response["clipped"]
    assert build_frames["trajectory"].iloc[-1].dls_deg_per_100ft <= 3.0 + 1e-8
    initialize_run(root, config, top, base)
    advance_run(root, "DROP", "Observed layer below current position")
    drop_frames = load_well_frames(root, config.active_well_id)
    assert build_frames["trajectory"].iloc[-1].tvd_ft != pytest.approx(drop_frames["trajectory"].iloc[-1].tvd_ft)
    assert build_frames["logs"].iloc[-1].GR != pytest.approx(drop_frames["logs"].iloc[-1].GR)
    pd.testing.assert_frame_equal(build_frames["trajectory"], load_well_frames(root, config.active_well_id, run_id=build_id)["trajectory"])
    assert load_simulation_config(root).mode == "causal"


def test_causal_sensor_does_not_use_interpretation(tmp_path: Path) -> None:
    root, config, top, base = prepare_run(tmp_path, "causal")
    shifted_top = [ControlPoint(**{**point.model_dump(), "tvd_ft": point.tvd_ft + 500}) for point in top]
    shifted_base = [ControlPoint(**{**point.model_dump(), "tvd_ft": point.tvd_ft + 500}) for point in base]
    advance_run(root, "HOLD", "Same command, altered interpretation", top_control_points=shifted_top, base_control_points=shifted_base)
    altered = load_well_frames(root, config.active_well_id)
    initialize_run(root, config, top, base)
    advance_run(root, "HOLD", "Same command, original interpretation")
    original = load_well_frames(root, config.active_well_id)
    for key in ("trajectory", "logs"):
        pd.testing.assert_frame_equal(altered[key], original[key])


def test_replay_configuration_rejects_nonpositive_or_nonfinite_steps() -> None:
    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            SimulationConfig(active_well_id="a", end_md_ft=1000, step_size_ft=value)

def test_causal_fork_preserves_prefix_and_supports_counterfactual(tmp_path: Path) -> None:
    from app.io.project_store import atomic_write_json, read_json
    from app.services.runs import fork_run
    root, config, _, _ = prepare_run(tmp_path, "causal")
    advance_run(root, "HOLD", "Observed landing log")
    original_id = load_simulation_state(root).run_id
    original_metrics = load_run_metrics(root)
    prefix = load_well_frames(root, config.active_well_id)["trajectory"]
    fork = fork_run(root)
    assert fork.run_id != original_id
    pd.testing.assert_frame_equal(prefix, load_well_frames(root, config.active_well_id)["trajectory"])
    assert Path(load_simulation_config(root).hidden_truth_path).is_relative_to(run_root(root))
    advance_run(root, "BUILD", "Compare build from same acquired state")
    built = load_well_frames(root, config.active_well_id)["trajectory"].iloc[-1]
    assert load_run_metrics(root, original_id) == original_metrics
    assert read_json(run_root(root) / "manifest.json")["parent_run_id"] == original_id
    atomic_write_json(root / "active_run.json", {"run_id": original_id})
    advance_run(root, "DROP", "Compare drop from same acquired state")
    dropped = load_well_frames(root, config.active_well_id)["trajectory"].iloc[-1]
    assert built.tvd_ft < dropped.tvd_ft
    assert load_run_metrics(root)[0] == original_metrics[0]

def test_causal_default_requires_explicit_selection(tmp_path: Path) -> None:
    root, config, top, base = prepare_run(tmp_path, "causal")
    previous_id = load_simulation_state(root).run_id
    config = config.model_copy(update={"hidden_truth_path": None})
    with pytest.raises(ValueError, match="explicit selection"):
        initialize_run(root, config, top, base)
    assert load_simulation_state(root).run_id == previous_id
    selected = initialize_run(root, config.model_copy(update={"use_default_synthetic_scenario": True}), top, base)
    assert selected.run_id != previous_id
    assert Path(load_simulation_config(root).hidden_truth_path).is_file()
