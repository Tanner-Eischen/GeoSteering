from __future__ import annotations

import numpy as np
import pandas as pd

from app.geo.formation import Scenario, formation_top_base

# Public synthetic sensor calibration. This is an idealized continuous layer
# signature, not a claim about inversion of real gamma-ray measurements.
GR_CENTER_API = 80.0
GR_GRADIENT_API_PER_FT = 2.0
GR_NOISE_STD_API = 0.6


def sample_logs(trajectory_df: pd.DataFrame, scenario: Scenario, seed: int = 123) -> pd.DataFrame:
    x = trajectory_df["x_ft" if "x_ft" in trajectory_df else "east_ft"].to_numpy(dtype=float)
    top, base = formation_top_base(x, scenario)
    relative = trajectory_df["tvd_ft"].to_numpy(dtype=float) - (top + base) / 2.0
    rng = np.random.default_rng(seed)
    gr = np.clip(GR_CENTER_API + GR_GRADIENT_API_PER_FT * relative, 20.0, 160.0)
    gr = gr + rng.normal(0.0, GR_NOISE_STD_API, len(relative))
    res = np.clip(40.0 * np.exp(-np.abs(relative) / 18.0) + rng.normal(0.0, 0.3, len(relative)), 0.2, None)
    return pd.DataFrame({"md_ft": trajectory_df["md_ft"].to_numpy(), "GR": gr, "RES": res})


def observed_center_tvd(tvd_ft: float, gr_api: float) -> float:
    """Infer local center using only the current sensor and public calibration.

    Saturated GR cannot uniquely locate the center. Callers must document that
    limitation; the flagship lateral remains within the calibrated range.
    """
    return tvd_ft - (gr_api - GR_CENTER_API) / GR_GRADIENT_API_PER_FT
