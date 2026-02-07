from __future__ import annotations

import numpy as np
import pandas as pd


def interp_trajectory(trajectory_df: pd.DataFrame, md_query: float, clamp: bool = True) -> dict[str, float]:
    required = {"md_ft", "tvd_ft", "north_ft", "east_ft"}
    missing = required - set(trajectory_df.columns)
    if missing:
        raise ValueError(f"Trajectory is missing required columns: {sorted(missing)}")

    traj = trajectory_df.sort_values("md_ft")
    md = traj["md_ft"].to_numpy(dtype=float)

    if clamp:
        md_q = float(np.clip(md_query, md.min(), md.max()))
    else:
        if md_query < md.min() or md_query > md.max():
            raise ValueError(f"md_query={md_query} is outside [{md.min()}, {md.max()}]")
        md_q = float(md_query)

    return {
        "md_ft": md_q,
        "tvd_ft": float(np.interp(md_q, md, traj["tvd_ft"].to_numpy(dtype=float))),
        "north_ft": float(np.interp(md_q, md, traj["north_ft"].to_numpy(dtype=float))),
        "east_ft": float(np.interp(md_q, md, traj["east_ft"].to_numpy(dtype=float))),
    }

