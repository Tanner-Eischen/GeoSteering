from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class QCWarning(BaseModel):
    code: str
    message: str


class WellQCResult(BaseModel):
    well_name: str
    md_min_ft: float
    md_max_ft: float
    survey_station_count: int
    curves_present: List[str] = Field(default_factory=list)
    sample_step_ft_est: float
    overlap_ratio: float
    valid: bool
    warnings: List[QCWarning] = Field(default_factory=list)

