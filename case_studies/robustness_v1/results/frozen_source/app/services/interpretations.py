from __future__ import annotations

from pathlib import Path
from typing import Sequence

from app.io.project_store import append_only_write, read_json
from app.model.schemas import ControlPoint, InterpretationVersion, UncertaintyModel
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run


def _path(project_root: str | Path, run_id: str | None = None) -> Path:
    return run_root(project_root, run_id) / "interpretations" / "interpretations.json"


def load_interpretations(project_root: str | Path, run_id: str | None = None) -> list[InterpretationVersion]:
    recover_run(run_root(project_root, run_id))
    rows = read_json(_path(project_root, run_id), default=[])
    return [InterpretationVersion.model_validate(r) for r in rows]


def _save_interpretations(project_root: str | Path, versions: list[InterpretationVersion]) -> None:
    ordered = sorted(versions, key=lambda v: v.created_at)
    append_only_write(
        _path(project_root),
        [v.model_dump(mode="json") for v in ordered],
        key_fields=["version_id"],
    )


def create_baseline_interpretation(
    project_root: str | Path,
    top_control_points: Sequence[ControlPoint],
    base_control_points: Sequence[ControlPoint],
    rationale: str = "Baseline interpretation",
    uncertainty_band_tvd_ft: float = 5.0,
) -> InterpretationVersion:
    versions = load_interpretations(project_root)
    if versions:
        return versions[0]
    baseline = InterpretationVersion(
        derived_from_version_id=None,
        step_index=0,
        rationale=rationale,
        top_control_points=list(top_control_points),
        base_control_points=list(base_control_points),
        uncertainty=UncertaintyModel(band_tvd_ft=uncertainty_band_tvd_ft),
    )
    versions.append(baseline)
    _save_interpretations(project_root, versions)
    return baseline


def get_latest_interpretation(project_root: str | Path, run_id: str | None = None) -> InterpretationVersion | None:
    versions = load_interpretations(project_root, run_id)
    if not versions:
        return None
    return max(versions, key=lambda v: v.created_at)


def get_interpretation_by_id(project_root: str | Path, version_id: str) -> InterpretationVersion:
    for version in load_interpretations(project_root):
        if version.version_id == version_id:
            return version
    raise ValueError(f"Interpretation version not found: {version_id}")


def create_interpretation_version(
    project_root: str | Path,
    step_index: int,
    rationale: str,
    top_control_points: Sequence[ControlPoint],
    base_control_points: Sequence[ControlPoint],
    uncertainty_band_tvd_ft: float = 5.0,
) -> InterpretationVersion:
    latest = get_latest_interpretation(project_root)
    derived_from = latest.version_id if latest else None
    version = InterpretationVersion(
        derived_from_version_id=derived_from,
        step_index=step_index,
        rationale=rationale,
        top_control_points=list(top_control_points),
        base_control_points=list(base_control_points),
        uncertainty=UncertaintyModel(band_tvd_ft=uncertainty_band_tvd_ft),
    )
    versions = load_interpretations(project_root)
    versions.append(version)
    _save_interpretations(project_root, versions)
    return version

