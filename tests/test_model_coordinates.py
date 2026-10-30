from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app.alg.trajectory_min_curve import compute_trajectory
from app.geo.evaluation import evaluate_trajectory
from app.geo.formation import default_scenario, formation_top_base
from app.sim.causal import landing_trajectory, run_strategy
from tools.generate_sample_data import generate_sample_data


def test_landing_matches_analytic_quarter_circle_and_zone() -> None:
    scenario = default_scenario()
    landing = landing_trajectory(scenario).iloc[-1]
    radius = 1500.0 * 2.0 / np.pi
    assert landing.east_ft == pytest.approx(radius, abs=1e-8)
    assert landing.tvd_ft == pytest.approx(500.0 + radius, abs=1e-8)
    top, base = formation_top_base(landing.east_ft, scenario)
    assert float(top) < landing.tvd_ft < float(base)


def test_offset_markers_cross_the_same_spatial_field(tmp_path) -> None:
    generate_sample_data(tmp_path)
    scenario = default_scenario()
    positions = []
    for name in ["offset_01", "offset_02", "offset_03"]:
        root = tmp_path / "wells" / name
        reference = json.loads((root / "reference.json").read_text())
        traj = compute_trajectory(pd.read_csv(root / "survey.csv"), initial_tvd_ft=reference["initial_tvd_ft"],
                                  initial_east_ft=reference["origin_east_ft"])
        markers = pd.read_csv(root / "markers.csv").set_index("marker_name")
        top, base = formation_top_base(traj.east_ft.iloc[0], scenario)
        assert np.interp(markers.loc["Top_A", "md_ft"], traj.md_ft, traj.tvd_ft) == pytest.approx(float(top))
        assert np.interp(markers.loc["Base_A", "md_ft"], traj.md_ft, traj.tvd_ft) == pytest.approx(float(base))
        positions.append(traj.east_ft.iloc[0])
    assert positions == [0.0, 500.0, 900.0]


def test_independent_evaluator_integrates_half_interval() -> None:
    scenario = default_scenario().model_copy(update={"lateral_length_ft": 1.0, "regional_dip": 0.0,
                                                    "disturbance_height_ft": 0.0})
    center = scenario.landing_center_tvd_ft
    # Entire first half is inside; second half is below the base.
    trajectory = pd.DataFrame({"md_ft": [2000.0, 2001.0], "x_ft": [1000.0, 1001.0],
                               "tvd_ft": [center + 11.5, center + 12.5],
                               "dls_deg_per_100ft": [0.0, 0.0]})
    result = evaluate_trajectory(trajectory, scenario)
    assert result["percent_in_zone"] == pytest.approx(50.0)
    assert result["in_zone_length_ft"] == pytest.approx(0.5)
    assert result["evaluated_length_ft"] == 1.0


def test_nonzero_md_requires_tie_in_and_preserves_it() -> None:
    survey = pd.DataFrame({"md_ft": [1000.0, 1100.0], "inc_deg": [0.0, 0.0], "azi_deg": [0.0, 0.0]})
    with pytest.raises(ValueError, match="tie-in"):
        compute_trajectory(survey)
    result = compute_trajectory(survey, initial_tvd_ft=900.0, initial_east_ft=500.0)
    np.testing.assert_allclose(result.tvd_ft, [900.0, 1000.0])
    np.testing.assert_allclose(result.east_ft, [500.0, 500.0])


def test_truth_evaluation_requires_completion_and_converges() -> None:
    scenario = default_scenario()
    result = run_strategy("guided")
    trajectory = pd.DataFrame(result["trajectory"])
    coarse = evaluate_trajectory(trajectory, scenario, integration_step_ft=1.0)
    refined = evaluate_trajectory(trajectory, scenario, integration_step_ft=0.1)
    assert abs(coarse["percent_in_zone"] - refined["percent_in_zone"]) < 0.001
    assert abs(coarse["avg_center_distance_ft"] - refined["avg_center_distance_ft"]) < 0.001
    with pytest.raises(ValueError, match="completed"):
        evaluate_trajectory(trajectory.iloc[:-1], scenario)


@pytest.mark.parametrize("update", [{"step_ft": float("nan")}, {"thickness_ft": -1.0},
                                   {"landing_md_ft": 400.0}, {"landing_center_tvd_ft": 1200.0}])
def test_invalid_scenario_parameters_are_rejected(update) -> None:
    scenario = default_scenario()
    with pytest.raises(ValueError):
        type(scenario).model_validate({**scenario.model_dump(), **update})
