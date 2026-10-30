from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from app.plot.correlation_panel import CURVE_COLORS, build_correlation_figure
from app.services.baseline import estimate_offset_baseline
from app.services.interpretations import (
    create_baseline_interpretation,
    create_interpretation_version,
    get_latest_interpretation,
)
from app.services.markers import add_marker, delete_marker, edit_marker, load_markers
from app.services.project_data import load_project_and_wells, load_well_frames
from app.ui.theme import render_page_header


def _selected_depth_window(logs_by_well: dict[str, pd.DataFrame]) -> tuple[float, float]:
    mins = [float(df["md_ft"].min()) for df in logs_by_well.values()]
    maxs = [float(df["md_ft"].max()) for df in logs_by_well.values()]
    return min(mins), max(maxs)


def _series_for_range(
    logs_by_well: dict[str, pd.DataFrame],
    curves: list[str],
    depth_min: float | None,
    depth_max: float | None,
) -> np.ndarray:
    arrays = []
    for df in logs_by_well.values():
        df_local = df
        if depth_min is not None:
            df_local = df_local[df_local["md_ft"] >= float(depth_min)]
        if depth_max is not None:
            df_local = df_local[df_local["md_ft"] <= float(depth_max)]
        for curve in curves:
            if curve not in df_local.columns:
                continue
            values = np.asarray(df_local[curve], dtype="float64")
            values = values[np.isfinite(values)]
            if values.size:
                arrays.append(values)
    if not arrays:
        return np.array([], dtype="float64")
    return np.concatenate(arrays)


def _series_for_curve(
    logs_by_well: dict[str, pd.DataFrame],
    curve: str,
    depth_min: float | None,
    depth_max: float | None,
) -> np.ndarray:
    arrays = []
    for df in logs_by_well.values():
        df_local = df
        if depth_min is not None:
            df_local = df_local[df_local["md_ft"] >= float(depth_min)]
        if depth_max is not None:
            df_local = df_local[df_local["md_ft"] <= float(depth_max)]
        if curve not in df_local.columns:
            continue
        values = np.asarray(df_local[curve], dtype="float64")
        values = values[np.isfinite(values)]
        if values.size:
            arrays.append(values)
    if not arrays:
        return np.array([], dtype="float64")
    return np.concatenate(arrays)


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
    return float(span / 1000.0)


def _log_slider_step() -> float:
    return 0.01


