from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from app.plot.correlation_panel import CURVE_COLORS, build_correlation_figure
from app.services.markers import add_marker, delete_marker, edit_marker, load_markers
from app.services.prejob import list_prejob_models, model_label, save_prejob_model
from app.services.project_data import load_project_and_wells, load_well_frames
from app.ui.charts import render_chart
from app.ui.theme import render_page_header


def _selected_depth_window(logs_by_well: dict[str, pd.DataFrame]) -> tuple[float, float]:
    mins = [float(df["md_ft"].min()) for df in logs_by_well.values() if not df.empty]
    maxs = [float(df["md_ft"].max()) for df in logs_by_well.values() if not df.empty]
    return min(mins), max(maxs)


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


def _jump_to_marker(md_ft: float, minimum: float, maximum: float) -> None:
    st.session_state["corr_alignment"] = "Measured depth (ft)"
    context = st.session_state.get("corr_depth_context")
    if context:
        st.session_state["corr_depth_context"] = (*context[:2], "Measured depth (ft)")
    st.session_state["corr_depth_min"] = max(minimum, md_ft - 150.0)
    st.session_state["corr_depth_max"] = min(maximum, md_ft + 150.0)


def _follow_chart_group(group_key, groups):
    # Keep the editor on a well that is actually visible in the chosen chart group.
    st.session_state["corr_marker_well"] = groups[st.session_state[group_key]][0]


def _marker_editor(root, well, observed, logs_by_well):
    st.caption("Marker edits use measured depth (MD), including when the chart uses TVD.")
    result = st.session_state.pop("corr_marker_result", None)
    if result:
        st.success(result)
    trajectory = observed["trajectory"]
    if trajectory.empty:
        st.info("An acquired survey is required to add or edit marker depths.")
        return None
    minimum, maximum = float(trajectory.md_ft.min()), float(trajectory.md_ft.max())
    visible_ids = {marker["marker_id"] for marker in observed["markers"]}
    markers = [marker for marker in load_markers(root, well.well_id) if marker.marker_id in visible_ids]
    selection_key = f"corr_selected_marker_{well.well_id}"
    pending = st.session_state.pop("corr_marker_pending", None)
    tab_revision_key = f"corr_marker_tab_revision_{well.well_id}"
    if pending and pending[0] == well.well_id:
        st.session_state[selection_key] = pending[1]
        st.session_state[tab_revision_key] = st.session_state.get(tab_revision_key, 0) + 1
    edit_tab, add_tab = st.tabs(
        ["Edit marker", "Add marker"],
        key=f"corr_marker_tabs_{well.well_id}_{st.session_state.get(tab_revision_key, 0)}",
    )
    draft = None
    with edit_tab:
        if not markers:
            st.info("No acquired markers for this well. Use Add marker to create a pick.")
        else:
            by_id = {marker.marker_id: marker for marker in markers}
            if st.session_state.get(selection_key) not in by_id:
                st.session_state[selection_key] = markers[0].marker_id
            selected_id = st.selectbox(
                "Select marker", list(by_id), key=selection_key,
                format_func=lambda identifier: f"{by_id[identifier].name} @ {by_id[identifier].md_ft:.2f} ft · {identifier[:8]}",
            )
            selected = by_id[selected_id]
            key = f"corr_edit_{well.well_id}_{selected_id}"
            new_name = st.text_input("Edit name", value=selected.name, key=f"{key}_name")
            default_md = min(maximum, max(minimum, float(selected.md_ft)))
            if default_md != selected.md_ft:
                st.warning("This marker is outside acquired survey support. Choose a supported depth to correct it.")
            new_md = st.number_input(
                "Edit MD (ft)", value=default_md, min_value=minimum, max_value=maximum, key=f"{key}_md",
                help=f"Acquired survey support: {minimum:,.1f}–{maximum:,.1f} ft MD.",
            )
            new_notes = st.text_input("Edit notes", value=selected.notes or "", key=f"{key}_notes")
            valid_depth = np.isfinite(new_md) and minimum <= new_md <= maximum
            changed = (new_name.strip(), float(new_md), new_notes) != (selected.name, selected.md_ft, selected.notes or "")
            if changed:
                st.caption("Unsaved changes · the orange line previews a changed depth. Select Update Marker to save.")
            draft = {"well": well.name, "marker": selected, "md": float(new_md) if valid_depth else selected.md_ft}
            update_col, jump_col = st.columns(2)
            if update_col.button("Update Marker", disabled=not new_name.strip(), type="primary", width="stretch"):
                try:
                    if not valid_depth:
                        raise ValueError("Marker depth must be within the acquired survey support.")
                    edit_marker(root, well.well_id, selected_id, name=new_name.strip(), md_ft=float(new_md), notes=new_notes)
                except (ValueError, OSError) as exc:
                    st.error(f"Could not update marker: {exc}")
                else:
                    # Remount the selector after its formatted label changes,
                    # while retaining this marker's stable identity.
                    st.session_state["corr_marker_pending"] = (well.well_id, selected_id)
                    st.session_state["corr_marker_result"] = "Marker updated and saved."
                    st.rerun()
            jump_col.button(
                "Jump to Marker", on_click=_jump_to_marker, width="stretch", disabled=not valid_depth,
                args=(float(new_md), *_selected_depth_window(logs_by_well)),
                help="Center the MD chart on the edited depth, without saving it.",
            )
            with st.expander("Delete marker"):
                confirm = st.checkbox("Allow deletion of the selected marker", key=f"{key}_delete")
                if st.button("Delete Marker", disabled=not confirm):
                    try:
                        delete_marker(root, well.well_id, selected_id)
                    except (ValueError, OSError) as exc:
                        st.error(f"Could not delete marker: {exc}")
                    else:
                        st.session_state["corr_marker_result"] = "Marker deleted."
                        st.rerun()
    with add_tab:
        with st.form(f"corr_add_marker_{well.well_id}", clear_on_submit=False):
            name = st.text_input("Marker name", value="Top")
            md = st.number_input("Marker MD (ft)", value=minimum, min_value=minimum, max_value=maximum)
            notes = st.text_input("Notes", value="")
            submitted = st.form_submit_button("Add Marker", type="primary")
            if submitted:
                try:
                    if not name.strip():
                        raise ValueError("Enter a marker name before saving.")
                    if not np.isfinite(md) or not minimum <= md <= maximum:
                        raise ValueError("Marker depth must be within the acquired survey support.")
                    created = add_marker(root, well.well_id, name=name.strip(), md_ft=float(md), notes=notes or None)
                except (ValueError, OSError) as exc:
                    st.error(f"Could not add marker: {exc}")
                else:
                    st.session_state["corr_marker_pending"] = (well.well_id, created.marker_id)
                    st.session_state["corr_marker_result"] = "Marker added and saved."
                    st.rerun()
    with st.expander("Marker list"):
        st.dataframe(pd.DataFrame([{"Marker": m.name, "MD (ft)": m.md_ft, "Notes": m.notes or ""} for m in markers]),
                     hide_index=True, width="stretch")
    return draft


