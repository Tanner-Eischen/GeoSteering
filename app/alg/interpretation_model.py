from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

from app.model.schemas import ControlPoint


def add_or_update_control_point(points: Sequence[ControlPoint], md_ft: float, tvd_ft: float) -> list[ControlPoint]:
    updated = list(points)
    replaced = False
    for idx, cp in enumerate(updated):
        if abs(cp.md_ft - md_ft) < 1e-9:
            updated[idx] = ControlPoint(md_ft=md_ft, tvd_ft=tvd_ft)
            replaced = True
            break
    if not replaced:
        updated.append(ControlPoint(md_ft=md_ft, tvd_ft=tvd_ft))
    return sorted(updated, key=lambda p: p.md_ft)


def evaluate_piecewise_linear(points: Sequence[ControlPoint], md_query: Iterable[float], hold_constant: bool = True) -> np.ndarray:
    if len(points) < 2:
        raise ValueError("At least two control points are required for evaluation.")
    ordered = sorted(points, key=lambda p: p.md_ft)
    x = np.array([p.md_ft for p in ordered], dtype=float)
    y = np.array([p.tvd_ft for p in ordered], dtype=float)
    md = np.array(list(md_query), dtype=float)

    if hold_constant:
        return np.interp(md, x, y, left=float(y[0]), right=float(y[-1]))
    return np.interp(md, x, y)


def validate_top_base_ordering(
    top_points: Sequence[ControlPoint],
    base_points: Sequence[ControlPoint],
    md_grid: Iterable[float],
) -> None:
    top = evaluate_piecewise_linear(top_points, md_grid)
    base = evaluate_piecewise_linear(base_points, md_grid)
    if np.any(base < top):
        raise ValueError("Invalid interpretation: base_tvd_ft is above top_tvd_ft in the evaluation range.")

