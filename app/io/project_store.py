from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, List, Sequence, TypeVar

import pandas as pd

from app.model.schemas import Project, Well, WellRef

T = TypeVar("T")


def ensure_project_dirs(root: Path) -> None:
    (root / "wells").mkdir(parents=True, exist_ok=True)
    (root / "interpretations").mkdir(parents=True, exist_ok=True)
    (root / "plans").mkdir(parents=True, exist_ok=True)
    (root / "simulations").mkdir(parents=True, exist_ok=True)
    (root / "decisions").mkdir(parents=True, exist_ok=True)
    (root / "exports").mkdir(parents=True, exist_ok=True)
    (root / "cache").mkdir(parents=True, exist_ok=True)


def _normalize_ordered_lists(project: Project) -> Project:
    project.wells = sorted(project.wells, key=lambda w: (w.name.lower(), w.well_id))
    return project


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", suffix=".tmp", prefix=path.stem + "_", dir=path.parent, delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, sort_keys=True, indent=2, ensure_ascii=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is None:
            raise FileNotFoundError(path)
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def append_only_write(path: Path, new_items: Sequence[dict], key_fields: Sequence[str]) -> None:
    existing = read_json(path, default=[])
    old_by_key = {tuple(row[k] for k in key_fields): row for row in existing}
    new_by_key = {tuple(row[k] for k in key_fields): row for row in new_items}
    if len(old_by_key) != len(existing) or len(new_by_key) != len(new_items):
        raise ValueError(f"Duplicate append-only identifiers in {path}")
    for key, row in old_by_key.items():
        if new_by_key.get(key) != row:
            raise ValueError(f"Refusing to alter or delete immutable history {key} in {path}")
    atomic_write_json(path, list(new_items))


def create_project(root: str | Path, name: str) -> Project:
    root_path = Path(root)
    if root_path.exists() and any(root_path.iterdir()):
        raise FileExistsError(f"Project destination is not empty: {root_path}. Choose a new directory.")
    root_path.mkdir(parents=True, exist_ok=True)
    ensure_project_dirs(root_path)
    project = Project(name=name)
    save_project(project, root_path)
    return project


def save_project(project: Project, root: str | Path) -> None:
    root_path = Path(root)
    ensure_project_dirs(root_path)
    project = _normalize_ordered_lists(project)
    payload = project.model_dump(mode="json")
    atomic_write_json(root_path / "project.json", payload)


def load_project(root: str | Path) -> Project:
    root_path = Path(root)
    project_json = read_json(root_path / "project.json")
    return Project.model_validate(project_json)


def well_dir(root: str | Path, well_id: str) -> Path:
    return Path(root) / "wells" / well_id


def well_paths(root: str | Path, well_id: str) -> dict[str, Path]:
    d = well_dir(root, well_id)
    return {
        "well_json": d / "well.json",
        "survey": d / "survey.parquet",
        "trajectory": d / "trajectory.parquet",
        "logs": d / "logs.parquet",
        "markers": d / "markers.json",
    }


def save_well(root: str | Path, well: Well, survey_df: pd.DataFrame, trajectory_df: pd.DataFrame, logs_df: pd.DataFrame) -> None:
    paths = well_paths(root, well.well_id)
    paths["well_json"].parent.mkdir(parents=True, exist_ok=True)
    survey_df.sort_values("md_ft").to_parquet(paths["survey"], index=False)
    trajectory_df.sort_values("md_ft").to_parquet(paths["trajectory"], index=False)
    logs_df.sort_values("md_ft").to_parquet(paths["logs"], index=False)
    atomic_write_json(paths["well_json"], well.model_dump(mode="json"))
    if well.markers_path and not paths["markers"].exists():
        atomic_write_json(paths["markers"], [])


def load_well(root: str | Path, well_id: str) -> tuple[Well, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = well_paths(root, well_id)
    well = Well.model_validate(read_json(paths["well_json"]))
    survey = pd.read_parquet(paths["survey"])
    trajectory = pd.read_parquet(paths["trajectory"])
    logs = pd.read_parquet(paths["logs"])
    return well, survey, trajectory, logs


def upsert_well_ref(project: Project, well_id: str, well_name: str) -> None:
    refs: List[WellRef] = [w for w in project.wells if w.well_id != well_id]
    refs.append(WellRef(well_id=well_id, name=well_name))
    project.wells = sorted(refs, key=lambda w: (w.name.lower(), w.well_id))

