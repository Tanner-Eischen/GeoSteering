"""Guarded advance requests bind a run, acquired step and durable command payload."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.io.project_store import read_json
from app.services.decisions import load_decisions
from app.services.markers import edit_marker, load_markers
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.services.runs import advance_run, fork_run, initialize_run
from app.sim.sim_store import load_simulation_state
from tests.test_run_history import prepare_run


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*.json")}


def guards(root, *, request_id="request-1"):
    state = load_simulation_state(root)
    return {"run_id": state.run_id, "expected_step_index": state.step_index, "request_id": request_id}


@pytest.mark.parametrize("mode", ("replay", "causal"))
def test_retry_after_later_steps_returns_original_result_and_changes_nothing(tmp_path, mode):
    root, config, top, base = prepare_run(tmp_path, mode)
    request = guards(root)
    first = advance_run(root, "HOLD", "Observed landing", **request)
    advance_run(root, "BUILD", "Next acquired observation", **guards(root, request_id="request-2"))
    pick = load_markers(root, config.offset_well_ids[0])[0]
    edit_marker(root, config.offset_well_ids[0], pick.marker_id, name="Current marker edited after request")
    other = initialize_run(root, config, top, base)
    before = snapshot(root)
    assert advance_run(root, "HOLD", "Observed landing", **request) == first
    assert snapshot(root) == before
    assert load_simulation_state(root).run_id == other.run_id
    assert load_simulation_state(root, request["run_id"]).step_index == 2
    assert len(load_decisions(root, request["run_id"])) == len(load_run_metrics(root, request["run_id"])) == 2


@pytest.mark.parametrize("expected", (True, False, 0.5, 1.0, -1))
def test_invalid_step_type_is_rejected_without_any_write(tmp_path, expected):
    root, _, _, _ = prepare_run(tmp_path)
    request = {**guards(root), "expected_step_index": expected}
    before = snapshot(root)
    with pytest.raises(ValueError, match="requires"):
        advance_run(root, "HOLD", "Observed landing", **request)
    assert snapshot(root) == before


@pytest.mark.parametrize("changed", (
    {"action": "BUILD"}, {"observations": "Conflicting evidence"},
    {"target_inc_deg": 91.0}, {"rationale": "Different rationale"},
))
def test_reused_identity_rejects_conflicting_command_before_writes(tmp_path, changed):
    root, _, _, _ = prepare_run(tmp_path)
    request = guards(root)
    payload = {"action": "HOLD", "observations": "Observed landing"}
    advance_run(root, **payload, **request)
    before = snapshot(root)
    with pytest.raises(ValueError, match="different step or payload"):
        advance_run(root, **{**payload, **changed}, **request)
    assert snapshot(root) == before


def test_new_request_for_a_stale_step_and_partial_guards_do_not_write(tmp_path):
    root, _, _, _ = prepare_run(tmp_path)
    request = guards(root)
    advance_run(root, "HOLD", "Observed landing", **request)
    before = snapshot(root)
    with pytest.raises(ValueError, match="Stale"):
        advance_run(root, "HOLD", "Observed landing", **{**request, "request_id": "different-request"})
    for partial in ({"run_id": request["run_id"]}, {"request_id": "only-id"}, {"expected_step_index": 1}):
        with pytest.raises(ValueError, match="requires"):
            advance_run(root, "HOLD", "Observed landing", **partial)
    assert snapshot(root) == before


def test_explicit_run_selection_preserves_active_pointer_and_other_run(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    request = guards(root)
    other = initialize_run(root, config, top, base)
    pointer = (root / "active_run.json").read_bytes()
    other_before = snapshot(run_root(root, other.run_id))
    result = advance_run(root, "HOLD", "Selected old run's observation", **request)
    assert result.run_id == request["run_id"] and result.step_index == 1
    assert (root / "active_run.json").read_bytes() == pointer
    assert snapshot(run_root(root, other.run_id)) == other_before
    assert load_simulation_state(root).run_id == other.run_id
    assert len(load_decisions(root, request["run_id"])) == 1


def test_overlapping_same_process_retries_append_only_one_step(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    request = guards(root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(advance_run, root, "HOLD", "Observed landing", **request) for _ in range(2)]
        first, repeated = [future.result() for future in pending]
    assert first == repeated
    assert len(load_decisions(root)) == len(load_run_metrics(root)) == 1
    assert len(read_json(run_root(root) / "step_requests.json")) == 1


def test_fork_has_its_own_request_namespace_without_altering_parent(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    request = guards(root)
    advance_run(root, "HOLD", "Observed landing", **request)
    parent_before = snapshot(run_root(root))
    fork = fork_run(root)
    assert read_json(run_root(root) / "step_requests.json") == []
    result = advance_run(root, "BUILD", "Forked current observation", **guards(root))
    assert result.run_id == fork.run_id and result.step_index == 2
    assert snapshot(run_root(root, request["run_id"])) == parent_before


def test_legacy_calls_remain_unguarded_and_old_state_needs_no_migration(tmp_path):
    root, _, _, _ = prepare_run(tmp_path)
    assert not (run_root(root) / "step_requests.json").exists()
    advance_run(root, "HOLD", "Legacy caller observation")
    assert load_simulation_state(root).step_index == 1
    assert not (run_root(root) / "step_requests.json").exists()


CHILD = """
import json,os,sys
import app.services.run_transactions as transactions
from app.services.runs import advance_run
root,request,stage=sys.argv[1:]
if stage=='receipt_saved':
    original=transactions.append_only_write
    def interrupted(*args,**kwargs):
        original(*args,**kwargs)
        os._exit(73)
    transactions.append_only_write=interrupted
elif stage=='committed':
    original=transactions.atomic_write_json
    def interrupted(path,payload):
        original(path,payload)
        if payload=={'status':'committed'}:
            os._exit(73)
    transactions.atomic_write_json=interrupted
result=advance_run(root,'HOLD','Observed landing',**json.loads(request))
print(result.model_dump_json())
"""


@pytest.mark.parametrize("mode", ("replay", "causal"))
@pytest.mark.parametrize("stage", ("receipt_saved", "committed"))
def test_request_receipt_recovery_and_retry_across_process_restart(tmp_path, mode, stage):
    root, _, _, _ = prepare_run(tmp_path, mode)
    request = guards(root)
    command = [sys.executable, "-c", CHILD, str(root.resolve()), json.dumps(request)]
    crashed = subprocess.run([*command, stage], cwd=tmp_path, capture_output=True, text=True, timeout=45)
    assert crashed.returncode == 73, crashed.stdout + crashed.stderr
    assert load_simulation_state(root).step_index == (0 if stage == "receipt_saved" else 1)
    if stage == "receipt_saved":
        assert not (run_root(root) / "step_requests.json").exists()
    restarted = subprocess.run([*command, "retry"], cwd=tmp_path, capture_output=True, text=True, timeout=45)
    assert restarted.returncode == 0, restarted.stdout + restarted.stderr
    result = json.loads(restarted.stdout)
    assert result["step_index"] == 1
    before = snapshot(root)
    repeated = subprocess.run([*command, "retry"], cwd=tmp_path, capture_output=True, text=True, timeout=45)
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert json.loads(repeated.stdout) == result
    assert snapshot(root) == before
    assert len(load_decisions(root)) == len(load_run_metrics(root)) == 1
