from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from app.model.schemas import ControlPoint


def add_or_update_control_point(
    points: Sequence[ControlPoint], md_ft: float, tvd_ft: float, *, x_ft: float | None = None
) -> list[ControlPoint]:
    spatial = bool(points) and points[0].x_ft is not None
    if spatial and x_ft is None:
        raise ValueError("Spatial horizons require an explicit x_ft control coordinate.")
    coordinate = x_ft if x_ft is not None else md_ft
    updated = list(points)
    replaced = False
    for idx, cp in enumerate(updated):
        cp_coordinate = cp.x_ft if spatial else cp.md_ft
        if abs(cp_coordinate - coordinate) < 1e-9:
            updated[idx] = ControlPoint(md_ft=md_ft, tvd_ft=tvd_ft, x_ft=x_ft)
            replaced = True
            break
    if not replaced:
        updated.append(ControlPoint(md_ft=md_ft, tvd_ft=tvd_ft, x_ft=x_ft))
    return sorted(updated, key=lambda p: p.x_ft if p.x_ft is not None else p.md_ft)


def evaluate_piecewise_linear(points: Sequence[ControlPoint], md_query: Iterable[float], hold_constant: bool = True) -> np.ndarray:
    if len(points) < 2:
        raise ValueError("At least two control points are required for evaluation.")
    spatial = [p.x_ft is not None for p in points]
    if any(spatial) and not all(spatial):
        raise ValueError("Cannot mix spatial and MD horizon points.")
    ordered = sorted(points, key=lambda p: p.x_ft if all(spatial) else p.md_ft)
    x = np.array([p.x_ft if all(spatial) else p.md_ft for p in ordered], dtype=float)
    y = np.array([p.tvd_ft for p in ordered], dtype=float)
    md = np.array(list(md_query), dtype=float)
    if not np.isfinite(md).all() or np.any(np.diff(x) <= 0):
        raise ValueError("Horizon queries must be finite and control coordinates unique.")

    if hold_constant:
        return np.interp(md, x, y, left=float(y[0]), right=float(y[-1]))
    result = np.interp(md, x, y)
    result = np.where(md < x[0], y[0] + (md - x[0]) * (y[1] - y[0]) / (x[1] - x[0]), result)
    return np.where(md > x[-1], y[-1] + (md - x[-1]) * (y[-1] - y[-2]) / (x[-1] - x[-2]), result)


def validate_top_base_ordering(
    top_points: Sequence[ControlPoint],
    base_points: Sequence[ControlPoint],
    md_grid: Iterable[float],
) -> None:
    top = evaluate_piecewise_linear(top_points, md_grid)
    base = evaluate_piecewise_linear(base_points, md_grid)
    if np.any(base < top):
        raise ValueError("Invalid interpretation: base_tvd_ft is above top_tvd_ft in the evaluation range.")

