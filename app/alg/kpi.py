from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from app.alg.interpretation_model import evaluate_piecewise_linear, validate_top_base_ordering
from app.model.schemas import ControlPoint


@dataclass
class KPIResult:
    percent_in_zone: float
    avg_center_distance: float
    last_step_in_zone: float


def build_md_grid(md_from_ft: float, md_to_ft: float, step_ft: float = 1.0) -> np.ndarray:
    if md_to_ft < md_from_ft:
        raise ValueError("md_to_ft must be >= md_from_ft")
    grid = np.arange(md_from_ft, md_to_ft + step_ft, step_ft)
    if grid[-1] > md_to_ft:
        grid[-1] = md_to_ft
    return grid


def compute_kpis(
    trajectory_df: pd.DataFrame,
    top_control_points: Sequence[ControlPoint],
    base_control_points: Sequence[ControlPoint],
    md_from_ft: float,
    md_to_ft: float,
    step_ft: float = 1.0,
) -> KPIResult:
    grid = build_md_grid(md_from_ft=md_from_ft, md_to_ft=md_to_ft, step_ft=step_ft)
    validate_top_base_ordering(top_control_points, base_control_points, grid)

    traj = trajectory_df.sort_values("md_ft")
    tvd_well = np.interp(grid, traj["md_ft"].to_numpy(dtype=float), traj["tvd_ft"].to_numpy(dtype=float))
    tvd_top = evaluate_piecewise_linear(top_control_points, grid, hold_constant=True)
    tvd_base = evaluate_piecewise_linear(base_control_points, grid, hold_constant=True)

    in_zone = (tvd_well >= tvd_top) & (tvd_well <= tvd_base)
    center = (tvd_top + tvd_base) / 2.0
    center_dist = np.abs(tvd_well - center)

    return KPIResult(
        percent_in_zone=float(np.mean(in_zone) * 100.0),
        avg_center_distance=float(np.mean(center_dist)),
        last_step_in_zone=float(in_zone[-1] * 100.0),
    )

