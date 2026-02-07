from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectSettings(BaseModel):
    depth_basis: Literal["MD_FT"] = "MD_FT"
    vertical_reference: Literal["TVD_FT"] = "TVD_FT"
    required_curves: List[str] = Field(default_factory=lambda: ["GR", "RES"])


class WellRef(BaseModel):
    well_id: str
    name: str


class CurveMeta(BaseModel):
    canonical_name: str
    original_mnemonics: List[str] = Field(default_factory=list)
    unit: str
    sample_step_ft_est: float
    depth_min_ft: float
    depth_max_ft: float


class Well(BaseModel):
    well_id: str
    name: str
    metadata: Dict[str, Optional[str]] = Field(default_factory=dict)
    survey_path: str
    trajectory_path: str
    logs_path: str
    markers_path: Optional[str] = None
    curve_inventory: Dict[str, CurveMeta] = Field(default_factory=dict)
    qc_summary: Dict[str, object] = Field(default_factory=dict)


class Project(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    project_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    wells: List[WellRef] = Field(default_factory=list)
    active_well_id: Optional[str] = None
    created_by: Optional[str] = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Project name must be non-empty.")
        return value.strip()


class Marker(BaseModel):
    marker_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    md_ft: float
    notes: Optional[str] = None
    color: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("name")
    @classmethod
    def marker_name_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Marker name must be non-empty.")
        return value.strip()


class ControlPoint(BaseModel):
    md_ft: float
    tvd_ft: float


class UncertaintyBand(BaseModel):
    md_from_ft: float
    md_to_ft: float
    band_tvd_ft: float


class UncertaintyModel(BaseModel):
    band_tvd_ft: Optional[float] = None
    bands: List[UncertaintyBand] = Field(default_factory=list)

    @model_validator(mode="after")
    def band_or_bands(self) -> "UncertaintyModel":
        if self.band_tvd_ft is None and not self.bands:
            raise ValueError("Either band_tvd_ft or bands must be provided.")
        return self


class InterpretationVersion(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid4()))
    derived_from_version_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    step_index: Optional[int] = None
    rationale: str
    top_control_points: List[ControlPoint] = Field(default_factory=list)
    base_control_points: List[ControlPoint] = Field(default_factory=list)
    uncertainty: UncertaintyModel

    @field_validator("rationale")
    @classmethod
    def rationale_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Interpretation rationale must be non-empty.")
        return value.strip()

    @field_validator("top_control_points", "base_control_points")
    @classmethod
    def sorted_control_points(cls, points: List[ControlPoint]) -> List[ControlPoint]:
        return sorted(points, key=lambda p: p.md_ft)


class Recommendation(BaseModel):
    action: Literal["HOLD", "BUILD", "DROP"]
    target_inc_deg: Optional[float] = None
    target_azi_deg: Optional[float] = None
    notes: Optional[str] = None


class DecisionEntry(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    step_index: int
    md_from_ft: float
    md_to_ft: float
    interpretation_version_id: str
    observations: str
    recommendation: Recommendation
    risk_note: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("observations")
    @classmethod
    def observations_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Decision observations must be non-empty.")
        return value.strip()


class PlanParameters(BaseModel):
    kickoff_md_ft: float
    landing_md_ft: float
    lateral_length_ft: float
    planned_azi_deg: float
    build_rate_hint_deg_per_100ft: Optional[float] = None
    step_ft: float = 100.0


class DLSExceedance(BaseModel):
    md_from_ft: float
    md_to_ft: float
    dls_deg_per_100ft: float


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    parameters: PlanParameters
    stations_path: str
    dls_max_deg_per_100ft: float
    dls_exceedances: List[DLSExceedance] = Field(default_factory=list)

