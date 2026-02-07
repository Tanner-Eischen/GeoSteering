from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _as_radians(series: pd.Series) -> np.ndarray:
    return np.deg2rad(series.to_numpy(dtype=float))


def compute_trajectory(survey_df: pd.DataFrame) -> pd.DataFrame:
    required = {"md_ft", "inc_deg", "azi_deg"}
    missing = required - set(survey_df.columns)
    if missing:
        raise ValueError(f"Survey is missing required columns: {sorted(missing)}")

    survey = survey_df.sort_values("md_ft").reset_index(drop=True).copy()
    md = survey["md_ft"].to_numpy(dtype=float)
    inc = _as_radians(survey["inc_deg"])
    azi = _as_radians(survey["azi_deg"])

    n = len(survey)
    tvd = np.zeros(n, dtype=float)
    north = np.zeros(n, dtype=float)
    east = np.zeros(n, dtype=float)
    dogleg_deg = np.zeros(n, dtype=float)
    dls = np.zeros(n, dtype=float)

    for i in range(1, n):
        dm = md[i] - md[i - 1]
        if dm <= 0:
            raise ValueError("Survey md_ft must be strictly increasing.")

        inc1, inc2 = inc[i - 1], inc[i]
        azi1, azi2 = azi[i - 1], azi[i]

        cos_dogleg = math.cos(inc2 - inc1) - (math.sin(inc1) * math.sin(inc2)) * (1.0 - math.cos(azi2 - azi1))
        cos_dogleg = float(np.clip(cos_dogleg, -1.0, 1.0))
        dogleg = math.acos(cos_dogleg)

        if abs(dogleg) < 1e-8:
            rf = 1.0
        else:
            rf = (2.0 / dogleg) * math.tan(dogleg / 2.0)

        d_n = (dm / 2.0) * (math.sin(inc1) * math.cos(azi1) + math.sin(inc2) * math.cos(azi2)) * rf
        d_e = (dm / 2.0) * (math.sin(inc1) * math.sin(azi1) + math.sin(inc2) * math.sin(azi2)) * rf
        d_tvd = (dm / 2.0) * (math.cos(inc1) + math.cos(inc2)) * rf

        north[i] = north[i - 1] + d_n
        east[i] = east[i - 1] + d_e
        tvd[i] = tvd[i - 1] + d_tvd

        dl_deg = math.degrees(dogleg)
        dogleg_deg[i] = dl_deg
        dls[i] = (dl_deg / dm) * 100.0

    out = survey.copy()
    out["tvd_ft"] = tvd
    out["north_ft"] = north
    out["east_ft"] = east
    out["dogleg_deg"] = dogleg_deg
    out["dls_deg_per_100ft"] = dls
    return out

