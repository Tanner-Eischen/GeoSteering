from __future__ import annotations

from pydantic import BaseModel, Field


class SimulationConfig(BaseModel):
    active_well_id: str
    offset_well_ids: list[str] = Field(default_factory=list)
    curves_used: list[str] = Field(default_factory=lambda: ["GR", "RES"])
    step_size_ft: float = 100.0
    window_size_ft: float = 500.0
    start_md_ft: float = 0.0
    end_md_ft: float


class SimulationState(BaseModel):
    step_index: int = 0
    revealed_md_ft: float = 0.0
    version_id_by_step: list[str | None] = Field(default_factory=list)
    decision_id_by_step: list[str | None] = Field(default_factory=list)
    complete: bool = False

