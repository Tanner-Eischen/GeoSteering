from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationConfig(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    run_id: str | None = None
    mode: Literal["replay", "causal"] = "replay"
    active_well_id: str
    offset_well_ids: list[str] = Field(default_factory=list)
    curves_used: list[str] = Field(default_factory=lambda: ["GR", "RES"])
    step_size_ft: float = Field(default=100.0, gt=0)
    window_size_ft: float = Field(default=500.0, gt=0)
    start_md_ft: float = Field(default=0.0, ge=0)
    end_md_ft: float
    lateral_start_md_ft: float = Field(default=0.0, ge=0)
    scenario_version: str = "unspecified"
    seed: int = 123
    plan_id: str | None = None
    guided: bool = True
    max_dls_deg_per_100ft: float = Field(default=3.0, gt=0)
    hidden_truth_path: str | None = None
    use_default_synthetic_scenario: bool = False

    @model_validator(mode="after")
    def validate_interval(self) -> SimulationConfig:
        if self.end_md_ft <= self.start_md_ft:
            raise ValueError("end_md_ft must be greater than start_md_ft")
        if self.active_well_id in self.offset_well_ids:
            raise ValueError("Active well cannot also be an offset")
        return self


class SimulationState(BaseModel):
    run_id: str | None = None
    step_index: int = 0
    revealed_md_ft: float = 0.0
    version_id_by_step: list[str | None] = Field(default_factory=list)
    decision_id_by_step: list[str | None] = Field(default_factory=list)
    complete: bool = False

