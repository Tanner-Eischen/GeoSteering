from __future__ import annotations

from pathlib import Path
from typing import Dict
import os

import numpy as np
import pandas as pd

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import read_json
from app.plot.correlation_panel import build_correlation_figure
from app.plot.dls_plot import build_dls_figure
from app.plot.plan_profile import build_plan_profile_figure
from app.plot.steering import build_interpretation_overlay_figure, build_kpi_trend_figure
from app.services.decisions import load_decisions
from app.services.interpretations import get_latest_interpretation
from app.services.markers import load_markers
from app.services.project_data import load_project_and_wells, load_well_frames


def _write_image(fig, out_path: Path, width: int = 1200, height: int = 700) -> Path | None:
    if os.environ.get("GEOSTEERING_ENABLE_SNAPSHOTS", "0") != "1":
        return None
    try:
        fig.write_image(str(out_path), width=width, height=height, scale=1)
        return out_path
    except Exception:
        return None


def generate_report_snapshots(project_root: str | Path) -> Dict[str, Path]:
    root = Path(project_root)
    snap_dir = root / "cache" / "report_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, Path] = {}

    project, wells = load_project_and_wells(root)
    if wells:
        refs = {w.name: w.well_id for w in wells}
        selected = list(refs.keys())[:3]
        logs_by_well = {}
        markers_by_well = {}
        for name in selected:
            frames = load_well_frames(root, refs[name])
            logs = frames["logs"]
            if len(logs) > 2000:
                stride = int(np.ceil(len(logs) / 2000))
                logs = logs.iloc[::stride].reset_index(drop=True)
            logs_by_well[name] = logs
            markers_by_well[name] = [m.model_dump(mode="json") for m in load_markers(root, refs[name])]
        corr_fig = build_correlation_figure(logs_by_well=logs_by_well, markers_by_well=markers_by_well, curves=["GR"])
        out = _write_image(corr_fig, snap_dir / "correlation_snapshot.png")
        if out:
            outputs["correlation_snapshot"] = out

    plan_jsons = sorted((root / "plans").glob("*.json"))
    if plan_jsons:
        latest_plan = read_json(plan_jsons[-1])
        stations = pd.read_parquet(root / latest_plan["stations_path"])
        plan_fig = build_plan_profile_figure(stations)
        dls_fig = build_dls_figure(stations, max_dls_deg_per_100ft=float(latest_plan["dls_max_deg_per_100ft"]))
        out1 = _write_image(plan_fig, snap_dir / "plan_profile.png")
        out2 = _write_image(dls_fig, snap_dir / "dls_profile.png")
        if out1:
            outputs["plan_profile"] = out1
        if out2:
            outputs["dls_profile"] = out2

    latest_interp = get_latest_interpretation(root)
    if latest_interp and project.active_well_id:
        frames = load_well_frames(root, project.active_well_id)
        traj = frames["trajectory"]
        md_grid = np.linspace(float(traj["md_ft"].min()), float(traj["md_ft"].max()), 300)
        top = evaluate_piecewise_linear(latest_interp.top_control_points, md_grid, hold_constant=True)
        base = evaluate_piecewise_linear(latest_interp.base_control_points, md_grid, hold_constant=True)
        interp_fig = build_interpretation_overlay_figure(trajectory_df=traj, md_grid=md_grid, top_tvd=top, base_tvd=base)
        out3 = _write_image(interp_fig, snap_dir / "interpretation_overlay.png")
        if out3:
            outputs["interpretation_overlay"] = out3

        decisions = load_decisions(root)
        if decisions:
            kpi_fig = build_kpi_trend_figure(
                step_index=[d.step_index for d in decisions],
                percent_in_zone=[0.0 for _ in decisions],
            )
            out4 = _write_image(kpi_fig, snap_dir / "kpi_trend.png")
            if out4:
                outputs["kpi_trend"] = out4

    return outputs
