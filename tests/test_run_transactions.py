from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.io.project_store import atomic_write_json
from app.services.decisions import load_decisions
from app.services.interpretations import load_interpretations
from app.services.project_data import load_well_frames
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.services.runs import advance_run
from app.sim.sim_store import load_simulation_state
from tests.test_run_history import prepare_run


@pytest.mark.parametrize("mode", ["replay", "causal"])
def test_failed_step_rolls_back_every_document_and_can_be_retried(tmp_path, monkeypatch, mode):
    root, config, _, _ = prepare_run(tmp_path, mode)
    scope = run_root(root)
    before = {path.relative_to(scope): path.read_bytes() for path in scope.rglob("*.json")}
    original_state = load_simulation_state(root)
    import app.services.runs as runs
    save = runs.save_simulation_state
    def fail(*args, **kwargs):
        raise OSError("simulated write interruption")
    with monkeypatch.context() as patch:
        patch.setattr(runs, "save_simulation_state", fail)
        with pytest.raises(OSError, match="interruption"):
            advance_run(root, "BUILD", "Current observation supports a bounded correction")
    assert load_simulation_state(root) == original_state
    assert len(load_decisions(root)) == 0
    assert len(load_interpretations(root)) == 1
    assert load_run_metrics(root) == []
    for relative, payload in before.items():
        assert (scope / relative).read_bytes() == payload
    assert not (scope / "pending_step.json").exists()
    assert load_well_frames(root, config.active_well_id)["trajectory"].md_ft.max() == 2000
    assert runs.save_simulation_state is save
    state = advance_run(root, "BUILD", "Retry the same supported correction")
    assert state.step_index == 1
    assert len(load_decisions(root)) == len(load_run_metrics(root)) == 1


def test_process_interruption_journal_is_recovered_before_reading_state(tmp_path: Path):
    root, _, _, _ = prepare_run(tmp_path)
    scope = run_root(root)
    path = scope / "simulations" / "simulation_state.json"
    original = path.read_bytes()
    atomic_write_json(scope / "pending_step.json", {
        "status": "pending", "files": {
            "simulations/simulation_state.json": base64.b64encode(original).decode("ascii"),
            "metrics.json": None,
        },
    })
    atomic_write_json(path, {"invalid": "partially written transaction"})
    atomic_write_json(scope / "metrics.json", [{"step_index": 99}])
    assert load_simulation_state(root).step_index == 0
    assert path.read_bytes() == original
    assert load_run_metrics(root) == []
    assert not (scope / "pending_step.json").exists()
