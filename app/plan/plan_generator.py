from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory
from app.model.schemas import DLSExceedance, PlanParameters


@dataclass
class PlanGenerationResult:
    stations: pd.DataFrame
    exceedances: list[DLSExceedance]


def _md_grid(total_md_ft: float, step_ft: float) -> np.ndarray:
    grid = np.arange(0.0, total_md_ft + step_ft, step_ft)
    if grid[-1] > total_md_ft + 1e-9:
        grid[-1] = total_md_ft
    if grid[-1] < total_md_ft:
        grid = np.append(grid, total_md_ft)
    return grid


def generate_plan_stations(parameters: PlanParameters) -> pd.DataFrame:
    if parameters.step_ft <= 0:
        raise ValueError("step_ft must be > 0")
    if parameters.landing_md_ft <= parameters.kickoff_md_ft:
        raise ValueError("landing_md_ft must be greater than kickoff_md_ft")

    total_md = parameters.landing_md_ft + parameters.lateral_length_ft
    md = _md_grid(total_md, parameters.step_ft)

    inc = np.zeros_like(md)
    build_mask = (md >= parameters.kickoff_md_ft) & (md <= parameters.landing_md_ft)
    inc[build_mask] = (md[build_mask] - parameters.kickoff_md_ft) / (
        parameters.landing_md_ft - parameters.kickoff_md_ft
    ) * 90.0
    inc[md > parameters.landing_md_ft] = 90.0
    azi = np.full_like(md, parameters.planned_azi_deg, dtype=float)

    survey = pd.DataFrame({"md_ft": md, "inc_deg": inc, "azi_deg": azi})
    stations = compute_trajectory(survey)
    return stations


def detect_dls_exceedances(stations: pd.DataFrame, dls_max_deg_per_100ft: float) -> list[DLSExceedance]:
    exceed = stations[stations["dls_deg_per_100ft"] > dls_max_deg_per_100ft]
    out: list[DLSExceedance] = []
    for idx in exceed.index:
        if idx == 0:
            continue
        out.append(
            DLSExceedance(
                md_from_ft=float(stations.iloc[idx - 1]["md_ft"]),
                md_to_ft=float(stations.iloc[idx]["md_ft"]),
                dls_deg_per_100ft=float(stations.iloc[idx]["dls_deg_per_100ft"]),
            )
        )
    return out


def generate_plan(parameters: PlanParameters, dls_max_deg_per_100ft: float) -> PlanGenerationResult:
    stations = generate_plan_stations(parameters)
    exceedances = detect_dls_exceedances(stations, dls_max_deg_per_100ft=dls_max_deg_per_100ft)
    return PlanGenerationResult(stations=stations, exceedances=exceedances)

