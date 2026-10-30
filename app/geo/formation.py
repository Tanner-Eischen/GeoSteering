from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Scenario(BaseModel):
    """Private synthetic field configuration, in a local positive-down frame."""

    model_config = ConfigDict(allow_inf_nan=False)

    version: str = "structural_dip_01-v1"
    seed: int = Field(default=123, ge=0)
    kickoff_md_ft: float = Field(default=500.0, ge=0)
    landing_md_ft: float = Field(default=2000.0, gt=0)
    lateral_length_ft: float = Field(default=5000.0, gt=0)
    thickness_ft: float = Field(default=24.0, gt=0)
    regional_dip: float = 0.005
    landing_x_ft: float = 3000.0 / math.pi
    landing_center_tvd_ft: float = 500.0 + 3000.0 / math.pi
    disturbance_x_ft: float = 2800.0
    disturbance_width_ft: float = Field(default=300.0, gt=0)
    disturbance_height_ft: float = 25.0
    max_dls_deg_per_100ft: float = Field(default=3.0, gt=0)
    step_ft: float = Field(default=50.0, gt=0)

    @model_validator(mode="after")
    def valid_landing_geometry(self) -> "Scenario":
        if self.landing_md_ft <= self.kickoff_md_ft:
            raise ValueError("Landing MD must follow kickoff MD.")
        radius = (self.landing_md_ft - self.kickoff_md_ft) * 2.0 / math.pi
        if not math.isclose(self.landing_x_ft, radius, abs_tol=1e-6):
            raise ValueError("Landing x must match the quarter-circle build radius.")
        if not math.isclose(self.landing_center_tvd_ft, self.kickoff_md_ft + radius, abs_tol=1e-6):
            raise ValueError("Landing center must match the build geometry.")
        return self

    @property
    def lateral_start_md_ft(self) -> float:
        return self.landing_md_ft

    @property
    def max_md_ft(self) -> float:
        return self.landing_md_ft + self.lateral_length_ft


def default_scenario(seed: int = 123) -> Scenario:
    return Scenario(seed=seed)


def formation_top_base(x_ft: np.ndarray | float, scenario: Scenario) -> tuple[np.ndarray, np.ndarray]:
    """One fixed spatial field, shared by every well and every strategy."""
    x = np.asarray(x_ft, dtype=float)
    # Compact smooth transition is exactly absent at all offset locations.
    u = np.clip((x - scenario.disturbance_x_ft) / scenario.disturbance_width_ft, 0.0, 1.0)
    disturbance = scenario.disturbance_height_ft * (3.0 * u**2 - 2.0 * u**3)
    center = (
        scenario.landing_center_tvd_ft
        + scenario.regional_dip * (x - scenario.landing_x_ft)
        + disturbance
    )
    return center - scenario.thickness_ft / 2.0, center + scenario.thickness_ft / 2.0
