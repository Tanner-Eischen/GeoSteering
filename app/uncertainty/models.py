"""Versioned, finite, JSON-safe settings and particle state."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class CalibrationSettings(EnsembleSettings):
    """Declared fixed calibration sensitivity hypotheses, never learned weights."""

    version: Literal["spatial-calibration-v2"] = "spatial-calibration-v2"
    calibration_biases_api: tuple[float, ...] = (-16.0, -8.0, 0.0, 8.0, 16.0)

    @field_validator("calibration_biases_api", mode="before")
    @classmethod
    def fixed_biases(cls, value):
        if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 9:
            raise ValueError("Declare one to nine calibration bias hypotheses")
        if any(type(item) not in {int, float} or not math.isfinite(item) for item in value):
            raise ValueError("Calibration biases must be finite numeric values")
        biases = tuple(float(item) for item in value)
        if tuple(sorted(set(biases))) != biases or 0.0 not in biases:
            raise ValueError("Calibration biases must be sorted, unique and include zero")
        if any(abs(item) > 40 for item in biases):
            raise ValueError("Calibration biases must lie within -40 to +40 API")
        return biases

    @model_validator(mode="after")
    def nominal_calibration(self):
        if self.sensor_center_api != 80.0:
            raise ValueError("Calibration v2 uses the declared nominal 80 API center")
        return self

    def conditional_settings(self, bias_api: float) -> EnsembleSettings:
        payload = self.model_dump(exclude={"calibration_biases_api"})
        payload.update(version="spatial-particle-v1", sensor_center_api=80.0 + bias_api)
        return EnsembleSettings.model_validate(payload)


class CalibrationComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    bias_api: float
    weight: float = Field(gt=0, le=1)
    ensemble: EnsembleState


class CalibrationState(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    version: Literal["spatial-calibration-state-v2"] = "spatial-calibration-state-v2"
    settings: CalibrationSettings
    seed: int = Field(ge=0, strict=True)
    x_ft: float = Field(ge=0)
    step_index: int | None = Field(default=None, ge=0, strict=True)
    last_observation_md_ft: float | None = Field(default=None, ge=0)
    update_count: int = Field(default=0, ge=0, strict=True)
    components: list[CalibrationComponent] = Field(min_length=1, max_length=9)
    ess: float = Field(gt=0)
    resampled: bool = False
    last_update: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_components(self):
        biases = self.settings.calibration_biases_api
        if tuple(component.bias_api for component in self.components) != biases:
            raise ValueError("Calibration components must match the declared ordered bias hypotheses")
        weight = 1.0 / len(biases)
        reference_prior = self.components[0].ensemble.thickness_prior_ft
        reference_thickness = self.components[0].ensemble.prior_thickness_mean_ft
        for component in self.components:
            state = component.ensemble
            if component.weight != weight:
                raise ValueError("Calibration hypothesis weights are fixed equal weights and cannot be learned")
            expected = self.settings.conditional_settings(component.bias_api)
            if state.settings != expected:
                raise ValueError("Calibration component settings differ from the declared conditional sensor model")
            if (state.seed, state.x_ft, state.step_index, state.last_observation_md_ft, state.update_count) != (
                self.seed, self.x_ft, self.step_index, self.last_observation_md_ft, self.update_count,
            ):
                raise ValueError("Calibration component seed or observation timing does not match its enclosing state")
            if state.thickness_prior_ft != reference_prior or state.prior_thickness_mean_ft != reference_thickness:
                raise ValueError("Calibration components must share the same independent thickness prior")
        expected_ess = min(component.ensemble.ess for component in self.components)
        if self.ess != expected_ess:
            raise ValueError("Calibration ESS must report the minimum conditional posterior ESS")
        if self.resampled != any(component.ensemble.resampled for component in self.components):
            raise ValueError("Calibration resampling status does not match its conditional ensembles")
        return self
