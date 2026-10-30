from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory
from app.model.schemas import ControlPoint, DLSExceedance, PlanParameters


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
    if parameters.build_rate_hint_deg_per_100ft is not None:
        actual_rate = 9000 / (parameters.landing_md_ft - parameters.kickoff_md_ft)
        if abs(actual_rate - parameters.build_rate_hint_deg_per_100ft) > 1e-6:
            raise ValueError("Build-rate hint conflicts with specified kickoff and landing MD.")

    total_md = parameters.landing_md_ft + parameters.lateral_length_ft
    md = np.unique(np.append(_md_grid(total_md, parameters.step_ft), [parameters.kickoff_md_ft, parameters.landing_md_ft]))

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
    if not np.isfinite(dls_max_deg_per_100ft) or dls_max_deg_per_100ft <= 0:
        raise ValueError("DLS limit must be positive and finite.")
    exceed = stations[stations["dls_deg_per_100ft"] > dls_max_deg_per_100ft + 1e-8]
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


def plan_to_target(
    top_control_points: list[ControlPoint],
    base_control_points: list[ControlPoint],
    *,
    kickoff_md_ft: float = 500.0,
    lateral_length_ft: float = 5000.0,
    dls_max_deg_per_100ft: float = 6.0,
    step_ft: float = 50.0,
) -> tuple[PlanParameters, PlanGenerationResult]:
    """Solve a constant-build eastward landing on an offset-derived centerline.

    The two-point regional model is a planning assumption. The solver rejects
    infeasible depth/curvature combinations rather than silently relaxing DLS.
    """
    if len(top_control_points) != 2 or len(base_control_points) != 2:
        raise ValueError("Target planning requires a two-point regional spatial model.")
    if any(p.x_ft is None for p in top_control_points + base_control_points):
        raise ValueError("Target planning requires spatial horizon coordinates.")
    from app.alg.interpretation_model import evaluate_piecewise_linear

    knots = sorted({float(point.x_ft) for point in top_control_points + base_control_points})
    tops = evaluate_piecewise_linear(top_control_points, knots, False)
    bases = evaluate_piecewise_linear(base_control_points, knots, False)
    if np.any(bases <= tops):
        raise ValueError("Target top/base must define a strictly positive thickness throughout their spatial support.")
    x = np.array([0.0, 1000.0])
    center = (evaluate_piecewise_linear(top_control_points, x, False) + evaluate_piecewise_linear(base_control_points, x, False)) / 2
    slope = float((center[1] - center[0]) / 1000)
    if slope >= 1 or not np.isfinite(dls_max_deg_per_100ft) or dls_max_deg_per_100ft <= 0:
        raise ValueError("No feasible landing for this regional slope or DLS limit.")
    build_length = (float(center[0]) - kickoff_md_ft) * np.pi / (2 * (1 - slope))
    if build_length <= 0 or 9000 / build_length > dls_max_deg_per_100ft + 1e-8:
        raise ValueError("No feasible constant-build landing at this kickoff depth and DLS limit.")
    parameters = PlanParameters(
        kickoff_md_ft=kickoff_md_ft, landing_md_ft=kickoff_md_ft + build_length,
        lateral_length_ft=lateral_length_ft, planned_azi_deg=90, step_ft=step_ft,
        build_rate_hint_deg_per_100ft=9000 / build_length,
    )
    result = generate_plan(parameters, dls_max_deg_per_100ft)
    if result.exceedances:
        raise ValueError("Generated landing exceeds the requested DLS limit.")
    landing = result.stations.loc[np.isclose(result.stations.md_ft, parameters.landing_md_ft)].iloc[0]
    target = (evaluate_piecewise_linear(top_control_points, [landing.east_ft], False)[0] + evaluate_piecewise_linear(base_control_points, [landing.east_ft], False)[0]) / 2
    if abs(landing.tvd_ft - target) > 0.01:
        raise ValueError("Landing integration failed the target-depth tolerance.")
    return parameters, result

