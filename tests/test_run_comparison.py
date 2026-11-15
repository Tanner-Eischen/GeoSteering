from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.io.project_store import atomic_write_json, read_json
from app.services import evaluation
from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.run_comparison import compare_runs, list_run_catalog
from app.services.run_paths import active_run_id, run_root
from app.services.runs import fork_run, initialize_run
from tests.test_run_history import prepare_run


def advance(root, run_id, action="HOLD", **updates):
    view = load_operator_view(root, run_id)
    return submit_steering(
        root, run_id=run_id, expected_step_index=view["state"].step_index,
        interpretation_version_id=view["interpretation"].version_id,
        action=action, observations=f"Acquired evidence supports {action}", **updates,
    )


def branch_pair(tmp_path, mode="causal", end_md=2300):
    root, config, top, base = prepare_run(tmp_path, mode)
    parent = initialize_run(root, config.model_copy(update={"end_md_ft": end_md}), top, base)
    advance(root, parent.run_id)
    before = snapshot(run_root(root, parent.run_id))
    child = fork_run(root, parent.run_id)
    assert snapshot(run_root(root, parent.run_id)) == before
    return root, parent.run_id, child.run_id


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_catalog_exposes_fork_relationship_and_preserves_parent(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    before = snapshot(root)
    rows = {row["run_id"]: row for row in list_run_catalog(root)}
    assert rows[child]["parent_run_id"] == parent
    assert rows[child]["forked_at_step"] == 1
    assert rows[child]["family_root_id"] == parent
    assert rows[child]["depth"] == 1
    assert "fork of" in rows[child]["label"]
    assert rows[parent]["status"] == "In progress"
    assert snapshot(root) == before


def test_partial_comparison_clips_advanced_branch_and_uses_historical_metric(tmp_path, monkeypatch):
    root, parent, child = branch_pair(tmp_path)
    advance(root, parent, "BUILD")
    advance(root, child, "DROP")
    common_snapshot = read_json(run_root(root, parent) / "metrics.json")[-1]
    advance(root, parent, "HOLD")
    assert load_operator_view(root, parent)["state"].complete
    # A completed branch's saved outcome must not be loaded into a partial pair.
    atomic_write_json(run_root(root, parent) / "evaluation/replay.json", {"secret_future_outcome": 9999})
    before = snapshot(root)
    monkeypatch.setattr(evaluation, "evaluate_completed_run", lambda *a, **kw: pytest.fail("Partial comparison evaluated truth"))
    from app.sim import environment
    monkeypatch.setattr(environment, "load_private_scenario", lambda *a, **kw: pytest.fail("Partial comparison loaded private truth"))
    result = compare_runs(root, parent, child)
    assert result["truth_evaluation"] is None
    assert not result["both_complete"]
    assert "secret_future_outcome" not in json.dumps(result)
    assert result["interval"] == {"start_md_ft": 2000, "end_md_ft": 2200, "evaluated_length_ft": 200, "branch_start_md_ft": 2100}
    assert result["runs"]["left"]["estimated_snapshot"] == {key: value for key, value in common_snapshot.items() if key != "command_response"}
    for side in ("left", "right"):
        assert max(row["md_ft"] for row in result["runs"][side]["trajectory"]) == 2200
        assert max(row["md_ft"] for row in result["runs"][side]["logs"]) == 2200
        assert all(row["md_to_ft"] <= 2200 for row in result["runs"][side]["decisions"])
    assert result["differences"]["command_rows"][0]["left"]["action"] == "BUILD"
    assert result["differences"]["command_rows"][0]["right"]["action"] == "DROP"
    assert snapshot(root) == before
    with pytest.raises(ValueError, match="Complete both branches"):
        compare_runs(root, parent, child, evaluate=True)


def test_completed_evaluation_is_explicit_deterministic_and_uses_one_denominator(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    for run_id, action in ((parent, "BUILD"), (child, "DROP")):
        advance(root, run_id, action)
        advance(root, run_id, action)
    before = snapshot(root)
    assert compare_runs(root, parent, child)["truth_evaluation"] is None
    result = compare_runs(root, parent, child, evaluate=True)
    assert result == compare_runs(root, parent, child, evaluate=True)
    assert result["interval"]["evaluated_length_ft"] == 300
    truth = result["truth_evaluation"]
    assert truth["left"]["metrics"]["evaluated_length_ft"] == truth["right"]["metrics"]["evaluated_length_ft"] == 300
    assert truth["differences"]["percent_in_zone"] == pytest.approx(truth["right"]["metrics"]["percent_in_zone"] - truth["left"]["metrics"]["percent_in_zone"])
    assert snapshot(root) == before


@pytest.mark.parametrize("field,value", [("seed", 999), ("active_well_id", "different"), ("step_size_ft", 50), ("end_md_ft", 2400), ("max_dls_deg_per_100ft", 1)])
def test_configuration_changes_reject_false_controlled_comparisons(tmp_path, field, value):
    root, parent, child = branch_pair(tmp_path)
    path = run_root(root, child) / "simulations/simulation_config.json"
    payload = read_json(path)
    payload[field] = value
    atomic_write_json(path, payload)
    with pytest.raises((ValueError, FileNotFoundError), match="(configurations differ|different|No such file|system cannot find)"):
        compare_runs(root, parent, child)


def test_other_family_same_seed_and_scenario_is_rejected(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    first = active_run_id(root)
    second = initialize_run(root, config, top, base)
    with pytest.raises(ValueError, match="same fork family"):
        compare_runs(root, first, second.run_id)
    with pytest.raises(ValueError, match="different saved runs"):
        compare_runs(root, first, first)


@pytest.mark.parametrize("mode", ["field", "source", "inputs", "mechanics", "baseline", "prefix"])
def test_fairness_rejects_changed_field_source_evidence_mechanics_and_prefix(tmp_path, mode):
    root, parent, child = branch_pair(tmp_path)
    scope = run_root(root, child)
    if mode == "field":
        path = scope / "environment/provenance.json"
        payload = read_json(path)
        payload["private_scenario_sha256"] = "other-field"
    elif mode == "source":
        path = scope / "manifest.json"
        payload = read_json(path)
        payload["code_provenance"]["source_fingerprint"] = "other-source"
    elif mode == "inputs":
        path = next((scope / "inputs").rglob("markers.json"))
        payload = [{"changed": True}]
    elif mode == "mechanics":
        path = scope / "environment/mechanics.json"
        payload = read_json(path)
        payload["max_dls_deg_per_100ft"] = 1.0
    elif mode == "baseline":
        path = scope / "interpretations/interpretations.json"
        payload = read_json(path)
        payload[0]["top_control_points"][0]["tvd_ft"] += 2
    else:
        path = scope / "environment/state.json"
        payload = read_json(path)
        payload["logs"][-1]["GR"] += 10
    atomic_write_json(path, payload)
    with pytest.raises(ValueError, match="(different|changed|same acquired)"):
        compare_runs(root, parent, child)


def test_siblings_and_nested_forks_find_the_correct_common_prefix(tmp_path):
    root, parent, first = branch_pair(tmp_path)
    advance(root, parent)
    second = fork_run(root, parent).run_id
    result = compare_runs(root, first, second)
    assert result["relationship"]["common_prefix_step"] == 1
    assert result["interval"]["end_md_ft"] == 2100
    nested = fork_run(root, second).run_id
    result = compare_runs(root, parent, nested)
    assert result["relationship"]["common_prefix_step"] == 2


def test_missing_common_metric_is_unavailable_instead_of_recomputed(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    advance(root, parent, "BUILD")
    advance(root, child, "DROP")
    # Only post-fork row is absent. The verified shared prefix is preserved.
    path = run_root(root, parent) / "metrics.json"
    atomic_write_json(path, read_json(path)[:1])
    result = compare_runs(root, parent, child)
    assert result["runs"]["left"]["estimated_snapshot"] is None
    assert result["runs"]["right"]["estimated_snapshot"] is not None
    assert result["differences"]["estimated_percent_in_zone_pp"] is None


def test_replay_reports_its_fixed_path_semantics(tmp_path):
    root, parent, child = branch_pair(tmp_path, mode="replay")
    advance(root, parent, "BUILD")
    advance(root, child, "DROP")
    result = compare_runs(root, parent, child)
    assert result["differences"]["endpoint_tvd_ft"] == 0
    assert any("fixed recorded path" in note for note in result["notes"])


def test_ordered_locks_allow_opposite_selection_order_without_deadlock(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    started = threading.Barrier(2)

    def compare(a, b):
        started.wait(timeout=5)
        return compare_runs(root, a, b)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(compare, parent, child)
        b = pool.submit(compare, child, parent)
        assert a.result(timeout=10)["interval"] == b.result(timeout=10)["interval"]


def test_changed_frozen_input_fingerprint_is_checked_against_actual_bytes(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    scope = run_root(root, child)
    manifest_path = scope / "manifest.json"
    manifest = read_json(manifest_path)
    name = next(iter(manifest["input_hashes"]))
    assert hashlib.sha256((scope / name).read_bytes()).hexdigest() == manifest["input_hashes"][name]
    manifest["input_hashes"][name] = "not-the-file-hash"
    atomic_write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="inputs changed"):
        compare_runs(root, parent, child)


def test_comparison_export_excludes_unacquired_rows_and_raw_metric_payloads(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    advance(root, parent, "BUILD")
    advance(root, child, "DROP")
    scope = run_root(root, parent)
    metric_path = scope / "metrics.json"
    metrics = read_json(metric_path)
    metrics[-1]["raw_future_payload"] = "future-secret-sentinel"
    metrics[-1]["command_response"]["observation"] = {"md_ft": 9999, "GR": "future-secret-sentinel"}
    atomic_write_json(metric_path, metrics)
    state_path = scope / "environment/state.json"
    state = read_json(state_path)
    state["logs"].append({"md_ft": 9999, "GR": "future-secret-sentinel", "RES": -1})
    atomic_write_json(state_path, state)
    result = compare_runs(root, parent, child)
    assert "future-secret-sentinel" not in json.dumps(result)
    assert "raw_future_payload" not in result["runs"]["left"]["estimated_snapshot"]
    assert "observation" not in result["differences"]["command_rows"][0]["left"]["response"]
