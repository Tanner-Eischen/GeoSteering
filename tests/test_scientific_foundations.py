from __future__ import annotations

from pathlib import Path

import lasio
import numpy as np
import pandas as pd
import pytest

from app.alg.kpi import compute_kpis
from app.alg.trajectory_min_curve import compute_trajectory
from app.io.las_import import read_las
from app.io.project_store import append_only_write, create_project, read_json
from app.io.survey_import import read_survey_csv
from app.model.schemas import ControlPoint
from app.plan.plan_generator import plan_to_target
from app.qc.qc_checks import run_well_qc


def test_midpoint_crossing_uses_length_not_sample_count() -> None:
    trajectory = pd.DataFrame({"md_ft": [0., 1.], "tvd_ft": [0., 1.]})
    top = [ControlPoint(md_ft=0, tvd_ft=.5), ControlPoint(md_ft=1, tvd_ft=.5)]
    base = [ControlPoint(md_ft=0, tvd_ft=2), ControlPoint(md_ft=1, tvd_ft=2)]
    for step in (1., .5, .3, .01):
        score = compute_kpis(trajectory, top, base, 0, 1, step)
        assert score.percent_in_zone == pytest.approx(50)
        assert score.in_zone_length_ft == pytest.approx(.5)
        assert score.evaluated_length_ft == 1


def test_partial_interval_center_distance_and_returning_x() -> None:
    trajectory = pd.DataFrame({"md_ft": [0., 1., 2.], "tvd_ft": [0., 2., 0.], "x_ft": [0., 1., 0.]})
    top = [ControlPoint(md_ft=x, x_ft=x, tvd_ft=.5) for x in (0, .5, 1)]
    base = [ControlPoint(md_ft=x, x_ft=x, tvd_ft=1.5) for x in (0, .5, 1)]
    score = compute_kpis(trajectory, top, base, .1, 1.9, .7)
    assert score.in_zone_length_ft == pytest.approx(1.)
    assert score.avg_center_distance == pytest.approx(.82 / 1.8)
    with pytest.raises(ValueError, match="outside"):
        compute_kpis(trajectory, top, base, 0, 3)


def test_nonzero_survey_start_requires_explicit_tie_in() -> None:
    survey = pd.DataFrame({"md_ft": [1000., 1100.], "inc_deg": [0., 0.], "azi_deg": [0., 0.]})
    with pytest.raises(ValueError, match="tie-in"):
        compute_trajectory(survey)
    result = compute_trajectory(survey, initial_tvd_ft=950, initial_east_ft=500, initial_north_ft=100)
    np.testing.assert_allclose(result.tvd_ft, [950, 1050])
    np.testing.assert_allclose(result.x_ft, 500)
    np.testing.assert_allclose(result.north_ft, 100)


@pytest.mark.parametrize("depth", [[0., np.inf], [0., 0.], [100., 0.]])
def test_reject_invalid_survey_order_or_values(tmp_path: Path, depth) -> None:
    path = tmp_path / "survey.csv"
    pd.DataFrame({"md_ft": depth, "inc_deg": [0., 0.], "azi_deg": [0., 0.]}).to_csv(path, index=False)
    with pytest.raises(ValueError):
        read_survey_csv(path)


def test_unknown_las_units_rejected(tmp_path: Path) -> None:
    path = tmp_path / "logs.las"
    las = lasio.LASFile()
    las.append_curve("DEPT", [0, 1], unit="FATHOMS")
    las.append_curve("GR", [80, 81], unit="API")
    las.append_curve("RT", [10, 11], unit="OHMM")
    las.write(str(path), version=2)
    with pytest.raises(ValueError, match="depth unit"):
        read_las(path)