def _interpretations(root, selected_offset_ids):
    st.caption(f"Saving uses all {len(selected_offset_ids)} selected offsets, regardless of the visible chart group.")
    st.caption("MD alignment is not a stratigraphic tie. Formation picks constrain the shared-x regional model.")
    if st.button("Save pre-job interpretation from selected offset picks", type="primary"):
        try:
            model = save_prejob_model(root, selected_offset_ids)
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
        else:
            st.session_state["planning_selected_model"] = model.interpretation.version_id
            st.success(f"Saved interpretation {model.interpretation.version_id[:8]} from {len(selected_offset_ids)} selected offsets.")
    models = list_prejob_models(root)
    if models:
        with st.expander("Saved interpretations and evidence", expanded=True):
            for model in models:
                st.write(model_label(model))
                st.caption(f"Model hash {model.model_sha256[:12]} · ±{model.interpretation.uncertainty.band_tvd_ft:g} ft assumed range")
        if st.button("Continue to Planning"):
            st.session_state["nav_target"] = "Planning"
            st.rerun()


def _highlight_marker(figure, draft, view, observed_by_well):
    if not draft or draft["well"] not in view["visible"]:
        return
    column = view["visible"].index(draft["well"]) + 1
    marker = draft["marker"]
    values = [(marker.md_ft, "Selected marker", "#0f766e", "solid")]
    if draft["md"] != marker.md_ft:
        values.append((draft["md"], "Unsaved depth", "#b45309", "dash"))
    shown = False
    for md, label, color, dash in values:
        depth = md
        if view["basis"] == "Local TVD (ft)":
            trajectory = observed_by_well[draft["well"]]["trajectory"]
            depth = float(np.interp(md, trajectory.md_ft, trajectory.tvd_ft))
        if view["minimum"] <= depth <= view["maximum"]:
            figure.add_hline(y=depth, row=1, col=column, line_color=color, line_dash=dash, line_width=2,
                             annotation_text=label, annotation_position="top left")
            shown = True
    if not shown:
        st.caption("Selected marker is outside this depth window. Use Jump to Marker to bring it into view.")


