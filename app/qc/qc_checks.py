from __future__ import annotations

import pandas as pd

from app.qc.qc_models import QCWarning, WellQCResult


def _overlap_ratio(range_a: tuple[float, float], range_b: tuple[float, float]) -> float:
    a_min, a_max = range_a
    b_min, b_max = range_b
    overlap = max(0.0, min(a_max, b_max) - max(a_min, b_min))
    denom = max(1e-9, b_max - b_min)
    return overlap / denom


def _sample_step(md: pd.Series) -> float:
    diffs = md.diff().dropna()
    if diffs.empty:
        return 0.0
    return float(diffs.median())


def run_well_qc(
    well_name: str,
    survey_df: pd.DataFrame,
    logs_df: pd.DataFrame,
    required_curves: list[str] | None = None,
    overlap_threshold: float = 0.8,
) -> WellQCResult:
    required = required_curves or ["GR", "RES"]
    warnings: list[QCWarning] = []

    survey_md_min = float(survey_df["md_ft"].min())
    survey_md_max = float(survey_df["md_ft"].max())
    logs_md_min = float(logs_df["md_ft"].min())
    logs_md_max = float(logs_df["md_ft"].max())

    overlap = _overlap_ratio((survey_md_min, survey_md_max), (logs_md_min, logs_md_max))
    if overlap < overlap_threshold:
        warnings.append(
            QCWarning(
                code="OVERLAP_TOO_LOW",
                message=f"Survey/log overlap ratio {overlap:.3f} is below threshold {overlap_threshold:.3f}.",
            )
        )

    curves_present = sorted([c for c in logs_df.columns if c != "md_ft"])
    missing = [curve for curve in required if curve not in curves_present]
    if missing:
        warnings.append(
            QCWarning(code="MISSING_REQUIRED_CURVES", message=f"Missing required curves: {', '.join(missing)}")
        )

    valid = len(warnings) == 0
    return WellQCResult(
        well_name=well_name,
        md_min_ft=logs_md_min,
        md_max_ft=logs_md_max,
        survey_station_count=int(len(survey_df)),
        curves_present=curves_present,
        sample_step_ft_est=_sample_step(logs_df["md_ft"]),
        overlap_ratio=overlap,
        valid=valid,
        warnings=warnings,
    )

