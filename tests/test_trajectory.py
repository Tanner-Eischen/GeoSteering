from __future__ import annotations

import numpy as np
import pandas as pd

from app.alg.trajectory_interp import interp_trajectory
from app.alg.trajectory_min_curve import compute_trajectory


def test_min_curve_vertical_well() -> None:
    survey = pd.DataFrame(
        {
            "md_ft": [0.0, 100.0, 200.0, 300.0],
            "inc_deg": [0.0, 0.0, 0.0, 0.0],
            "azi_deg": [0.0, 10.0, 20.0, 30.0],
        }
    )
    traj = compute_trajectory(survey)
    np.testing.assert_allclose(traj["tvd_ft"], traj["md_ft"], atol=1e-6)
    np.testing.assert_allclose(traj["north_ft"], 0.0, atol=1e-6)
    np.testing.assert_allclose(traj["east_ft"], 0.0, atol=1e-6)
    np.testing.assert_allclose(traj["dogleg_deg"], 0.0, atol=1e-6)


def test_min_curve_constant_inc_azi() -> None:
    survey = pd.DataFrame(
        {
            "md_ft": [0.0, 100.0, 200.0, 300.0],
            "inc_deg": [60.0, 60.0, 60.0, 60.0],
            "azi_deg": [90.0, 90.0, 90.0, 90.0],
        }
    )
    traj = compute_trajectory(survey)
    # Constant inc/azi should have zero dogleg.
    np.testing.assert_allclose(traj["dogleg_deg"], 0.0, atol=1e-6)
    np.testing.assert_allclose(traj["dls_deg_per_100ft"], 0.0, atol=1e-6)

    expected_east = survey["md_ft"] * np.sin(np.deg2rad(60.0))
    expected_tvd = survey["md_ft"] * np.cos(np.deg2rad(60.0))
    np.testing.assert_allclose(traj["east_ft"], expected_east, atol=1e-3)
    np.testing.assert_allclose(traj["tvd_ft"], expected_tvd, atol=1e-3)


def test_interp_midpoint() -> None:
    traj = pd.DataFrame(
        {
            "md_ft": [0.0, 100.0],
            "tvd_ft": [0.0, 50.0],
            "north_ft": [0.0, 10.0],
            "east_ft": [0.0, 20.0],
        }
    )
    out = interp_trajectory(traj, md_query=50.0, clamp=False)
    assert out["tvd_ft"] == 25.0
    assert out["north_ft"] == 5.0
    assert out["east_ft"] == 10.0

