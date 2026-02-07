from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory
from app.io.project_store import well_paths


def read_survey_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    df = pd.read_csv(csv_path)
    required = {"md_ft", "inc_deg", "azi_deg"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Survey CSV {csv_path} missing columns: {sorted(missing)}")

    df = df[list(required)].copy()
    df = df.sort_values("md_ft").reset_index(drop=True)

    if df[["md_ft", "inc_deg", "azi_deg"]].isna().any().any():
        raise ValueError(f"Survey CSV {csv_path} contains NaNs in required columns.")
    if not (df["md_ft"].diff().fillna(1.0) > 0).all():
        raise ValueError(f"Survey CSV {csv_path} must have strictly increasing md_ft.")
    if not ((df["inc_deg"] >= 0.0) & (df["inc_deg"] <= 180.0)).all():
        raise ValueError(f"Survey CSV {csv_path} has inc_deg outside [0, 180].")
    if not ((df["azi_deg"] >= 0.0) & (df["azi_deg"] < 360.0)).all():
        raise ValueError(f"Survey CSV {csv_path} has azi_deg outside [0, 360).")
    return df


def import_survey(project_root: str | Path, well_id: str, survey_csv: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    survey_df = read_survey_csv(survey_csv)
    trajectory_df = compute_trajectory(survey_df)

    paths = well_paths(project_root, well_id)
    paths["survey"].parent.mkdir(parents=True, exist_ok=True)
    survey_df.to_parquet(paths["survey"], index=False)
    trajectory_df.to_parquet(paths["trajectory"], index=False)
    return survey_df, trajectory_df

