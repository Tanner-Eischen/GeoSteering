from __future__ import annotations

from pathlib import Path

from app.io.project_store import create_project, load_project
from app.io.well_import import import_well_folder
from tools.generate_sample_data import generate_sample_data


def test_imports_all_synthetic_wells(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample_project"
    generate_sample_data(out=sample_root, seed=123)

    project_root = tmp_path / "project"
    create_project(project_root, "ImportAll")

    well_dirs = sorted((sample_root / "wells").iterdir())
    for d in well_dirs:
        import_well_folder(project_root=project_root, well_folder=d, well_name=d.name)

    project = load_project(project_root)
    assert len(project.wells) == 4

