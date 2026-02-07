from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.plot.correlation_panel import build_correlation_figure
from app.services.markers import add_marker, delete_marker, edit_marker, load_markers
from app.services.project_data import load_project_and_wells, load_well_frames


def _selected_depth_window(logs_by_well: dict[str, pd.DataFrame]) -> tuple[float, float]:
    mins = [float(df["md_ft"].min()) for df in logs_by_well.values()]
    maxs = [float(df["md_ft"].max()) for df in logs_by_well.values()]
    return min(mins), max(maxs)


def render(project_root: str | None) -> None:
    st.subheader("Correlation Panel")
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    project, wells = load_project_and_wells(root)
    if len(wells) < 1:
        st.info("No wells imported yet.")
        return

    well_names = [w.name for w in wells]
    default_wells = [w.name for w in wells if w.well_id != project.active_well_id][:3] or well_names[:3]
    selected_wells = st.multiselect("Wells", options=well_names, default=default_wells)
    if not selected_wells:
        st.warning("Select at least one well.")
        return

    selected_curves = st.multiselect("Curves", options=["GR", "RES"], default=["GR", "RES"])
    if not selected_curves:
        st.warning("Select at least one curve.")
        return

    well_by_name = {w.name: w for w in wells}
    logs_by_well: dict[str, pd.DataFrame] = {}
    markers_by_well: dict[str, list[dict]] = {}
    for name in selected_wells:
        frames = load_well_frames(root, well_by_name[name].well_id)
        logs_by_well[name] = frames["logs"]
        markers_by_well[name] = [m.model_dump(mode="json") for m in load_markers(root, well_by_name[name].well_id)]

    md_min_all, md_max_all = _selected_depth_window(logs_by_well)
    if "corr_depth_min" not in st.session_state:
        st.session_state["corr_depth_min"] = md_min_all
    if "corr_depth_max" not in st.session_state:
        st.session_state["corr_depth_max"] = md_max_all
    c1, c2 = st.columns(2)
    depth_min = c1.number_input("Depth min (ft)", value=float(st.session_state["corr_depth_min"]), key="corr_depth_min")
    depth_max = c2.number_input("Depth max (ft)", value=float(st.session_state["corr_depth_max"]), key="corr_depth_max")

    fig = build_correlation_figure(
        logs_by_well=logs_by_well,
        markers_by_well=markers_by_well,
        curves=selected_curves,
        depth_min=depth_min,
        depth_max=depth_max,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Marker CRUD")
    edit_well_name = st.selectbox("Marker well", options=selected_wells)
    edit_well_id = well_by_name[edit_well_name].well_id
    marker_models = load_markers(root, edit_well_id)

    with st.form("add_marker_form", clear_on_submit=True):
        name = st.text_input("Marker name", value="Top")
        md_ft = st.number_input("Marker depth md_ft", value=float(depth_min))
        notes = st.text_input("Notes", value="")
        submitted = st.form_submit_button("Add Marker")
        if submitted:
            add_marker(root, edit_well_id, name=name, md_ft=float(md_ft), notes=notes or None)
            st.success("Marker added and saved.")
            st.rerun()

    marker_rows = [m.model_dump(mode="json") for m in marker_models]
    st.dataframe(pd.DataFrame(marker_rows), use_container_width=True)

    if marker_models:
        marker_name_map = {f"{m.name} @ {m.md_ft:.2f}": m for m in marker_models}
        selected_marker_label = st.selectbox("Select marker", options=list(marker_name_map.keys()))
        selected_marker = marker_name_map[selected_marker_label]

        c3, c4, c5 = st.columns(3)
        new_name = c3.text_input("Edit name", value=selected_marker.name, key="edit_marker_name")
        new_md = c4.number_input("Edit md_ft", value=float(selected_marker.md_ft), key="edit_marker_md")
        new_notes = c5.text_input("Edit notes", value=selected_marker.notes or "", key="edit_marker_notes")

        c6, c7, c8 = st.columns(3)
        if c6.button("Update Marker"):
            edit_marker(
                root,
                edit_well_id,
                selected_marker.marker_id,
                name=new_name,
                md_ft=float(new_md),
                notes=new_notes or None,
            )
            st.success("Marker updated and saved.")
            st.rerun()

        if c7.button("Delete Marker"):
            delete_marker(root, edit_well_id, selected_marker.marker_id)
            st.success("Marker deleted.")
            st.rerun()

        if c8.button("Jump to Marker"):
            jump_min = float(selected_marker.md_ft) - 150.0
            jump_max = float(selected_marker.md_ft) + 150.0
            st.session_state["corr_depth_min"] = jump_min
            st.session_state["corr_depth_max"] = jump_max
            st.rerun()
