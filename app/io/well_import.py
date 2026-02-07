from __future__ import annotations

from pathlib import Path
from typing import List
from uuid import uuid4

import pandas as pd

from app.io.las_import import import_las
from app.io.project_store import (
    atomic_write_json,
    load_project,
    save_project,
    upsert_well_ref,
    well_paths,
)
from app.io.survey_import import import_survey
from app.model.schemas import Marker, Well
from app.qc.qc_checks import run_well_qc


def read_markers_csv(path: str | Path) -> List[Marker]:
    marker_path = Path(path)
    df = pd.read_csv(marker_path)
    required = {"marker_name", "md_ft"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Markers CSV {marker_path} missing columns: {sorted(missing)}")

    markers: List[Marker] = []
    for _, row in df.iterrows():
        markers.append(
            Marker(
                name=str(row["marker_name"]),
                md_ft=float(row["md_ft"]),
                color=str(row["color"]) if "color" in df.columns and pd.notna(row.get("color")) else None,
                notes=str(row["notes"]) if "notes" in df.columns and pd.notna(row.get("notes")) else None,
            )
        )
    return sorted(markers, key=lambda m: m.md_ft)


def import_well_folder(project_root: str | Path, well_folder: str | Path, well_name: str) -> dict:
    project_root = Path(project_root)
    well_folder = Path(well_folder)
    survey_path = well_folder / "survey.csv"
    logs_path = well_folder / "logs.las"
    markers_path = well_folder / "markers.csv"

    if not survey_path.exists():
        raise FileNotFoundError(f"Missing survey CSV: {survey_path}")
    if not logs_path.exists():
        raise FileNotFoundError(f"Missing logs LAS: {logs_path}")

    project = load_project(project_root)
    well_id = str(uuid4())

    survey_df, trajectory_df = import_survey(project_root, well_id, survey_path)
    logs_df, curve_inventory = import_las(project_root, well_id, logs_path)
    qc_result = run_well_qc(well_name=well_name, survey_df=survey_df, logs_df=logs_df, required_curves=["GR", "RES"])
    if not qc_result.valid:
        warnings = "; ".join(w.message for w in qc_result.warnings)
        raise ValueError(f"Well '{well_name}' failed QC: {warnings}")

    paths = well_paths(project_root, well_id)
    marker_models: List[Marker] = []
    marker_rel = None
    if markers_path.exists():
        marker_models = read_markers_csv(markers_path)
        atomic_write_json(paths["markers"], [m.model_dump(mode="json") for m in marker_models])
        marker_rel = str(paths["markers"].relative_to(project_root).as_posix())

    well = Well(
        well_id=well_id,
        name=well_name,
        survey_path=str(paths["survey"].relative_to(project_root).as_posix()),
        trajectory_path=str(paths["trajectory"].relative_to(project_root).as_posix()),
        logs_path=str(paths["logs"].relative_to(project_root).as_posix()),
        markers_path=marker_rel,
        curve_inventory=curve_inventory,
        qc_summary=qc_result.model_dump(mode="json"),
    )

    atomic_write_json(paths["well_json"], well.model_dump(mode="json"))
    upsert_well_ref(project, well_id=well_id, well_name=well_name)
    if project.active_well_id is None:
        project.active_well_id = well_id
    save_project(project, project_root)

    return {
        "well_id": well_id,
        "well_name": well_name,
        "survey_rows": len(survey_df),
        "log_rows": len(logs_df),
        "markers_loaded": len(marker_models),
    }

