from __future__ import annotations

from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from app.plot.log_tracks import build_log_tracks_figure
from app.services.project_data import load_project_and_wells, load_simulation_revealed_md, load_well_frames
from app.ui.theme import render_page_header


def _default_well_id(project, wells) -> str | None:
    if project.active_well_id:
        return project.active_well_id
    if wells:
        return wells[0].well_id
    return None


def _series_for_range(logs, curve: str, depth_min: float | None, depth_max: float | None, log_scale: bool) -> np.ndarray:
    df = logs
    if depth_min is not None:
        df = df[df["md_ft"] >= float(depth_min)]
    if depth_max is not None:
        df = df[df["md_ft"] <= float(depth_max)]
    series = (
        np.asarray(df[curve])
        if curve in df.columns
        else np.asarray([])
    )
    series = np.array(series, dtype="float64")
    series = series[np.isfinite(series)]
    if log_scale:
        series = series[series > 0]
    return series


def _range_stats(series: np.ndarray) -> tuple[float, float, float, float] | None:
    if series.size == 0:
        return None
    vmin = float(series.min())
    vmax = float(series.max())
    p01 = float(np.quantile(series, 0.01))
    p99 = float(np.quantile(series, 0.99))
    low = max(vmin, p01)
    high = min(vmax, p99)
    if low >= high:
        low, high = vmin, vmax
    return vmin, vmax, low, high


def _range_stats_log(series: np.ndarray) -> tuple[float, float, float, float] | None:
    series = series[series > 0]
    if series.size == 0:
        return None
    log_series = np.log10(series)
    vmin = float(log_series.min())
    vmax = float(log_series.max())
    p01 = float(np.quantile(log_series, 0.01))
    p99 = float(np.quantile(log_series, 0.99))
    low = max(vmin, p01)
    high = min(vmax, p99)
    if low >= high:
        low, high = vmin, vmax
    return vmin, vmax, low, high


def _slider_step(vmin: float, vmax: float) -> float:
    span = max(1e-9, vmax - vmin)
    step = span / 1000.0
    return float(step)


def _log_slider_step() -> float:
    return 0.01


def render(project_root: str | None) -> None:
    render_page_header(
        "Well Viewer",
        "Single-well log and trajectory inspection with marker overlays and simulation bit-depth context.",
    )
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    project, wells = load_project_and_wells(root)
    if not wells:
        st.info("No wells imported yet.")
        return

    well_map = {w.name: w.well_id for w in wells}
    default_well = _default_well_id(project, wells)
    default_name = next((name for name, wid in well_map.items() if wid == default_well), list(well_map.keys())[0])
    selected_name = st.selectbox("Well", options=list(well_map.keys()), index=list(well_map.keys()).index(default_name))
    selected_well_id = well_map[selected_name]

    frames = load_well_frames(root, selected_well_id)
    logs = frames["logs"]
    trajectory = frames["trajectory"]
    markers = frames["markers"]
    if logs.empty or trajectory.empty:
        st.info("No measurements have been revealed for this well yet.")
        return
    st.caption("Active-well logs, markers, trajectory and scaling statistics are restricted to acquired records during a run.")
    available_curves = [c for c in logs.columns if c != "md_ft"]
    default_curves = [c for c in ["GR", "RES"] if c in available_curves]
    with st.expander("Viewer Controls", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        selected_curves = c1.multiselect("Curves", options=available_curves, default=default_curves)
        depth_mode = c2.selectbox("Depth Range", options=["Full", "Last 1000 ft", "Custom"])
        bit_md = load_simulation_revealed_md(root)
        c3.metric("Bit MD (ft)", f"{bit_md:.1f}" if bit_md is not None else "N/A")

    depth_min = None
    depth_max = None
    if depth_mode == "Last 1000 ft":
        depth_max = float(logs["md_ft"].max())
        depth_min = max(float(logs["md_ft"].min()), depth_max - 1000.0)
    elif depth_mode == "Custom":
        c1, c2 = st.columns(2)
        depth_min = c1.number_input("Depth Min (ft)", value=float(logs["md_ft"].min()))
        depth_max = c2.number_input("Depth Max (ft)", value=float(logs["md_ft"].max()))

    x_ranges: dict[str, tuple[float, float]] = {}
    exclude_outliers = False
    with st.expander("Scale & Outliers", expanded=False):
        range_mode = st.selectbox("X-axis range", options=["Auto", "Manual"], index=0)
        exclude_outliers = st.checkbox("Exclude values outside range (visual only)", value=False)

        if range_mode == "Manual" or exclude_outliers:
            for curve in selected_curves:
                log_scale = curve.upper() == "RES"
                series = _series_for_range(logs, curve, depth_min, depth_max, log_scale=log_scale)
                if log_scale:
                    stats = _range_stats_log(series)
                else:
                    stats = _range_stats(series)
                if stats is None:
                    st.caption(f"{curve}: no numeric data available in current depth window.")
                    continue
                vmin, vmax, low, high = stats
                if vmax <= vmin:
                    st.caption(f"{curve}: insufficient range for scaling.")
                    continue
                if log_scale:
                    step = _log_slider_step()
                    selected = st.slider(
                        f"{curve} log10 range",
                        min_value=float(vmin),
                        max_value=float(vmax),
                        value=(float(low), float(high)),
                        step=step,
                        key=f"range_{curve}",
                    )
                    x_ranges[curve] = (float(10 ** selected[0]), float(10 ** selected[1]))
                    st.caption(f"{curve} range: {10 ** selected[0]:.3g} to {10 ** selected[1]:.3g}")
                else:
                    step = _slider_step(vmin, vmax)
                    selected = st.slider(
                        f"{curve} range",
                        min_value=float(vmin),
                        max_value=float(vmax),
                        value=(float(low), float(high)),
                        step=step,
                        key=f"range_{curve}",
                    )
                    x_ranges[curve] = (float(selected[0]), float(selected[1]))

    fig, meta = build_log_tracks_figure(
        logs_df=logs,
        markers=markers,
        curves=selected_curves,
        depth_min=depth_min,
        depth_max=depth_max,
        bit_md_ft=bit_md,
        x_ranges=x_ranges if x_ranges else None,
        exclude_outliers=exclude_outliers,
    )
    tab1, tab2 = st.tabs(["Logs", "Trajectory"])
    with tab1:
        st.markdown("#### Log Tracks")
        st.plotly_chart(fig, use_container_width=True)
        if "RES" in selected_curves:
            st.caption(f"RES clipped (<=0): {meta.clipped_res_count}")
        if exclude_outliers and meta.excluded_by_curve:
            parts = [f"{curve}: {count}" for curve, count in meta.excluded_by_curve.items() if count > 0]
            if parts:
                st.caption(f"Excluded points: {', '.join(parts)}")

    traj_fig = go.Figure(
        data=[
            go.Scatter(
                x=trajectory["md_ft"],
                y=trajectory["tvd_ft"],
                mode="lines",
                name="Trajectory",
                line={"color": "#2e7d32"},
            )
        ]
    )
    traj_fig.update_layout(height=360, xaxis_title="MD (ft)", yaxis_title="TVD (ft)")
    with tab2:
        st.markdown("#### Trajectory Profile")
        st.plotly_chart(traj_fig, use_container_width=True)

    c4, c5 = st.columns(2)
    if c4.button("Open Correlation Panel"):
        st.session_state["nav_target"] = "Correlation Panel"
        st.rerun()
    if c5.button("Open Steering Console"):
        st.session_state["nav_target"] = "Steering Console"
        st.rerun()
