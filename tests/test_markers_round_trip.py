from __future__ import annotations

from pathlib import Path

from app.io.project_store import create_project
from app.io.well_import import import_well_folder
from app.services.markers import add_marker, delete_marker, edit_marker, load_markers
from tools.generate_sample_data import generate_sample_data


def test_marker_crud_persistence(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample"
    generate_sample_data(sample_root, seed=123)

    project_root = tmp_path / "project"
    create_project(project_root, "Markers")
    result = import_well_folder(project_root, sample_root / "wells" / "offset_01", "offset_01")
    well_id = result["well_id"]

    original_count = len(load_markers(project_root, well_id))
    created = add_marker(project_root, well_id, name="TestMarker", md_ft=3333.0, notes="crud")
    loaded = load_markers(project_root, well_id)
    assert len(loaded) == original_count + 1
    assert any(m.marker_id == created.marker_id for m in loaded)

    updated = edit_marker(project_root, well_id, created.marker_id, md_ft=3344.0, name="TestMarker2")
    loaded2 = load_markers(project_root, well_id)
    assert any(m.marker_id == updated.marker_id and m.md_ft == 3344.0 for m in loaded2)

    delete_marker(project_root, well_id, created.marker_id)
    loaded3 = load_markers(project_root, well_id)
    assert len(loaded3) == original_count
    assert [m.md_ft for m in loaded3] == sorted([m.md_ft for m in loaded3])

