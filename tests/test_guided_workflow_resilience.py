"""Abrupt process-exit checks at real persisted workflow boundaries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.services.decisions import load_decisions
from app.services.interpretations import load_interpretations
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.sim.sim_store import load_simulation_state
from tests.test_run_history import prepare_run

STAGES = [
    (mode, stage)
    for mode in ("replay", "causal")
    for stage in (
        "create_interpretation_version", "create_decision", "save_metric_snapshot",
        "commit_environment_step", "save_simulation_state",
    )
    if mode == "causal" or stage != "commit_environment_step"
]

CHILD = """
import os, sys
import app.services.runs as runs
import app.services.run_transactions as transactions
import app.sim.environment as environment
root, stage = sys.argv[1:]
if stage == 'committed_marker':
    original = transactions.atomic_write_json
    def interrupted(path, payload):
        result = original(path, payload)
        if payload == {'status': 'committed'}:
            os._exit(73)
        return result
    transactions.atomic_write_json = interrupted
else:
    module = environment if stage == 'commit_environment_step' else runs
    original = getattr(module, stage)
    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        os._exit(73)
        return result
    setattr(module, stage, interrupted)
runs.advance_run(root, 'BUILD', 'Current acquired observation supports bounded correction')
raise AssertionError('Persistence fault was not reached')
"""


def abruptly_advance(root: Path, stage: str) -> None:
    # Running outside the repository loads the actual installed app package.
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(root.resolve()), stage],
        cwd=root.parent, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 73, result.stdout + result.stderr


@pytest.mark.parametrize(("mode", "stage"), STAGES)
def test_uncommitted_process_exit_restores_every_saved_document(tmp_path, mode, stage):
    root, _, _, _ = prepare_run(tmp_path, mode)
    scope = run_root(root)
    before = {p.relative_to(scope): p.read_bytes() for p in scope.rglob("*.json")}
    original_state = load_simulation_state(root)
    abruptly_advance(root, stage)
    assert (scope / "pending_step.json").is_file()
    assert load_simulation_state(root) == original_state
    assert load_decisions(root) == []
    assert load_run_metrics(root) == []
    assert len(load_interpretations(root)) == 1
    assert not (scope / "pending_step.json").exists()
    assert {p.relative_to(scope): p.read_bytes() for p in scope.rglob("*.json")} == before


@pytest.mark.parametrize("mode", ("replay", "causal"))
def test_process_exit_after_commit_marker_preserves_one_step(tmp_path, mode):
    root, _, _, _ = prepare_run(tmp_path, mode)
    scope = run_root(root)
    abruptly_advance(root, "committed_marker")
    assert (scope / "pending_step.json").is_file()
    assert load_simulation_state(root).step_index == 1
    assert len(load_decisions(root)) == len(load_run_metrics(root)) == 1
    assert len(load_interpretations(root)) == 2
    assert not (scope / "pending_step.json").exists()
    # A second reopen must not roll the committed action back or duplicate it.
    assert load_simulation_state(root).step_index == 1
    assert len(load_decisions(root)) == len(load_run_metrics(root)) == 1
