"""Explicit, immutable handoff from selected offset evidence to plans and runs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.io.project_store import atomic_write_json, read_json, well_paths
from app.model.schemas import InterpretationVersion, PrejobModel, UncertaintyModel
from app.services.baseline import estimate_offset_baseline
from app.services.project_data import load_project_and_wells


def _evidence_hashes(root: Path, active_well_id: str, offset_well_ids: list[str]) -> dict[str, str]:
    # Active-well geometry/logs/markers are not evidence for a pre-job fit.
    # Its metadata captures the declared reference; offset inputs are complete.
    paths = [well_paths(root, active_well_id)["well_json"]]
    paths.extend(path for well_id in sorted(offset_well_ids) for path in well_paths(root, well_id).values())
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


def save_prejob_model(project_root, offset_well_ids: list[str], *, active_well_id: str | None = None) -> PrejobModel:
    """Deliberately fit selected current observations and save a new version."""
    root = Path(project_root)
    project, wells = load_project_and_wells(root)
    active = active_well_id or project.active_well_id
    if not active:
        raise ValueError("Select an active well before saving a pre-job interpretation")
    offsets = list(dict.fromkeys(offset_well_ids))
    hashes = _evidence_hashes(root, active, offsets)
    top, base, uncertainty = estimate_offset_baseline(root, offsets, active_well_id=active)
    model = PrejobModel(
        interpretation=InterpretationVersion(
            step_index=0, rationale="Regional top/base fitted to explicitly selected offset marker crossings only",
            top_control_points=top, base_control_points=base,
            uncertainty=UncertaintyModel(band_tvd_ft=uncertainty),
        ),
        active_well_id=active, offset_well_ids=offsets,
        well_names={well.well_id: well.name for well in wells if well.well_id in [active, *offsets]},
        input_hashes=hashes,
    )
    # Reject an input change during the fit rather than publishing mixed evidence.
    validate_prejob_model(root, model)
    path = root / "prejob" / "models" / f"{model.interpretation.version_id}.json"
    if path.exists():
        raise ValueError("A pre-job interpretation with this identity already exists")
    atomic_write_json(path, model.model_dump(mode="json"))
    return model


def load_prejob_model(project_root, version_id: str) -> PrejobModel:
    if Path(version_id).name != version_id or not version_id:
        raise ValueError("Invalid pre-job interpretation identifier")
    return PrejobModel.model_validate(read_json(Path(project_root) / "prejob" / "models" / f"{version_id}.json"))


def list_prejob_models(project_root) -> list[PrejobModel]:
    models = [PrejobModel.model_validate(read_json(path))
              for path in (Path(project_root) / "prejob" / "models").glob("*.json")]
    return sorted(models, key=lambda model: model.interpretation.created_at, reverse=True)


def validate_prejob_model(project_root, model: PrejobModel, *, active_well_id: str | None = None,
                          offset_well_ids: list[str] | None = None) -> None:
    """Require live evidence to match before creating a new plan/run.

    Existing plans/runs keep their embedded snapshots and do not call this when
    reopening or exporting historical results.
    """
    model = PrejobModel.model_validate(model.model_dump(mode="json"))
    if active_well_id is not None and active_well_id != model.active_well_id:
        raise ValueError("Selected interpretation belongs to a different active well")
    if offset_well_ids is not None and set(offset_well_ids) != set(model.offset_well_ids):
        raise ValueError("Run offset evidence must match the selected interpretation")
    try:
        hashes = _evidence_hashes(Path(project_root), model.active_well_id, model.offset_well_ids)
    except OSError as exc:
        raise ValueError("Selected interpretation evidence is unavailable; review and save a new model in Correlation") from exc
    if hashes != model.input_hashes:
        raise ValueError("Selected interpretation evidence changed; review and save a new model in Correlation")


def model_label(model: PrejobModel) -> str:
    names = ", ".join(model.well_names.get(well_id, well_id[:8]) for well_id in model.offset_well_ids)
    return f"{model.interpretation.created_at:%Y-%m-%d %H:%M} · {names} · {model.interpretation.version_id[:8]}"
