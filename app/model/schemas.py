from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScientificModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class WellReference(ScientificModel):
    coordinate_system: Literal["LOCAL_EAST_NORTH_FT"] = "LOCAL_EAST_NORTH_FT"
    vertical_datum: str = "LOCAL_TVD"
    origin_east_ft: float = 0.0
    origin_north_ft: float = 0.0
    initial_tvd_ft: float | None = None


class ProjectSettings(ScientificModel):
    depth_basis: Literal["MD_FT"] = "MD_FT"
    vertical_reference: Literal["TVD_FT"] = "TVD_FT"
    required_curves: List[str] = Field(default_factory=lambda: ["GR", "RES"])


class WellRef(ScientificModel):
    well_id: str
    name: str


class CurveMeta(ScientificModel):
    canonical_name: str
    original_mnemonics: List[str] = Field(default_factory=list)
    unit: str
    sample_step_ft_est: float
    depth_min_ft: float
    depth_max_ft: float


class Well(ScientificModel):
    well_id: str
    name: str
    metadata: Dict[str, Optional[str]] = Field(default_factory=dict)
    reference: WellReference | None = None
    survey_path: str
    trajectory_path: str
    logs_path: str
    markers_path: Optional[str] = None
    curve_inventory: Dict[str, CurveMeta] = Field(default_factory=dict)
    qc_summary: Dict[str, object] = Field(default_factory=dict)


class Project(ScientificModel):
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


class Marker(ScientificModel):
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


class ControlPoint(ScientificModel):
    md_ft: float
    tvd_ft: float
    x_ft: float | None = None


class UncertaintyBand(ScientificModel):
    md_from_ft: float
    md_to_ft: float
    band_tvd_ft: float = Field(ge=0)


class UncertaintyModel(ScientificModel):
    band_tvd_ft: Optional[float] = Field(default=None, ge=0)
    bands: List[UncertaintyBand] = Field(default_factory=list)

    @model_validator(mode="after")
    def band_or_bands(self) -> "UncertaintyModel":
        if self.band_tvd_ft is None and not self.bands:
            raise ValueError("Either band_tvd_ft or bands must be provided.")
        return self


class InterpretationVersion(ScientificModel):
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
        spatial = [p.x_ft is not None for p in points]
        if any(spatial) and not all(spatial):
            raise ValueError("Cannot mix MD and spatial horizon control points.")
        coordinates = [p.x_ft if all(spatial) else p.md_ft for p in points]
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("Horizon control coordinates must be unique.")
        return sorted(points, key=lambda p: p.x_ft if all(spatial) else p.md_ft)


class Recommendation(ScientificModel):
    action: Literal["HOLD", "BUILD", "DROP"]
    target_inc_deg: Optional[float] = Field(default=None, ge=0, le=180)
    target_azi_deg: Optional[float] = Field(default=None, ge=0, lt=360)
    notes: Optional[str] = None


class DecisionEntry(ScientificModel):
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


class PlanParameters(ScientificModel):
    kickoff_md_ft: float = Field(ge=0)
    landing_md_ft: float = Field(gt=0)
    lateral_length_ft: float = Field(gt=0)
    planned_azi_deg: float = Field(ge=0, lt=360)
    build_rate_hint_deg_per_100ft: Optional[float] = Field(default=None, gt=0)
    step_ft: float = Field(default=100.0, gt=0)


class DLSExceedance(ScientificModel):
    md_from_ft: float
    md_to_ft: float
    dls_deg_per_100ft: float


class Plan(ScientificModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    parameters: PlanParameters
    stations_path: str
    dls_max_deg_per_100ft: float
    dls_exceedances: List[DLSExceedance] = Field(default_factory=list)