def render(project_root: str | None) -> None:
    render_page_header(
        "Correlation Panel",
        "Multiwell signature comparison and marker editing for stratigraphic tie consistency.",
    )
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
        markers_by_well[name] = frames["markers"]

    st.caption("MD alignment is a measurement-depth view, not a stratigraphic tie. Formation picks constrain the shared-x regional model. TVD alignment requires a common vertical datum.")
    selected_offset_ids = [well_by_name[name].well_id for name in selected_wells if well_by_name[name].well_id != project.active_well_id]
    if st.button("Save pre-job interpretation from selected offset picks"):
        try:
            top, base, uncertainty = estimate_offset_baseline(root, selected_offset_ids)
            prejob = root / "prejob"
            if get_latest_interpretation(prejob) is None:
                create_baseline_interpretation(prejob, top, base, uncertainty_band_tvd_ft=uncertainty,
                                              rationale="Regional top/base fitted to selected offset marker intersections only")
            else:
                create_interpretation_version(prejob, 0, "Revised regional fit to selected offset picks", top, base, uncertainty)
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Saved offset-derived regional model. ±{uncertainty:g} ft assumed uncertainty; spatial support is limited to the offset marker locations.")

    md_min_all, md_max_all = _selected_depth_window(logs_by_well)
    if "corr_depth_min" not in st.session_state:
        st.session_state["corr_depth_min"] = md_min_all
    if "corr_depth_max" not in st.session_state:
        st.session_state["corr_depth_max"] = md_max_all
    c1, c2 = st.columns(2)
    depth_min = c1.number_input("Depth min (ft)", value=float(st.session_state["corr_depth_min"]), key="corr_depth_min")
    depth_max = c2.number_input("Depth max (ft)", value=float(st.session_state["corr_depth_max"]), key="corr_depth_max")

    x_range = None
    x_ranges: dict[str, tuple[float, float]] = {}
    exclude_outliers = False
    normalize_curves = False
    with st.expander("Scale & Outliers", expanded=False):
        normalize_curves = st.checkbox("Normalize curves to 0-1", value=False)
        exclude_outliers = st.checkbox("Exclude values outside range (visual only)", value=False)

        if normalize_curves:
            for curve in selected_curves:
                series = _series_for_curve(logs_by_well, curve, depth_min, depth_max)
                log_scale = curve.upper() == "RES"
                stats = _range_stats_log(series) if log_scale else _range_stats(series)
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
                        key=f"corr_range_{curve}",
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
                        key=f"corr_range_{curve}",
                    )
                    x_ranges[curve] = (float(selected[0]), float(selected[1]))
        else:
            range_mode = st.selectbox("X-axis range", options=["Auto", "Manual"], index=0)
            per_curve = st.checkbox("Per-curve ranges", value=len(selected_curves) > 1)
            if range_mode == "Manual" or exclude_outliers:
                if per_curve:
                    for curve in selected_curves:
                        series = _series_for_curve(logs_by_well, curve, depth_min, depth_max)
                        log_scale = curve.upper() == "RES"
                        stats = _range_stats_log(series) if log_scale else _range_stats(series)
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
                                key=f"corr_range_{curve}",
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
                                key=f"corr_range_{curve}",
                            )
                            x_ranges[curve] = (float(selected[0]), float(selected[1]))
                else:
                    combined = _series_for_range(logs_by_well, selected_curves, depth_min, depth_max)
                    stats = _range_stats(combined)
                    if stats is None:
                        st.caption("No numeric data available in current depth window.")
                    else:
                        vmin, vmax, low, high = stats
                        if vmax > vmin:
                            step = _slider_step(vmin, vmax)
                            selected = st.slider(
                                "X-axis range",
                                min_value=float(vmin),
                                max_value=float(vmax),
                                value=(float(low), float(high)),
                                step=step,
                                key="corr_range_all",
                            )
                            x_range = (float(selected[0]), float(selected[1]))

    view_tab, marker_tab = st.tabs(["Correlation View", "Marker Editor"])
    with view_tab:
        st.markdown("#### Multiwell Correlation View")
        depth_basis = st.selectbox("Alignment basis", ["Measured depth (ft)", "Local TVD (ft)"])
        plot_logs, plot_markers = logs_by_well, markers_by_well
        if depth_basis == "Local TVD (ft)":
            references = [well_by_name[name].reference for name in selected_wells]
            if any(reference is None for reference in references) or len({reference.vertical_datum for reference in references if reference}) != 1:
                st.warning("Explicit shared vertical datum is required for TVD alignment.")
                return
            plot_logs, plot_markers = {}, {}
            for name in selected_wells:
                observed = load_well_frames(root, well_by_name[name].well_id)
                trajectory = observed["trajectory"]
                converted = observed["logs"].copy()
                converted["md_ft"] = np.interp(converted.md_ft, trajectory.md_ft, trajectory.tvd_ft)
                plot_logs[name] = converted
                plot_markers[name] = [{**marker, "md_ft": float(np.interp(marker["md_ft"], trajectory.md_ft, trajectory.tvd_ft))} for marker in observed["markers"]]
        fig = build_correlation_figure(
            logs_by_well=plot_logs,
            markers_by_well=plot_markers,
            curves=selected_curves,
            depth_min=depth_min if depth_basis == "Measured depth (ft)" else None,
            depth_max=depth_max if depth_basis == "Measured depth (ft)" else None,
            x_range=x_range,
            x_ranges=x_ranges if x_ranges else None,
            exclude_outliers=exclude_outliers,
            normalize_curves=normalize_curves,
            curve_colors=CURVE_COLORS,
        )
        fig.update_yaxes(title_text=depth_basis)
        st.plotly_chart(fig, use_container_width=True)
        if st.button("Open Planning"):
            st.session_state["nav_target"] = "Planning"
            st.rerun()

    with marker_tab:
        st.markdown("#### Marker CRUD")
        edit_well_name = st.selectbox("Marker well", options=selected_wells)
        edit_well_id = well_by_name[edit_well_name].well_id
        visible_ids = {marker["marker_id"] for marker in load_well_frames(root, edit_well_id)["markers"]}
        marker_models = [marker for marker in load_markers(root, edit_well_id) if marker.marker_id in visible_ids]
        known_max_md = float(logs_by_well[edit_well_name].md_ft.max())

        with st.form("add_marker_form", clear_on_submit=True):
            name = st.text_input("Marker name", value="Top")
            md_ft = st.number_input("Marker depth md_ft", value=float(min(depth_min, known_max_md)), max_value=known_max_md)
            notes = st.text_input("Notes", value="")
            submitted = st.form_submit_button("Add Marker")
            if submitted:
                add_marker(root, edit_well_id, name=name, md_ft=float(md_ft), notes=notes or None)
                st.success("Marker added and saved.")
                st.rerun()

        marker_rows = [m.model_dump(mode="json") for m in marker_models]
        st.dataframe(pd.DataFrame(marker_rows), use_container_width=True, hide_index=True)

        if marker_models:
            marker_name_map = {f"{m.name} @ {m.md_ft:.2f}": m for m in marker_models}
            selected_marker_label = st.selectbox("Select marker", options=list(marker_name_map.keys()))
            selected_marker = marker_name_map[selected_marker_label]

            c3, c4, c5 = st.columns(3)
            new_name = c3.text_input("Edit name", value=selected_marker.name, key="edit_marker_name")
            new_md = c4.number_input("Edit md_ft", value=float(selected_marker.md_ft), max_value=known_max_md, key="edit_marker_md")
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
