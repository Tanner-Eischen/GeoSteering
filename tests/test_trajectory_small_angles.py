import numpy as np
import pandas as pd
import pytest

from app.alg.trajectory_min_curve import compute_trajectory


@pytest.mark.parametrize("angle", [1e-10, 1e-7, 1e-5, 0.001])
def test_tiny_inclination_build_retains_analytic_dogleg(angle):
    survey = pd.DataFrame({"md_ft": [0.0, 100.0], "inc_deg": [0.0, angle], "azi_deg": [0.0, 0.0]})
    result = compute_trajectory(survey).iloc[-1]
    assert result["dogleg_deg"] == pytest.approx(angle, rel=1e-12)
    assert result["dls_deg_per_100ft"] == pytest.approx(angle, rel=1e-12)
    # Integral of a continuously building direction over exactly 100 ft.
    radians = np.deg2rad(angle)
    assert result["tvd_ft"] == pytest.approx(100 * np.sinc(radians / np.pi), abs=1e-12)
    expected_north = 100 * 2 * np.sin(radians / 2) ** 2 / radians
    assert result["north_ft"] == pytest.approx(expected_north, rel=1e-12)


def test_tiny_azimuth_change_across_wrap_is_retained():
    survey = pd.DataFrame({"md_ft": [0.0, 100.0], "inc_deg": [90.0, 90.0], "azi_deg": [359.9999999, 0.0]})
    assert compute_trajectory(survey).iloc[-1]["dogleg_deg"] == pytest.approx(1e-7, abs=5e-14)


def test_opposite_directions_fail_instead_of_producing_singular_arc():
    survey = pd.DataFrame({"md_ft": [0.0, 100.0], "inc_deg": [0.0, 180.0], "azi_deg": [0.0, 0.0]})
    with pytest.raises(ValueError, match="unique"):
        compute_trajectory(survey)
