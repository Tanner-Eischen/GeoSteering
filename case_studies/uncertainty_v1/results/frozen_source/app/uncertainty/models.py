"""Versioned, finite, JSON-safe settings and particle state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EnsembleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    version: Literal["spatial-particle-v1"] = "spatial-particle-v1"
    member_count: int = Field(default=256, ge=32, le=1024, strict=True)
    prior_center_std_ft: float = Field(default=10.0, gt=0)
    prior_dip_std: float = Field(default=0.006, gt=0)
    prior_thickness_relative_std: float = Field(default=0.10, gt=0, le=0.5)
    center_process_std_ft: float = Field(default=2.0, ge=0)
    dip_process_std: float = Field(default=0.002, ge=0)
    process_reference_step_ft: float = Field(default=50.0, gt=0)
    dip_bound: float = Field(default=0.15, gt=0, le=1)
    sensor_center_api: float = 80.0
    sensor_gradient_api_per_ft: float = Field(default=2.0, gt=0)
    sensor_clip_min_api: float = 20.0
    sensor_clip_max_api: float = 160.0
    sensor_noise_std_api: float = Field(default=0.6, gt=0)
    model_discrepancy_std_api: float = Field(default=4.0, ge=0)
    resample_ess_fraction: float = Field(default=0.5, gt=0, le=1)
    forecast_grid_step_ft: float = Field(default=50.0, gt=0, le=500)

    @model_validator(mode="after")
    def ordered_sensor_limits(self):
        if self.sensor_clip_max_api <= self.sensor_clip_min_api:
            raise ValueError("Sensor clipping maximum must exceed minimum")
        return self


class EnsembleMember(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    center_tvd_ft: float
    dip: float
    thickness_ft: float = Field(gt=0)


class EnsembleState(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    version: Literal["spatial-particle-state-v1"] = "spatial-particle-state-v1"
    settings: EnsembleSettings
    seed: int = Field(ge=0, strict=True)
    x_ft: float = Field(ge=0)
    members: list[EnsembleMember]
    weights: list[float] = Field(min_length=32)
    thickness_prior_ft: list[float] = Field(min_length=64, max_length=64)
    prior_thickness_mean_ft: float = Field(gt=0)
    last_observation_md_ft: float | None = None
    step_index: int | None = None
    update_count: int = Field(default=0, ge=0, strict=True)
    ess: float = Field(gt=0)
    resampled: bool = False
    last_update: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_members(self):
        count = self.settings.member_count
        if any(len(values) != count for values in (self.members, self.weights)):
            raise ValueError("Ensemble member and weight counts must match settings")
        if any(weight < 0 for weight in self.weights) or abs(sum(self.weights) - 1.0) > 1e-8:
            raise ValueError("Ensemble weights must be nonnegative and normalized")
        if any(not 0 < value < float("inf") for value in self.thickness_prior_ft):
            raise ValueError("Independent thickness prior must be positive and finite")
        if any(abs(member.dip) > self.settings.dip_bound + 1e-12 for member in self.members):
            raise ValueError("Ensemble dip exceeds the declared bound")
        actual_ess = 1.0 / sum(weight * weight for weight in self.weights)
        if abs(actual_ess - self.ess) > 1e-7 * count:
            raise ValueError("Recorded ESS does not match the posterior weights")
        if self.step_index is not None and (type(self.step_index) is not int or self.step_index < 0):
            raise ValueError("Ensemble step index must be nonnegative")
        return self
