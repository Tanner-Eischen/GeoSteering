from __future__ import annotations

import json
from pathlib import Path

import lasio
import pandas as pd
import pytest

from app.io.las_import import read_las
from app.io.project_store import create_project, load_project, read_json, well_paths
from app.io.survey_import import import_survey, read_survey_csv
from app.io.well_import import import_well_folder
from app.qc.qc_checks import run_well_qc
from tools.generate_sample_data import generate_sample_data


def test_a1_survey_import_validation_and_trajectory_rows(tmp_path: Path) -> None:
    survey_path = tmp_path / "survey.csv"
    pd.DataFrame(
        {
            "md_ft": [0.0, 100.0, 200.0],
            "inc_deg": [0.0, 10.0, 20.0],
            "azi_deg": [0.0, 20.0, 40.0],
        }
    ).to_csv(survey_path, index=False)

    project_root = tmp_path / "project"
    create_project(project_root, "A1")
    well_id = "well_a1"
    survey = read_survey_csv(survey_path)
    _, trajectory = import_survey(project_root, well_id, survey_path)

    assert len(trajectory) == len(survey)
    assert (survey["md_ft"].diff().fillna(1.0) > 0).all()


def test_a2_las_import_canonical_curves_and_depth_conversion(tmp_path: Path) -> None:
    las_path = tmp_path / "logs_m.las"
    las = lasio.LASFile()
    las.append_curve("DEPT", [0.0, 10.0, 20.0], unit="M")
    las.append_curve("GR", [80.0, 82.0, 81.0], unit="API")
    las.append_curve("RT", [10.0, 12.0, 11.0], unit="OHMM")
    las.write(str(las_path), version=2.0)

    logs, inventory = read_las(las_path)
    assert "GR" in logs.columns
    assert "RES" in logs.columns
    assert pytest.approx(logs["md_ft"].iloc[1], abs=1e-6) == 32.80839895013123
    assert set(inventory.keys()) >= {"GR", "RES"}


def test_a3_qc_overlap_failure(tmp_path: Path) -> None:
    survey = pd.DataFrame({"md_ft": [0.0, 100.0, 200.0], "inc_deg": [0.0, 1.0, 1.0], "azi_deg": [0.0, 0.0, 0.0]})
    logs = pd.DataFrame({"md_ft": [1000.0, 1100.0], "GR": [80.0, 82.0], "RES": [10.0, 11.0]})
    qc = run_well_qc("bad_overlap", survey_df=survey, logs_df=logs, overlap_threshold=0.8)
    assert not qc.valid
    assert any(w.code == "OVERLAP_TOO_LOW" for w in qc.warnings)


def test_a4_persistence_round_trip(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample_project"
    generate_sample_data(out=sample_root, seed=123)

    project_root = tmp_path / "project"
    create_project(project_root, "RoundTrip")

    result = import_well_folder(
        project_root=project_root,
        well_folder=sample_root / "wells" / "active_01",
        well_name="active_01",
    )
    assert result["well_name"] == "active_01"

    p1 = load_project(project_root)
    p2 = load_project(project_root)
    assert p1.model_dump(exclude={"created_at"}) == p2.model_dump(exclude={"created_at"})

    paths = well_paths(project_root, result["well_id"])
    well_json = read_json(paths["well_json"])
    assert "qc_summary" in well_json
    assert well_json["qc_summary"]["valid"] is True


def test_sample_generator_determinism(tmp_path: Path) -> None:
    out1 = tmp_path / "s1"
    out2 = tmp_path / "s2"
    generate_sample_data(out=out1, seed=123)
    generate_sample_data(out=out2, seed=123)

    t1 = json.loads((out1 / "truth.json").read_text(encoding="utf-8"))
    t2 = json.loads((out2 / "truth.json").read_text(encoding="utf-8"))
    assert t1 == t2

