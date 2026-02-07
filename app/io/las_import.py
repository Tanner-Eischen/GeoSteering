from __future__ import annotations

from pathlib import Path
from typing import Dict

import lasio
import numpy as np
import pandas as pd

from app.io.curve_normalize import normalize_curve_table
from app.io.project_store import well_paths
from app.model.schemas import CurveMeta

FT_PER_M = 3.280839895013123


def _depth_factor_to_feet(unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"ft", "feet"}:
        return 1.0
    if u in {"m", "meter", "metre", "meters", "metres"}:
        return FT_PER_M
    # Default to feet for unknown depth units in MVP.
    return 1.0


def _estimate_step(md_series: pd.Series) -> float:
    diffs = md_series.diff().dropna()
    if diffs.empty:
        return 0.0
    return float(diffs.median())


def read_las(path: str | Path) -> tuple[pd.DataFrame, Dict[str, CurveMeta]]:
    las_path = Path(path)
    las = lasio.read(str(las_path))
    raw_df = las.df().reset_index()

    depth_col = raw_df.columns[0]
    depth_unit = ""
    if las.curves:
        depth_unit = str(las.curves[0].unit or "")
    factor = _depth_factor_to_feet(depth_unit)
    raw_df = raw_df.rename(columns={depth_col: "md_raw"})
    raw_df["md_ft"] = pd.to_numeric(raw_df["md_raw"], errors="coerce") * factor
    raw_df = raw_df.drop(columns=["md_raw"])

    normalized, alias_map = normalize_curve_table(raw_df)
    if "GR" not in normalized.columns or "RES" not in normalized.columns:
        raise ValueError(f"LAS {las_path} must contain GR and one resistivity alias that maps to RES.")

    normalized = normalized.sort_values("md_ft").reset_index(drop=True)

    units_by_curve = {str(c.mnemonic).upper(): str(c.unit or "") for c in las.curves}
    inventory: Dict[str, CurveMeta] = {}
    for canonical, sources in sorted(alias_map.items()):
        source = sources[0]
        unit = units_by_curve.get(source.upper(), "")
        inventory[canonical] = CurveMeta(
            canonical_name=canonical,
            original_mnemonics=sorted(sources),
            unit=unit,
            sample_step_ft_est=_estimate_step(normalized["md_ft"]),
            depth_min_ft=float(normalized["md_ft"].min()),
            depth_max_ft=float(normalized["md_ft"].max()),
        )

    return normalized, inventory


def import_las(project_root: str | Path, well_id: str, las_path: str | Path) -> tuple[pd.DataFrame, Dict[str, CurveMeta]]:
    logs_df, inventory = read_las(las_path)
    paths = well_paths(project_root, well_id)
    paths["logs"].parent.mkdir(parents=True, exist_ok=True)
    logs_df.to_parquet(paths["logs"], index=False)
    return logs_df, inventory

