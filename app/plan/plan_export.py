from __future__ import annotations

from pathlib import Path

import pandas as pd

PLAN_EXPORT_COLUMNS = [
    "md_ft",
    "inc_deg",
    "azi_deg",
    "tvd_ft",
    "north_ft",
    "east_ft",
    "dls_deg_per_100ft",
]


def export_plan_csv(stations: pd.DataFrame, out_csv: str | Path) -> Path:
    missing = [c for c in PLAN_EXPORT_COLUMNS if c not in stations.columns]
    if missing:
        raise ValueError(f"Plan stations missing required columns: {missing}")
    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stations[PLAN_EXPORT_COLUMNS].to_csv(out_path, index=False)
    return out_path

