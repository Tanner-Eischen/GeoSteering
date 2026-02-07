from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.io.project_store import create_project, load_project
from app.io.well_import import import_well_folder
from app.plot.correlation_panel import build_correlation_figure
from app.services.markers import load_markers
from app.services.project_data import load_well_frames
from tools.generate_sample_data import generate_sample_data


def test_multiwell_display_minimum_three(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample"
    generate_sample_data(sample_root, seed=123)
    project_root = tmp_path / "project"
    create_project(project_root, "Corr")

    for name in ["offset_01", "offset_02", "offset_03"]:
        import_well_folder(project_root, sample_root / "wells" / name, name)

    project = load_project(project_root)
    refs = {w.name: w.well_id for w in project.wells}
    logs_by_well = {}
    markers_by_well = {}
    for name in ["offset_01", "offset_02", "offset_03"]:
        frames = load_well_frames(project_root, refs[name])
        logs_by_well[name] = frames["logs"]
        markers_by_well[name] = [m.model_dump(mode="json") for m in load_markers(project_root, refs[name])]

    markers_before = deepcopy(markers_by_well)
    fig = build_correlation_figure(
        logs_by_well=logs_by_well,
        markers_by_well=markers_by_well,
        curves=["GR"],
        display_shifts_ft={"offset_01": 15.0},
    )

    assert fig is not None
    # At least one trace per well when GR exists.
    assert len(fig.data) >= 3
    # Display shift must not mutate source marker MD values.
    assert markers_by_well == markers_before

