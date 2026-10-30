from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.model.schemas import ControlPoint


@dataclass
class KPIResult:
    percent_in_zone: float
    avg_center_distance: float
    last_step_in_zone: float
    in_zone_length_ft: float = 0.0
    evaluated_length_ft: float = 0.0
    max_overshoot_ft: float = 0.0


def build_md_grid(md_from_ft: float, md_to_ft: float, step_ft: float = 1.0) -> np.ndarray:
    if not np.isfinite([md_from_ft, md_to_ft, step_ft]).all() or step_ft <= 0:
        raise ValueError("Depth bounds must be finite and step_ft positive.")
    if md_to_ft < md_from_ft:
        raise ValueError("md_to_ft must be >= md_from_ft")
    grid = np.arange(md_from_ft, md_to_ft, step_ft)
    return np.append(grid, md_to_ft)


def compute_kpis(
    trajectory_df: pd.DataFrame,
    top_control_points: Sequence[ControlPoint],
    base_control_points: Sequence[ControlPoint],
    md_from_ft: float,
    md_to_ft: float,
    step_ft: float = 1.0,
) -> KPIResult:
    """Integrate piecewise-linear geometry exactly in measured-depth length.

    step_ft is retained for compatibility; scores do not depend on it.
    last_step_in_zone describes the final point, not a step-length fraction.
    Spatial horizons use x=east in the shared local reference. Legacy MD-based
    horizons remain readable, but cannot support cross-strategy comparisons.
    """
    if not np.isfinite([md_from_ft, md_to_ft, step_ft]).all() or step_ft <= 0 or md_to_ft < md_from_ft:
        raise ValueError("Finite ordered depth bounds and a positive step are required.")
    if trajectory_df.empty:
        raise ValueError("Cannot score an empty trajectory.")
    traj = trajectory_df.sort_values("md_ft")
    md = traj["md_ft"].to_numpy(dtype=float)
    tvd = traj["tvd_ft"].to_numpy(dtype=float)
    if not np.isfinite(md).all() or not np.isfinite(tvd).all() or np.any(np.diff(md) <= 0):
        raise ValueError("Trajectory must have finite values and unique increasing MD.")
    if md_from_ft < md[0] - 1e-8 or md_to_ft > md[-1] + 1e-8:
        raise ValueError("Cannot score outside observed trajectory support.")
    all_points = list(top_control_points) + list(base_control_points)
    spatial_flags = [p.x_ft is not None for p in all_points]
    if any(spatial_flags) and not all(spatial_flags):
        raise ValueError("Top and base must use the same coordinate basis.")
    spatial = all(spatial_flags)
    coord = traj["x_ft" if "x_ft" in traj else "east_ft"].to_numpy(dtype=float) if spatial else md
    if not np.isfinite(coord).all():
        raise ValueError("Trajectory coordinates must be finite.")
    knots = [p.x_ft if spatial else p.md_ft for p in all_points]
    breaks = [md_from_ft, md_to_ft, *md[(md > md_from_ft) & (md < md_to_ft)]]
    # Geological knots may be crossed more than once on a returning path.
    for i in range(len(md) - 1):
        if coord[i + 1] == coord[i]:
            continue
        for knot in knots:
            fraction = (knot - coord[i]) / (coord[i + 1] - coord[i])
            crossing = md[i] + fraction * (md[i + 1] - md[i])
            if 0 < fraction < 1 and md_from_ft < crossing < md_to_ft:
                breaks.append(crossing)
    grid = np.unique(breaks)
    query = np.interp(grid, md, coord)
    well = np.interp(grid, md, tvd)
    top = evaluate_piecewise_linear(top_control_points, query)
    base = evaluate_piecewise_linear(base_control_points, query)
    if np.any(base < top):
        raise ValueError("Formation base must not be above top.")
    above_top = well - top
    below_base = base - well
    distance = well - (top + base) / 2
    lengths = np.diff(grid)
    in_length = 0.0
    distance_integral = 0.0
    for i, length in enumerate(lengths):
        low, high = 0.0, 1.0
        for residual in (above_top, below_base):
            a, b = residual[i], residual[i + 1]
            if a < 0 and b < 0:
                high = -1.0
                break
            if a < 0 <= b:
                low = max(low, -a / (b - a))
            elif b < 0 <= a:
                high = min(high, a / (a - b))
        in_length += length * max(0.0, high - low)
        a, b = distance[i], distance[i + 1]
        if a * b >= 0:
            distance_integral += length * (abs(a) + abs(b)) / 2
        else:
            distance_integral += length * (a * a + b * b) / (2 * (abs(a) + abs(b)))
    total = float(md_to_ft - md_from_ft)
    return KPIResult(
        percent_in_zone=float(100 * in_length / total) if total else 0.0,
        avg_center_distance=float(distance_integral / total) if total else 0.0,
        last_step_in_zone=float(above_top[-1] >= 0 and below_base[-1] >= 0) * 100,
        in_zone_length_ft=float(in_length),
        evaluated_length_ft=total,
        max_overshoot_ft=float(max(0, -above_top.min(), -below_base.min())),
    )

