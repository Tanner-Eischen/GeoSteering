from __future__ import annotations

from pathlib import Path

from app.io.project_store import atomic_write_json, read_json
from app.sim.sim_models import SimulationConfig, SimulationState


def _config_path(project_root: str | Path) -> Path:
    return Path(project_root) / "simulations" / "simulation_config.json"


def _state_path(project_root: str | Path) -> Path:
    return Path(project_root) / "simulations" / "simulation_state.json"


def save_simulation_config(project_root: str | Path, config: SimulationConfig) -> None:
    atomic_write_json(_config_path(project_root), config.model_dump(mode="json"))


def load_simulation_config(project_root: str | Path) -> SimulationConfig:
    return SimulationConfig.model_validate(read_json(_config_path(project_root)))


def save_simulation_state(project_root: str | Path, state: SimulationState) -> None:
    atomic_write_json(_state_path(project_root), state.model_dump(mode="json"))


def load_simulation_state(project_root: str | Path) -> SimulationState:
    return SimulationState.model_validate(read_json(_state_path(project_root)))