def _view_options(root, selected_wells, well_by_name, logs_by_well, markers_by_well, selected_curves, edit_well_name):
    depth_basis = st.selectbox("Alignment basis", ["Measured depth (ft)", "Local TVD (ft)"], key="corr_alignment")
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
            if trajectory.empty:
                st.info(f"No acquired trajectory available for {name}.")
                return
            converted = observed["logs"].copy()
            converted["md_ft"] = np.interp(converted.md_ft, trajectory.md_ft, trajectory.tvd_ft)
            plot_logs[name] = converted
            plot_markers[name] = [{**marker, "md_ft": float(np.interp(marker["md_ft"], trajectory.md_ft, trajectory.tvd_ft))} for marker in observed["markers"]]

    md_min_all, md_max_all = _selected_depth_window(plot_logs)
    context = (str(root.resolve()), tuple(selected_wells), depth_basis)
    if (
        st.session_state.get("corr_depth_context") != context
        or "corr_depth_min" not in st.session_state
        or "corr_depth_max" not in st.session_state
    ):
        st.session_state["corr_depth_min"] = md_min_all
        st.session_state["corr_depth_max"] = md_max_all
        st.session_state["corr_depth_context"] = context
    c1, c2, c3 = st.columns([2, 2, 1])
    if c3.button("Full depth", key="corr_full_depth"):
        st.session_state["corr_depth_min"] = md_min_all
        st.session_state["corr_depth_max"] = md_max_all
    depth_min = c1.number_input("Depth min (ft)", key="corr_depth_min")
    depth_max = c2.number_input("Depth max (ft)", key="corr_depth_max")
    st.caption(f"Available {depth_basis}: {md_min_all:,.1f} to {md_max_all:,.1f} ft. Depth increases downward.")
    if depth_min > depth_max:
        st.warning("Depth minimum must be smaller than depth maximum.")
        return
    if not any(logs.md_ft.between(depth_min, depth_max).any() for logs in plot_logs.values()):
        st.info("No acquired samples in this depth range. Use Full depth or adjust the limits.")
        return

    x_ranges: dict[str, tuple[float, float]] = {}
    with st.expander("Curve scaling", expanded=False):
        normalize_curves = st.checkbox("Normalize curves to 0-1", value=len(selected_curves) > 1)
        st.caption("Normalization compares curve shapes on a shared scale. Turn it off to inspect original values; GR and RES have different units.")
        range_mode = st.selectbox("Curve ranges", ["Automatic", "Manual"])
        exclude_outliers = st.checkbox("Hide values outside manual ranges (display only)", value=False)
        if normalize_curves and range_mode == "Automatic":
            for curve in selected_curves:
                stats = _range_stats(_series_for_curve(plot_logs, curve, depth_min, depth_max))
                if stats is not None:
                    low, high = stats[:2]
                    x_ranges[curve] = (low, high) if low < high else (low - 0.5, high + 0.5)
            st.caption("Each curve uses the same acquired-data range across all selected wells.")
        if range_mode == "Manual":
            for curve in selected_curves:
                series = _series_for_curve(plot_logs, curve, depth_min, depth_max)
                stats = _range_stats(series)
                if stats is None:
                    st.caption(f"{curve}: no numeric data in this depth window.")
                    continue
                vmin, vmax, low, high = stats
                if vmax <= vmin:
                    st.caption(f"{curve}: all acquired values are {vmin:g}.")
                    continue
                # Inputs use original units, including resistivity; no log10 mental conversion.
                range_key = f"corr_{tuple(selected_wells)}_{curve}_{depth_basis}_{depth_min}_{depth_max}"
                low_col, high_col = st.columns(2)
                low = low_col.number_input(f"{curve} minimum", value=low, key=f"{range_key}_min")
                high = high_col.number_input(f"{curve} maximum", value=high, key=f"{range_key}_max")
                if low >= high:
                    st.warning(f"{curve} minimum must be smaller than maximum.")
                    return
                x_ranges[curve] = (low, high)
            if not normalize_curves:
                st.caption("Manual ranges hide each curve's out-of-range samples on the shared axis.")

    wells_per_chart = st.selectbox(
        "Wells per chart", [1, 2, 3], index=0, key="corr_wells_per_chart",
        help="One track keeps marker edits readable. Choose two or three to compare selected wells.",
    )
    groups = [selected_wells[start:start + wells_per_chart]
              for start in range(0, len(selected_wells), wells_per_chart)]
    group_key = f"corr_visible_group_{tuple(selected_wells)}_{wells_per_chart}"
    focus = (tuple(selected_wells), wells_per_chart, edit_well_name)
    if st.session_state.get("corr_chart_focus") != focus or group_key not in st.session_state:
        st.session_state[group_key] = next(i for i, names in enumerate(groups) if edit_well_name in names)
        st.session_state["corr_chart_focus"] = focus
    group = st.session_state[group_key]
    if len(groups) > 1:
        group = st.selectbox(
            "Visible well group", range(len(groups)), key=group_key,
            format_func=lambda index: f"{index + 1} / {len(groups)}: " + ", ".join(groups[index]),
            on_change=_follow_chart_group, args=(group_key, groups),
        )
    return {
        "logs": plot_logs, "markers": plot_markers, "basis": depth_basis,
        "minimum": depth_min, "maximum": depth_max, "ranges": x_ranges,
        "normalize": normalize_curves, "exclude": exclude_outliers, "visible": groups[group],
    }


