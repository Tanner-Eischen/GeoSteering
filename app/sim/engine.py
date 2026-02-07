from __future__ import annotations

from app.sim.sim_models import SimulationConfig, SimulationState


def initial_state(config: SimulationConfig) -> SimulationState:
    return SimulationState(step_index=0, revealed_md_ft=config.start_md_ft, version_id_by_step=[], decision_id_by_step=[])


def step_forward(state: SimulationState, config: SimulationConfig) -> SimulationState:
    if state.complete:
        return state.model_copy(deep=True)

    next_step = state.step_index + 1
    next_revealed = min(config.end_md_ft, config.start_md_ft + next_step * config.step_size_ft)
    complete = next_revealed >= config.end_md_ft

    new_state = state.model_copy(deep=True)
    new_state.step_index = next_step
    new_state.revealed_md_ft = float(next_revealed)
    new_state.complete = bool(complete)
    return new_state

