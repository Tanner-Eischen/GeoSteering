from __future__ import annotations

import numpy as np
import pandas as pd

from app.qc.qc_models import QCWarning, WellQCResult


def _overlap_ratio(range_a: tuple[float, float], range_b: tuple[float, float]) -> float:
    a_min, a_max = range_a
    b_min, b_max = range_b
    return max(0.0, min(a_max, b_max) - max(a_min, b_min)) / max(1e-9, b_max - b_min)


def run_well_qc(
    well_name: str,
    survey_df: pd.DataFrame,
    logs_df: pd.DataFrame,
    required_curves: list[str] | None = None,
    overlap_threshold: float = 0.8,
) -> WellQCResult:
    required = required_curves or ["GR", "RES"]
    warnings: list[QCWarning] = []

    def issue(code: str, message: str, severity: str = "error") -> None:
        warnings.append(QCWarning(code=code, message=message, severity=severity))

    for label, frame in (("SURVEY", survey_df), ("LOG", logs_df)):
        if "md_ft" not in frame or frame.empty:
            issue(f"{label}_EMPTY", f"{label} requires measured-depth samples.")
            continue
        md = frame["md_ft"].to_numpy(dtype=float)
        if not np.isfinite(md).all() or np.any(md < 0):
            issue(f"{label}_INVALID_DEPTH", f"{label} depths must be finite and nonnegative.")
        if np.any(np.diff(md) <= 0):
            issue(f"{label}_DEPTH_ORDER", f"{label} depths must be unique and strictly increasing.")
        gaps = np.diff(md)
        if len(gaps) and np.median(gaps) > 0 and np.max(gaps) > 5 * np.median(gaps):
            issue(f"{label}_GAPS", f"{label} has gaps greater than five median sample intervals.", "warning")
    for column, lower, upper in (("inc_deg", 0, 180), ("azi_deg", 0, 360)):
        if column not in survey_df:
            issue("SURVEY_COLUMNS", f"Missing survey column {column}.")
        else:
            values = survey_df[column].to_numpy(dtype=float)
            outside = (values < lower) | (values > upper if column == "inc_deg" else values >= upper)
            if not np.isfinite(values).all() or outside.any():
                issue("SURVEY_ANGLES", f"Invalid or nonfinite survey {column}.")
    curves_present = sorted(c for c in logs_df if c != "md_ft")
    for curve in required:
        if curve not in logs_df:
            issue("MISSING_REQUIRED_CURVES", f"Missing required curve: {curve}.")
            continue
        values = pd.to_numeric(logs_df[curve], errors="coerce").to_numpy(dtype=float)
        missing = float(np.mean(~np.isfinite(values))) if len(values) else 1.0
        if np.isinf(values).any():
            issue("INFINITE_CURVE", f"{curve} contains infinite values.")
        if missing > 0.4:
            issue("EXCESSIVE_NULLS", f"{curve} missing fraction {missing:.1%} exceeds 40%.")
        elif missing > 0.05:
            issue("CURVE_NULLS", f"{curve} missing fraction {missing:.1%} exceeds 5%.", "warning")
        if curve == "RES" and np.any(values[np.isfinite(values)] <= 0):
            issue("NONPOSITIVE_RES", "Nonpositive resistivity requires review.", "warning")

    def depth_range(frame: pd.DataFrame) -> tuple[float, float]:
        if "md_ft" not in frame:
            return 0.0, 0.0
        finite = frame["md_ft"][np.isfinite(frame["md_ft"])]
        return (float(finite.min()), float(finite.max())) if len(finite) else (0.0, 0.0)

    survey_range, logs_range = depth_range(survey_df), depth_range(logs_df)
    overlap = _overlap_ratio(survey_range, logs_range)
    if overlap < overlap_threshold:
        issue("OVERLAP_TOO_LOW", f"Survey/log overlap {overlap:.3f} is below {overlap_threshold:.3f}.")
    elif overlap < 1 - 1e-9:
        issue("PARTIAL_SUPPORT", "Some log depths lie outside survey coverage.", "warning")
    step = logs_df["md_ft"].diff().median() if "md_ft" in logs_df and len(logs_df) > 1 else 0.0
    return WellQCResult(
        well_name=well_name, md_min_ft=logs_range[0], md_max_ft=logs_range[1],
        survey_station_count=len(survey_df), curves_present=curves_present,
        sample_step_ft_est=float(step) if np.isfinite(step) else 0.0,
        overlap_ratio=overlap, valid=not any(w.severity == "error" for w in warnings), warnings=warnings,
    )

