from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.io.project_store import atomic_write_json, well_paths
from app.plot.steering import build_active_window_figure
from app.services.evaluation import evaluate_completed_run
from app.services.project_data import load_well_frames
from app.services.run_paths import run_root
from app.sim.sim_store import load_simulation_config, load_simulation_state
from tests.test_run_history import prepare_run


def test_future_records_cannot_change_operator_frames_or_plot_inputs(tmp_path: Path) -> None:
    root, config, _, _ = prepare_run(tmp_path)
    before = load_well_frames(root, config.active_well_id)
    state = load_simulation_state(root)
    paths = well_paths(root, config.active_well_id)
    for key in ("survey", "trajectory", "logs"):
        raw = pd.read_parquet(paths[key])
        future = raw.md_ft > state.revealed_md_ft
        for column in raw.columns:
            if column != "md_ft":
                raw.loc[future, column] = 999999.0
        raw.to_parquet(paths[key], index=False)
    atomic_write_json(paths["markers"], [{"marker_id": "future", "name": "Future contact", "md_ft": 6000.0}])
    after = load_well_frames(root, config.active_well_id)
    for key in ("survey", "trajectory", "logs"):
        pd.testing.assert_frame_equal(before[key], after[key])
        assert after[key].md_ft.max() <= state.revealed_md_ft
    assert after["markers"] == []
    figure = build_active_window_figure(after["logs"], state.revealed_md_ft, 500, ["GR", "RES"])
    assert all(max(trace.x) <= state.revealed_md_ft for trace in figure.data)
    offsets = load_well_frames(root, config.offset_well_ids[0])
    pd.testing.assert_frame_equal(offsets["logs"], pd.read_parquet(well_paths(root, config.offset_well_ids[0])["logs"]))


def test_truth_evaluation_is_blocked_before_complete(tmp_path: Path, monkeypatch) -> None:
    root, _, _, _ = prepare_run(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Private truth must not be read before completion")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="Complete"):
        evaluate_completed_run(root)


def test_replay_truth_snapshot_is_separate_from_operator_state(tmp_path: Path) -> None:
    root, config, _, _ = prepare_run(tmp_path)
    before = load_well_frames(root, config.active_well_id)
    truth_path = Path(load_simulation_config(root).hidden_truth_path)
    assert truth_path.is_relative_to(run_root(root))
    private = json.loads(truth_path.read_text())
    private["scenario"]["disturbance_height_ft"] = 500
    truth_path.write_text(json.dumps(private))
    after = load_well_frames(root, config.active_well_id)
    for key in ("trajectory", "logs"):
        pd.testing.assert_frame_equal(before[key], after[key])

def test_completed_replay_requires_captured_truth_even_with_known_version(tmp_path: Path) -> None:
    from app.services.evaluation import load_completed_scenario
    from app.services.runs import advance_run, initialize_run
    root, config, top, base = prepare_run(tmp_path)
    config = config.model_copy(update={"end_md_ft": 2100.0, "hidden_truth_path": None})
    initialize_run(root, config, top, base)
    advance_run(root, "HOLD", "Known version is metadata, not independent evaluation evidence")
    with pytest.raises(ValueError, match="no captured"):
        load_completed_scenario(root)


def test_completed_replay_rejects_tampered_truth_snapshot(tmp_path: Path) -> None:
    from app.services.evaluation import load_completed_scenario
    from app.services.runs import advance_run, initialize_run
    root, config, top, base = prepare_run(tmp_path)
    config = config.model_copy(update={"end_md_ft": 2100.0})
    initialize_run(root, config, top, base)
    advance_run(root, "HOLD", "Observed current layer position")
    truth_path = Path(load_simulation_config(root).hidden_truth_path)
    private = json.loads(truth_path.read_text())
    private["scenario"]["disturbance_height_ft"] += 10
    truth_path.write_text(json.dumps(private))
    with pytest.raises(ValueError, match="modified"):
        load_completed_scenario(root)
