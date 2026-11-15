from __future__ import annotations

import base64
import json

import pandas as pd
import pytest

from app.io.project_store import atomic_write_json, read_json, well_paths
from app.services import runs
from app.services.decision_review import load_decision_review
from app.services.operator_workflow import load_operator_view
from app.services.run_paths import active_run_id, run_root
from app.services.runs import advance_run, fork_run, initialize_run
from app.services.uncertainty import _measurement, load_uncertainty_snapshot
from app.uncertainty.models import EnsembleSettings
from tests.test_run_history import prepare_run


def files(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def opted_in(root, config, top, base, **changes):
    configured = config.model_copy(update={"ensemble_settings": EnsembleSettings(member_count=32), **changes})
    state = initialize_run(root, configured, top, base)
    return configured, state.run_id


def request(root, run_id, **changes):
    return {"run_id": run_id, "expected_step_index": load_operator_view(root, run_id)["state"].step_index,
            "request_id": f"test-{load_operator_view(root, run_id)['state'].step_index}",
            "action": "HOLD", "observations": "Acquired synthetic signal supports the recorded bounded command", **changes}


def test_disabled_runs_stay_unchanged_and_do_not_create_ensemble_files(tmp_path):
    root, _, _, _ = prepare_run(tmp_path)
    run_id = active_run_id(root)
    before = files(root)
    assert load_uncertainty_snapshot(root, run_id) is None
    assert load_operator_view(root, run_id)["uncertainty"] is None
    assert files(root) == before
    advance_run(root, **request(root, run_id))
    assert not (root / "runs" / run_id / "uncertainty").exists()


def test_prior_snapshot_is_deterministic_and_pinned_to_original_baseline(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    _, first_id = opted_in(root, config, top, base)
    _, second_id = opted_in(root, config, top, base)
    first, second = (load_uncertainty_snapshot(root, run_id) for run_id in (first_id, second_id))
    assert first == second
    assert first["step_index"] == 0 and first["revealed_md_ft"] == 2000
    assert first["measurement"]["md_ft"] == 2000
    assert first["observation_status"] == "updated"
    assert len(first["ensemble"]["members"]) == 32
    manifest = read_json(root / "runs" / first_id / "manifest.json")
    assert manifest["ensemble"]["settings_sha256"] == first["settings_sha256"]
    assert "inputs/ensemble_settings.json" in manifest["input_hashes"]
    baseline = read_json(root / "runs" / first_id / "inputs" / "ensemble_settings.json")["baseline"]
    assert baseline["top_control_points"] == [point.model_dump(mode="json") for point in top]


def test_original_log_pose_uses_only_acquired_survey_brackets():
    frames = {"trajectory": pd.DataFrame({"md_ft": [100, 200, 300], "x_ft": [5, 105, 999999],
                                          "tvd_ft": [1000, 1010, -999999]}),
              "logs": pd.DataFrame({"md_ft": [199.5, 201, 300], "GR": [81, 999999, 999999]})}
    station, measurement, status = _measurement(frames, 200)
    assert station["md_ft"] == 200 and status == "ready"
    assert measurement["md_ft"] == 199.5
    assert measurement["x_ft"] == pytest.approx(104.5)
    assert measurement["tvd_ft"] == pytest.approx(1009.95)
    assert measurement["GR"] == 81


def test_no_future_survey_is_used_to_locate_an_unbracketed_log():
    frames = {"trajectory": pd.DataFrame({"md_ft": [100, 200], "x_ft": [5, 105], "tvd_ft": [1000, 1010]}),
              "logs": pd.DataFrame({"md_ft": [150], "GR": [81]})}
    station, measurement, status = _measurement(frames, 150)
    assert station["md_ft"] == 100 and measurement is None and status == "no_acquired_gr"


def test_future_logs_and_private_field_do_not_affect_initial_ensemble(tmp_path, monkeypatch):
    root, config, top, base = prepare_run(tmp_path)
    _, first_id = opted_in(root, config, top, base)
    first = load_uncertainty_snapshot(root, first_id)
    path = well_paths(root, config.active_well_id)["logs"]
    logs = pd.read_parquet(path)
    logs.loc[logs.md_ft > 2000, "GR"] = 999999
    logs.to_parquet(path, index=False)
    from app.geo import formation
    from app.sim import environment
    monkeypatch.setattr(formation, "formation_top_base", lambda *a, **kw: pytest.fail("Ensemble read geological truth"))
    monkeypatch.setattr(environment, "load_private_scenario", lambda *a, **kw: pytest.fail("Ensemble loaded private field"))
    _, second_id = opted_in(root, config, top, base)
    assert load_uncertainty_snapshot(root, second_id) == first
    assert load_operator_view(root, first_id)["uncertainty"] == first


def test_manual_interpretation_revision_does_not_reset_or_feed_the_ensemble(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    _, altered_id = opted_in(root, config, top, base)
    shifted_top = [point.model_copy(update={"tvd_ft": point.tvd_ft + 100}) for point in top]
    shifted_base = [point.model_copy(update={"tvd_ft": point.tvd_ft + 100}) for point in base]
    advance_run(root, **request(root, altered_id, top_control_points=shifted_top, base_control_points=shifted_base))
    altered = load_uncertainty_snapshot(root, altered_id)
    _, control_id = opted_in(root, config, top, base)
    advance_run(root, **request(root, control_id))
    control = load_uncertainty_snapshot(root, control_id)
    assert altered == control


def test_historical_reviews_select_before_or_after_snapshot_without_rewriting(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    _, run_id = opted_in(root, config, top, base)
    original = load_uncertainty_snapshot(root, run_id)
    advance_run(root, **request(root, run_id))
    first = load_uncertainty_snapshot(root, run_id)
    advance_run(root, **request(root, run_id))
    before = files(root)
    assert load_decision_review(root, run_id, 2, "decision")["uncertainty"] == first
    assert load_decision_review(root, run_id, 2, "after")["uncertainty"]["step_index"] == 2
    assert load_uncertainty_snapshot(root, run_id, 0) == original
    assert files(root) == before


def test_fork_copies_prefix_and_child_update_preserves_parent(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    _, parent_id = opted_in(root, config, top, base)
    advance_run(root, **request(root, parent_id))
    original = files(root / "runs" / parent_id)
    child = fork_run(root, parent_id)
    assert load_uncertainty_snapshot(root, child.run_id) == load_uncertainty_snapshot(root, parent_id)
    advance_run(root, **request(root, child.run_id, action="BUILD", target_inc_deg=180))
    assert load_uncertainty_snapshot(root, child.run_id)["step_index"] == 2
    assert load_uncertainty_snapshot(root, parent_id)["step_index"] == 1
    assert files(root / "runs" / parent_id) == original


def test_failed_step_rolls_back_new_snapshot_pointer_environment_and_history(tmp_path, monkeypatch):
    root, config, top, base = prepare_run(tmp_path, "causal")
    _, run_id = opted_in(root, config, top, base)
    payload = request(root, run_id)
    scope = run_root(root, run_id)
    before = files(scope)
    with monkeypatch.context() as patch:
        patch.setattr(runs, "save_simulation_state", lambda *a, **kw: (_ for _ in ()).throw(OSError("interrupted write")))
        with pytest.raises(OSError, match="interrupted"):
            advance_run(root, **payload)
    assert files(scope) == before
    assert not (scope / "uncertainty" / "steps" / "00000001.json").exists()
    advance_run(root, **payload)
    assert load_uncertainty_snapshot(root, run_id)["step_index"] == 1


def test_interrupted_transaction_recovers_snapshot_file_and_pointer(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    _, run_id = opted_in(root, config, top, base)
    scope = run_root(root, run_id)
    original = load_uncertainty_snapshot(root, run_id)
    pointer = scope / "uncertainty" / "state.json"
    atomic_write_json(scope / "pending_step.json", {"status": "pending", "files": {
        "uncertainty/state.json": base64.b64encode(pointer.read_bytes()).decode("ascii"),
        "uncertainty/steps/00000001.json": None,
    }})
    atomic_write_json(pointer, {"step_index": 1, "invalid": "interrupted pointer"})
    atomic_write_json(scope / "uncertainty" / "steps" / "00000001.json", {"invalid": "interrupted new snapshot"})
    assert load_uncertainty_snapshot(root, run_id) == original
    assert not (scope / "uncertainty" / "steps" / "00000001.json").exists()
    assert not (scope / "pending_step.json").exists()


def test_identical_retry_returns_receipt_without_assimilating_twice(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    _, run_id = opted_in(root, config, top, base)
    payload = request(root, run_id)
    first = advance_run(root, **payload)
    before = files(root)
    assert advance_run(root, **payload) == first
    assert files(root) == before
    assert load_uncertainty_snapshot(root, run_id)["step_index"] == 1


def test_replay_partial_interval_does_not_reuse_log_or_future_survey(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    _, run_id = opted_in(root, config, top, base, step_size_ft=25)
    first = load_uncertainty_snapshot(root, run_id)
    advance_run(root, **request(root, run_id))
    pending = load_uncertainty_snapshot(root, run_id)
    assert pending["revealed_md_ft"] == 2025
    assert pending["acquired_station"]["md_ft"] == 2000
    assert pending["observation_status"] == "already_assimilated"
    assert pending["ensemble"] == first["ensemble"]
    advance_run(root, **request(root, run_id))
    updated = load_uncertainty_snapshot(root, run_id)
    assert updated["measurement"]["md_ft"] == 2050
    assert updated["ensemble"]["last_observation_md_ft"] == 2050


def test_missing_gr_propagates_without_likelihood_or_nonfinite_json(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    path = well_paths(root, config.active_well_id)["logs"]
    logs = pd.read_parquet(path)
    logs.loc[logs.md_ft == 2100, "GR"] = float("nan")
    logs.to_parquet(path, index=False)
    _, run_id = opted_in(root, config, top, base)
    advance_run(root, **request(root, run_id))
    snapshot = load_uncertainty_snapshot(root, run_id)
    assert snapshot["observation_status"] == "prediction_only"
    assert snapshot["measurement"]["GR"] is None
    assert snapshot["ensemble"]["last_observation_md_ft"] == 2100
    json.dumps(snapshot, allow_nan=False)


def test_forward_station_without_new_gr_predicts_without_relabeling_old_log(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    path = well_paths(root, config.active_well_id)["logs"]
    logs = pd.read_parquet(path)
    logs = logs.loc[~((logs.md_ft > 2000) & (logs.md_ft <= 2050))]
    logs.to_parquet(path, index=False)
    _, run_id = opted_in(root, config, top, base, step_size_ft=50)
    first = load_uncertainty_snapshot(root, run_id)
    advance_run(root, **request(root, run_id))
    prediction = load_uncertainty_snapshot(root, run_id)
    assert prediction["observation_status"] == "prediction_only_no_new_gr"
    assert prediction["measurement"] is None
    assert prediction["ensemble"]["x_ft"] > first["ensemble"]["x_ft"]
    assert prediction["ensemble"]["last_observation_md_ft"] == 2050
    assert prediction["acquired_station"]["md_ft"] == 2050


def test_stationary_x_with_new_md_is_not_assimilated_as_forward_geometry(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    _, run_id = opted_in(root, config, top, base, start_md_ft=100, lateral_start_md_ft=100)
    first = load_uncertainty_snapshot(root, run_id)
    advance_run(root, **request(root, run_id))
    stationary = load_uncertainty_snapshot(root, run_id)
    assert stationary["measurement"]["md_ft"] == 200
    assert stationary["observation_status"] == "non_forward_observation"
    assert stationary["ensemble"] == first["ensemble"]


def test_old_run_cannot_be_enabled_by_editing_config_without_frozen_inputs(tmp_path):
    root, _, _, _ = prepare_run(tmp_path)
    run_id = active_run_id(root)
    path = root / "runs" / run_id / "simulations" / "simulation_config.json"
    config = read_json(path)
    config["ensemble_settings"] = EnsembleSettings(member_count=32).model_dump(mode="json")
    atomic_write_json(path, config)
    before = files(root)
    with pytest.raises(ValueError, match="Initialize a new opted-in run"):
        load_uncertainty_snapshot(root, run_id)
    assert files(root) == before


def test_unknown_sensor_calibration_rejected_before_creating_a_run(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    before = files(root)
    with pytest.raises(ValueError, match="synthetic GR calibration"):
        opted_in(root, config, top, base, scenario_version="real-las-v1")
    assert files(root) == before


def test_changed_run_seed_does_not_silently_reinterpret_saved_particles(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    _, run_id = opted_in(root, config, top, base)
    path = root / "runs" / run_id / "simulations" / "simulation_config.json"
    saved = read_json(path)
    saved["seed"] += 1
    atomic_write_json(path, saved)
    before = files(root)
    with pytest.raises(ValueError, match="seed differs"):
        load_uncertainty_snapshot(root, run_id)
    assert files(root) == before


@pytest.mark.parametrize("target", ("snapshot", "settings"))
def test_changed_ensemble_artifacts_fail_without_regeneration(tmp_path, target):
    root, config, top, base = prepare_run(tmp_path)
    _, run_id = opted_in(root, config, top, base)
    scope = run_root(root, run_id)
    path = scope / ("uncertainty/steps/00000000.json" if target == "snapshot" else "inputs/ensemble_settings.json")
    payload = read_json(path)
    if target == "snapshot":
        payload["ensemble"]["members"][0]["center_tvd_ft"] += 100
    else:
        payload["settings"]["member_count"] = 64
    atomic_write_json(path, payload)
    before = files(root)
    with pytest.raises(ValueError, match="changed|different|match"):
        load_uncertainty_snapshot(root, run_id)
    assert files(root) == before