def test_qc_rejects_empty_curves_and_duplicate_depth() -> None:
    survey = pd.DataFrame({"md_ft": [0., 1., 2.], "inc_deg": [0.] * 3, "azi_deg": [0.] * 3})
    for depths, curve in (([0., 1., 2.], [np.nan] * 3), ([0., 0., 2.], [80.] * 3)):
        logs = pd.DataFrame({"md_ft": depths, "GR": curve, "RES": curve})
        qc = run_well_qc("invalid", survey, logs)
        assert not qc.valid
        assert any(item.severity == "error" for item in qc.warnings)


def test_history_immutable_and_project_recreation_refused(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    append_only_write(path, [{"id": "one", "value": "original"}], ["id"])
    with pytest.raises(ValueError, match="immutable"):
        append_only_write(path, [{"id": "one", "value": "rewritten"}], ["id"])
    assert read_json(path)[0]["value"] == "original"
    root = tmp_path / "project"
    original = create_project(root, "original")
    with pytest.raises(FileExistsError):
        create_project(root, "replacement")
    assert read_json(root / "project.json")["project_id"] == original.project_id


def test_target_landing_reaches_offset_model_and_rejects_infeasible_dls() -> None:
    import math
    center_intercept = 500 + 3000 / math.pi * .995
    top = [ControlPoint(md_ft=x, x_ft=x, tvd_ft=center_intercept + .005 * x - 12) for x in (0, 10000)]
    base = [ControlPoint(md_ft=x, x_ft=x, tvd_ft=center_intercept + .005 * x + 12) for x in (0, 10000)]
    parameters, result = plan_to_target(top, base, dls_max_deg_per_100ft=6)
    landing = result.stations.loc[np.isclose(result.stations.md_ft, parameters.landing_md_ft)].iloc[0]
    assert landing.tvd_ft == pytest.approx(center_intercept + .005 * landing.east_ft, abs=.01)
    assert not result.exceedances
    with pytest.raises(ValueError, match="feasible"):
        plan_to_target(top, base, dls_max_deg_per_100ft=3)
    with pytest.raises(ValueError, match="thickness"):
        plan_to_target(base, top)


def test_reference_without_tvd_cannot_invent_nonzero_survey_tie_in(tmp_path: Path) -> None:
    from app.io.project_store import atomic_write_json
    from app.io.well_import import import_well_folder
    root, source = tmp_path / "project", tmp_path / "source"
    create_project(root, "tie-in")
    source.mkdir()
    pd.DataFrame({"md_ft": [1000., 1100.], "inc_deg": [0., 0.], "azi_deg": [0., 0.]}).to_csv(source / "survey.csv", index=False)
    (source / "logs.las").write_text("not reached", encoding="utf-8")
    atomic_write_json(source / "reference.json", {"origin_east_ft": 500, "vertical_datum": "LOCAL_TVD"})
    with pytest.raises(ValueError, match="tie-in"):
        import_well_folder(root, source, "missing tie-in")


def test_spatial_baseline_rejects_unreferenced_active(tmp_path: Path) -> None:
    from app.io.project_store import atomic_write_json, load_project, well_paths
    from app.io.well_import import import_well_folder
    from app.services.baseline import estimate_offset_baseline
    from tools.generate_sample_data import generate_sample_data
    sample, root = tmp_path / "sample", tmp_path / "project"
    generate_sample_data(sample)
    create_project(root, "baseline")
    for name in ("active_01", "offset_01", "offset_02", "offset_03"):
        import_well_folder(root, sample / "wells" / name, name)
    project = load_project(root)
    path = well_paths(root, project.active_well_id)["well_json"]
    payload = read_json(path)
    offsets = [ref.well_id for ref in project.wells if ref.well_id != project.active_well_id]
    from app.services.markers import add_marker
    before = estimate_offset_baseline(root, offsets)
    for well_id in offsets:
        add_marker(root, well_id, "Top_B", 1638.)
        add_marker(root, well_id, "Base_B", 1662.)
    after = estimate_offset_baseline(root, offsets)
    assert after == before
    payload["reference"] = None
    atomic_write_json(path, payload)
    with pytest.raises(ValueError, match="active well"):
        estimate_offset_baseline(root, offsets)