def render(project_root: str | None) -> None:
    render_page_header("Correlation Panel", "Compare well logs and edit formation markers in one workspace.")
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
    well_names = [well.name for well in wells]
    defaults = [well.name for well in wells if well.well_id != project.active_well_id][:3] or well_names[:3]
    selection_col, curves_col = st.columns([2, 1])
    selected_wells = selection_col.multiselect("Wells", well_names, default=defaults)
    selected_curves = curves_col.multiselect("Curves", ["GR", "RES"], default=["GR", "RES"])
    if not selected_wells or not selected_curves:
        st.warning("Select at least one well and one curve.")
        return
    well_by_name = {well.name: well for well in wells}
    observed_by_well = {name: load_well_frames(root, well_by_name[name].well_id) for name in selected_wells}
    logs_by_well = {name: frames["logs"] for name, frames in observed_by_well.items()}
    markers_by_well = {name: frames["markers"] for name, frames in observed_by_well.items()}
    empty = [name for name, logs in logs_by_well.items() if logs.empty]
    if empty:
        st.info("No acquired logs for: " + ", ".join(empty) + ". Remove these wells or advance their run.")
        return
    offsets = [well_by_name[name].well_id for name in selected_wells if well_by_name[name].well_id != project.active_well_id]
    workspace, interpretations = st.tabs(["Correlate & edit", "Interpretations"])
    with workspace, st.container(key="corr_workspace"):
        chart_col, editor_col = st.columns([1.6, 1], gap="medium")
        with editor_col, st.container(border=True, key="corr_editor"):
            if st.session_state.get("corr_marker_well") not in selected_wells:
                st.session_state["corr_marker_well"] = selected_wells[0]
            edit_well = st.selectbox("Marker well", selected_wells, key="corr_marker_well")
            draft = _marker_editor(root, well_by_name[edit_well], observed_by_well[edit_well], logs_by_well)
        with chart_col, st.container(key="corr_charts"):
            with st.popover("View options"):
                view = _view_options(root, selected_wells, well_by_name, logs_by_well, markers_by_well, selected_curves, edit_well)
            if view is not None:
                visible = view["visible"]
                # Draw the selected pick once with a stronger overlay, without changing saved data.
                chart_markers = {
                    name: [marker for marker in view["markers"][name]
                           if not (draft and name == draft["well"] and marker["marker_id"] == draft["marker"].marker_id)]
                    for name in visible
                }
                figure = build_correlation_figure(
                    {name: view["logs"][name] for name in visible}, chart_markers, curves=selected_curves,
                    depth_min=view["minimum"], depth_max=view["maximum"], x_ranges=view["ranges"] or None,
                    exclude_outliers=view["exclude"], normalize_curves=view["normalize"], curve_colors=CURVE_COLORS,
                )
                figure.update_yaxes(title_text=view["basis"], row=1, col=1)
                figure.update_layout(
                    height=380, margin={"l": 45, "r": 15, "t": 80, "b": 45},
                    legend={"orientation": "h", "y": 1.12, "yanchor": "bottom", "x": 0,
                            "title": {"text": None}, "font": {"size": 11}},
                )
                _highlight_marker(figure, draft, view, observed_by_well)
                context = (str(root.resolve()), visible, selected_curves, view["basis"], view["minimum"],
                           view["maximum"], view["ranges"], view["exclude"], view["normalize"])
                revision = sha256(repr(context).encode()).hexdigest()
                render_chart(figure, key="corr_chart", compact=True, view_revision=revision)
                st.caption(f"Viewing {', '.join(visible)} · {view['basis']}. All {len(offsets)} selected offsets remain interpretation evidence.")
    with interpretations:
        _interpretations(root, offsets)
