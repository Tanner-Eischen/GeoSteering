"""Historical evidence is clipped to the selected decision, not current progress."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from app.io.project_store import atomic_write_json, read_json
from app.services.decision_review import list_review_steps, load_decision_review
from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.run_paths import active_run_id, run_root
from app.services.runs import fork_run, initialize_run
from tests.test_run_history import prepare_run


def record(root, run_id, *, action="HOLD", rationale="", update_bounds=None):
    view = load_operator_view(root, run_id)
    return submit_steering(root, run_id=run_id, expected_step_index=view["state"].step_index,
                           interpretation_version_id=view["interpretation"].version_id,
                           action=action, observations="Acquired observations support this decision",
                           rationale=rationale, update_bounds=update_bounds)


def normalize(value):
    if isinstance(value, pd.DataFrame):
        return value.to_json(orient="split", double_precision=15)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def file_snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_baseline_requires_explicit_run_and_is_read_only(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    selected = active_run_id(root)
    before = file_snapshot(root)
    assert list_review_steps(root, selected) == [{"step_index": 0, "md_from_ft": 2000, "md_to_ft": 2000}]
    view = load_decision_review(root, selected, 0)
    assert view["decision"] is None and view["metric"] is None
    assert view["interpretation"] == view["before_interpretation"]
    assert view["frames"]["logs"].md_ft.max() <= 2000
    for run_id, step, phase in [(None, 0, "decision"), (selected, True, "decision"), (selected, -1, "decision"),
                                 (selected, 1, "decision"), (selected, 0, "future")]:
        with pytest.raises(ValueError):
            load_decision_review(root, run_id, step, phase)
    assert file_snapshot(root) == before


def test_selected_revision_and_before_metrics_are_distinct_from_after_result(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    record(root, run_id)
    view = load_operator_view(root, run_id)
    last = view["frames"]["trajectory"].iloc[-1]
    record(root, run_id, action="BUILD", rationale="Observed boundary shift", update_bounds=(last.x_ft, 1430, 1454))
    before = load_decision_review(root, run_id, 2)
    after = load_decision_review(root, run_id, 2, "after")
    assert before["revealed_md_ft"] == 2100 and after["revealed_md_ft"] == 2200
    assert before["interpretation"].version_id == before["decision"]["interpretation_version_id"]
    assert before["interpretation"].rationale == "Observed boundary shift"
    assert before["before_interpretation"].version_id == before["metric"]["interpretation_version_id"]
    assert before["metric"]["step_index"] == 1
    assert after["metric"]["step_index"] == 2
    assert after["metric"]["interpretation_version_id"] == after["interpretation"].version_id
    assert before["decision"]["recommendation"]["action"] == "BUILD"
    assert "risk_note" not in before["decision"]
    for item in [before, after]:
        assert "observation" not in item["metric"].get("command_response", {})
        assert all(frame.md_ft.max() <= item["revealed_md_ft"] for frame in (
            item["frames"]["survey"], item["frames"]["trajectory"], item["frames"]["logs"]))


def test_old_payload_stays_unchanged_after_advances_and_future_poisoning(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    record(root, run_id)
    original = {phase: normalize(load_decision_review(root, run_id, 1, phase)) for phase in ("decision", "after")}
    record(root, run_id, action="DROP")
    scope = run_root(root, run_id)
    environment_path = scope / "environment/state.json"
    environment = read_json(environment_path)
    environment["logs"][-1]["GR"] = 123456789
    environment["trajectory"][-1]["tvd_ft"] = -123456789
    atomic_write_json(environment_path, environment)
    interpretation_path = scope / "interpretations/interpretations.json"
    interpretations = read_json(interpretation_path)
    interpretations[-1]["rationale"] = "FUTURE_SECRET_INTERPRETATION"
    interpretations[-1]["top_control_points"][0]["tvd_ft"] = -123456789
    atomic_write_json(interpretation_path, interpretations)
    metric_path = scope / "metrics.json"
    metrics = read_json(metric_path)
    metrics[-1]["percent_in_zone"] = 123456789
    atomic_write_json(metric_path, metrics)
    decisions_path = scope / "decisions/decisions.json"
    decisions = read_json(decisions_path)
    decisions[0]["risk_note"] = "FUTURE_SENSOR_SECRET"
    decisions[-1]["observations"] = "FUTURE_SECRET_EVIDENCE"
    atomic_write_json(decisions_path, decisions)
    for phase in ("decision", "after"):
        assert normalize(load_decision_review(root, run_id, 1, phase)) == original[phase]
    assert all(set(item) == {"step_index", "md_from_ft", "md_to_ft"} for item in list_review_steps(root, run_id))


def test_fork_and_other_active_run_do_not_change_explicit_selected_review(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    parent_id = active_run_id(root)
    record(root, parent_id)
    parent = normalize(load_decision_review(root, parent_id, 1))
    child = fork_run(root, parent_id)
    record(root, child.run_id, action="BUILD")
    initialize_run(root, config, top, base)
    assert normalize(load_decision_review(root, parent_id, 1)) == parent
    reviewed_child = load_decision_review(root, child.run_id, 2)
    assert reviewed_child["run"]["run_id"] == child.run_id
    assert reviewed_child["run"]["parent_run_id"] == parent_id
    assert reviewed_child["run"]["forked_at_step"] == 1


def test_partial_replay_interval_does_not_interpolate_against_a_future_station(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    state = initialize_run(root, config.model_copy(update={"step_size_ft": 25, "end_md_ft": 2025}), top, base)
    record(root, state.run_id)
    view = load_decision_review(root, state.run_id, 1, "after")
    assert view["revealed_md_ft"] == 2025
    assert view["frames"]["trajectory"].md_ft.max() == 2000
    assert not (view["frames"]["survey"].md_ft == 2025).any()


def test_marker_edits_after_run_do_not_rewrite_historical_evidence(tmp_path):
    root, config, _, _ = prepare_run(tmp_path)
    run_id = active_run_id(root)
    original = normalize(load_decision_review(root, run_id, 0))
    marker_path = root / "wells" / config.active_well_id / "markers.json"
    markers = read_json(marker_path, default=[])
    markers.append({"md_ft": 1000, "name": "FUTURE_EDIT"})
    atomic_write_json(marker_path, markers)
    assert normalize(load_decision_review(root, run_id, 0)) == original


def test_review_never_calls_truth_evaluation_or_samples_future_logs(tmp_path, monkeypatch):
    from app.services import evaluation
    from app.sim import environment

    root, _, _, _ = prepare_run(tmp_path, "causal")
    selected = active_run_id(root)
    record(root, selected)

    def forbidden(*args, **kwargs):
        pytest.fail("Historical review touched withheld truth or future sampling")

    monkeypatch.setattr(environment, "load_private_scenario", forbidden)
    monkeypatch.setattr(environment, "sample_station", forbidden)
    monkeypatch.setattr(evaluation, "evaluate_completed_run", forbidden)
    before = file_snapshot(root)
    for phase in ("decision", "after"):
        load_decision_review(root, selected, 1, phase)
    assert file_snapshot(root) == before


def test_selected_review_payload_does_not_expose_private_paths(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    selected = active_run_id(root)
    record(root, selected)
    payload = json.dumps(normalize(load_decision_review(root, selected, 1)), sort_keys=True)
    assert "hidden_truth_path" not in payload
    assert "risk_note" not in payload
    assert "\"observation\"" not in payload
