from __future__ import annotations

from pathlib import Path

from app.io.project_store import atomic_write_json, read_json
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run
from app.sim.sim_models import SimulationConfig, SimulationState


def _config_path(project_root: str | Path, run_id: str | None = None) -> Path:
    return run_root(project_root, run_id) / "simulations" / "simulation_config.json"


def _state_path(project_root: str | Path, run_id: str | None = None) -> Path:
    return run_root(project_root, run_id) / "simulations" / "simulation_state.json"


def save_simulation_config(project_root: str | Path, config: SimulationConfig) -> None:
    path = _config_path(project_root)
    payload = config.model_dump(mode="json")
    if config.hidden_truth_path:
        captured = Path(config.hidden_truth_path).resolve()
        scope = path.parent.parent.resolve()
        if captured.is_relative_to(scope):
            payload["hidden_truth_path"] = captured.relative_to(scope).as_posix()
    if config.run_id and path.exists() and read_json(path) != payload:
        raise ValueError("Run configuration is immutable; initialize a new run")
    atomic_write_json(path, payload)


def load_simulation_config(project_root: str | Path, run_id: str | None = None) -> SimulationConfig:
    path = _config_path(project_root, run_id)
    payload = read_json(path)
    truth = payload.get("hidden_truth_path")
    if truth:
        scope = path.parent.parent.resolve()
        parts = truth.replace("\\", "/").split("/")
        # Existing managed absolute paths are rebound to this run even if the
        # original directory still exists. Never read another copy's truth.
        if payload.get("run_id") and parts[-4:-1] == ["runs", payload["run_id"], "environment"]:
            payload["hidden_truth_path"] = str(scope / "environment" / parts[-1])
        elif not Path(truth).is_absolute():
            captured = (scope / truth).resolve()
            if not captured.is_relative_to(scope):
                raise ValueError("Captured truth path must stay inside its run")
            payload["hidden_truth_path"] = str(captured)
    return SimulationConfig.model_validate(payload)


def save_simulation_state(project_root: str | Path, state: SimulationState) -> None:
    path = _state_path(project_root)
    if state.run_id and path.exists() and read_json(path)["step_index"] > state.step_index:
        raise ValueError("Cannot rewind a persisted run; initialize a new run")
    atomic_write_json(path, state.model_dump(mode="json"))


def load_simulation_state(project_root: str | Path, run_id: str | None = None) -> SimulationState:
    recover_run(run_root(project_root, run_id))
    return SimulationState.model_validate(read_json(_state_path(project_root, run_id)))
