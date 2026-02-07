from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from app.plot.log_tracks import build_log_tracks_figure
from app.services.project_data import load_project_and_wells, load_simulation_revealed_md, load_well_frames


def _default_well_id(project, wells) -> str | None:
    if project.active_well_id:
        return project.active_well_id
    if wells:
        return wells[0].well_id
    return None


def render(project_root: str | None) -> None:
    st.subheader("Well Viewer")
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
    available_curves = [c for c in logs.columns if c != "md_ft"]
    default_curves = [c for c in ["GR", "RES"] if c in available_curves]
    selected_curves = st.multiselect("Curves", options=available_curves, default=default_curves)

    depth_mode = st.selectbox("Depth Range", options=["Full", "Last 1000 ft", "Custom"])
    depth_min = None
    depth_max = None
    if depth_mode == "Last 1000 ft":
        depth_max = float(logs["md_ft"].max())
        depth_min = max(float(logs["md_ft"].min()), depth_max - 1000.0)
    elif depth_mode == "Custom":
        c1, c2 = st.columns(2)
        depth_min = c1.number_input("Depth Min (ft)", value=float(logs["md_ft"].min()))
        depth_max = c2.number_input("Depth Max (ft)", value=float(logs["md_ft"].max()))

    bit_md = load_simulation_revealed_md(root)
    fig, meta = build_log_tracks_figure(
        logs_df=logs,
        markers=markers,
        curves=selected_curves,
        depth_min=depth_min,
        depth_max=depth_max,
        bit_md_ft=bit_md,
    )
    st.plotly_chart(fig, use_container_width=True)
    if "RES" in selected_curves:
        st.caption(f"RES clipped (<=0): {meta.clipped_res_count}")

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
    st.plotly_chart(traj_fig, use_container_width=True)

