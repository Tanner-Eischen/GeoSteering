from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from app.model.schemas import DLSExceedance, PlanParameters, PrejobModel
from app.plan.plan_export import PLAN_EXPORT_COLUMNS
from app.plan.plan_generator import generate_plan, plan_to_target
from app.plan.plan_store import save_plan
from app.plot.dls_plot import build_dls_figure
from app.plot.plan_profile import build_plan_profile_figure
from app.services.prejob import list_prejob_models, model_label, validate_prejob_model
from app.ui.charts import render_chart
from app.ui.theme import render_page_header


def _planning_inputs(selected_id, selected_model, has_models):
    st.markdown("#### Landing geometry")
    solve_target = st.checkbox("Solve landing from offset formation picks", value=has_models,
                               key="planning_input_solve")
    if solve_target:
        st.caption("Landing depth is solved from the selected geology, along eastward azimuth 90°.")
        st.session_state["planning_input_azimuth"] = 90.0
    kickoff = st.number_input("Kickoff MD (ft)", value=500.0, min_value=0.0, key="planning_input_kickoff")
    lateral_length = st.number_input("Lateral length (ft)", value=5000.0, min_value=1.0, key="planning_input_length")
    max_dls = st.number_input("Landing DLS limit (deg/100 ft)", value=6.0, min_value=0.1, key="planning_input_dls")
    plan_name = st.text_input("Plan name", value="Plan A", key="planning_input_name").strip()
    with st.expander("Landing & sampling options", expanded=not solve_target):
        landing = st.number_input("Landing MD · prescribed mode (ft)", value=2000.0, min_value=1.0,
                                  disabled=solve_target, key="planning_input_landing")
        azimuth = st.number_input("Azimuth (degrees)", value=90.0, min_value=0.0, max_value=359.9,
                                  disabled=solve_target, key="planning_input_azimuth")
        spacing = st.number_input("Station spacing (ft)", value=100.0, min_value=10.0, key="planning_input_spacing")
    st.caption("Preview updates automatically when you press Enter or leave an edited field. Save Plan remains explicit.")
    # Reactive controls reach Python before Save; unsubmitted form edits would not.
    request = {
        "model": selected_id,
        "model_sha256": selected_model.model_sha256 if selected_model else None,
        "solve_target": solve_target,
        "kickoff_md_ft": kickoff,
        "landing_md_ft": None if solve_target else landing,
        "lateral_length_ft": lateral_length,
        "planned_azi_deg": 90.0 if solve_target else azimuth,
        "step_ft": spacing,
        "max_dls": max_dls,
        "name": plan_name,
    }
    return request


def _clear_preview():
    st.session_state.pop("planning_preview_stations", None)
    st.session_state.pop("planning_preview_saved_id", None)


def _generate_preview(root, request, selected_model):
    # A failed regeneration must not leave an old preview eligible for saving.
    _clear_preview()
    try:
        if not request["name"]:
            raise ValueError("Enter a plan name to update the preview.")
        required = {
            "kickoff_md_ft": "Kickoff MD", "lateral_length_ft": "Lateral length",
            "max_dls": "Landing DLS limit", "step_ft": "Station spacing",
        }
        if not request["solve_target"]:
            required.update(landing_md_ft="Landing MD", planned_azi_deg="Azimuth")
        for key, label in required.items():
            try:
                valid = request[key] is not None and math.isfinite(float(request[key]))
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                raise ValueError(f"Enter a finite value for {label} to update the preview.")
        if request["solve_target"]:
            if selected_model is None:
                raise ValueError("Select a saved geological interpretation before solving the landing")
            validate_prejob_model(root, selected_model)
            params, result = plan_to_target(
                selected_model.interpretation.top_control_points, selected_model.interpretation.base_control_points,
                kickoff_md_ft=float(request["kickoff_md_ft"]), lateral_length_ft=float(request["lateral_length_ft"]),
                dls_max_deg_per_100ft=float(request["max_dls"]), step_ft=float(request["step_ft"]),
            )
        else:
            params = PlanParameters(
                kickoff_md_ft=float(request["kickoff_md_ft"]), landing_md_ft=float(request["landing_md_ft"]),
                lateral_length_ft=float(request["lateral_length_ft"]), planned_azi_deg=float(request["planned_azi_deg"]),
                step_ft=float(request["step_ft"]),
            )
            result = generate_plan(parameters=params, dls_max_deg_per_100ft=float(request["max_dls"]))
    except ValueError as exc:
        return str(exc)
    captured = {
        "stations": result.stations,
        "exceed": [item.model_dump(mode="json") for item in result.exceedances],
        "params": params.model_dump(mode="json"),
        "max_dls": float(request["max_dls"]),
        "name": request["name"],
        "root": str(root.resolve()),
        "model": selected_model.model_dump(mode="json") if request["solve_target"] and selected_model else None,
        "selection": request["model"],
        "request": request,
    }
    for key, value in captured.items():
        st.session_state[f"planning_preview_{key}"] = value
    return None


def _captured_preview(root):
    if st.session_state.get("planning_preview_root") != str(root.resolve()):
        return None
    stations = st.session_state.get("planning_preview_stations")
    if not isinstance(stations, pd.DataFrame) or stations.empty:
        return None
    return {
        key: st.session_state.get(f"planning_preview_{key}")
        for key in ("stations", "exceed", "params", "max_dls", "name", "model", "request", "saved_id")
    }


def _refresh_preview(root, request, selected_model, model_error):
    """Recompute changed inputs without saving or discarding an unchanged saved draft."""
    preview = _captured_preview(root)
    blocked = model_error if request["solve_target"] else None
    attempt = (str(root.resolve()), request, blocked)
    if blocked:
        _clear_preview()
        st.session_state["planning_preview_attempt"] = attempt
        st.session_state["planning_preview_error"] = blocked
    elif preview is not None and preview["request"] == request:
        # Tab/chart interactions and Save reruns keep the same computation and saved ID.
        st.session_state["planning_preview_attempt"] = attempt
        st.session_state["planning_preview_error"] = None
    elif (st.session_state.get("planning_preview_attempt") != attempt
          or not st.session_state.get("planning_preview_error")):
        st.session_state["planning_preview_error"] = _generate_preview(root, request, selected_model)
        st.session_state["planning_preview_attempt"] = attempt
    error = st.session_state.get("planning_preview_error")
    if error and not blocked:  # Invalid source evidence is already shown beside the selector.
        st.error(error)
    return _captured_preview(root)


def _save_actions(root, preview):
    stations, exceed, saved_id = preview["stations"], preview["exceed"], preview["saved_id"]
    if exceed:
        st.warning("This prescribed plan exceeds its DLS limit. Adjust its geometry before saving.")
    if st.button("Save Plan", type="primary", disabled=bool(exceed) or bool(saved_id), width="stretch"):
        try:
            plan = save_plan(
                project_root=root, name=preview["name"], parameters=PlanParameters.model_validate(preview["params"]),
                stations=stations, dls_max_deg_per_100ft=preview["max_dls"],
                exceedances=[DLSExceedance.model_validate(item) for item in exceed],
                geological_model=PrejobModel.model_validate(preview["model"]) if preview["model"] else None,
            )
        except (ValueError, OSError) as exc:
            st.error(str(exc))
        else:
            st.session_state["planning_saved_plan_id"] = plan.plan_id
            st.session_state["planning_preview_saved_id"] = plan.plan_id
            st.rerun()
    filename = re.sub(r"[^\w.-]+", "_", preview["name"]).strip("._") or "plan"
    st.download_button("Download station CSV" if saved_id else "Download preview CSV",
                        data=stations[PLAN_EXPORT_COLUMNS].to_csv(index=False).encode("utf-8"),
                        file_name=f"{filename}.csv", mime="text/csv", width="stretch")
    if st.button("Continue to Steering", disabled=not bool(saved_id), width="stretch"):
        st.session_state["planning_saved_plan_id"] = saved_id
        st.session_state["nav_target"] = "Steering Console"
        st.rerun()
    if saved_id:
        st.success(f"Saved {preview['name']} · {saved_id[:8]}.")
    else:
        st.caption("Save the reviewed plan to use it in Steering. Downloading a CSV does not save a project plan.")


def _preview_charts(preview):
    if preview is None:
        st.info("Enter valid planning inputs to see the automatic preview.")
        return
    params, stations = preview["params"], preview["stations"]
    st.caption(f"Preview: {preview['name']} · Landing MD {params['landing_md_ft']:,.1f} ft · "
               f"Spacing {params['step_ft']:g} ft · {len(stations)} stations")
    trajectory_tab, dls_tab = st.tabs(["Trajectory", "Dogleg limits"], key="planning_preview_tabs")
    with trajectory_tab:
        profile = build_plan_profile_figure(stations)
        profile.update_yaxes(autorange="reversed")
        profile.update_layout(height=320, margin={"l": 45, "r": 15, "t": 35, "b": 45})
        render_chart(profile, key="planning_profile", compact=True)
    with dls_tab:
        dls = build_dls_figure(stations, max_dls_deg_per_100ft=preview["max_dls"])
        dls.update_layout(height=320, margin={"l": 45, "r": 15, "t": 35, "b": 45})
        render_chart(dls, key="planning_dls", compact=True)
    count = len(preview["exceed"])
    st.caption(f"Preview max DLS {stations['dls_deg_per_100ft'].max():.2f}°/100 ft · "
               f"Captured limit {preview['max_dls']:g}°/100 ft · "
               + (f"{count} exceeding intervals" if count else "All stations within limit"))


def _model_details(model, title):
    st.markdown(f"#### {title}")
    st.write("Offsets: " + ", ".join(model.well_names[well_id] for well_id in model.offset_well_ids))
    st.caption(f"Active well: {model.well_names[model.active_well_id]} · Model {model.interpretation.version_id[:8]} · "
               f"Hash {model.model_sha256[:12]}")
    st.caption(f"±{model.interpretation.uncertainty.band_tvd_ft:g} ft assumed range. "
               "Planning uses these saved boundaries without refitting other offsets.")


def _preview_details(preview, selected_model):
    if preview is not None:
        st.markdown("#### Captured preview data")
        st.caption(f"{preview['name']} · Landing DLS limit {preview['max_dls']:g}°/100 ft")
        if preview["model"]:
            _model_details(PrejobModel.model_validate(preview["model"]), "Geological interpretation captured in preview")
        else:
            st.info("This preview contains prescribed geometry without a geological interpretation.")
        st.dataframe(preview["stations"][PLAN_EXPORT_COLUMNS], width="stretch", hide_index=True)
        if preview["exceed"]:
            st.markdown("#### Intervals exceeding the captured DLS limit")
            st.dataframe(pd.DataFrame(preview["exceed"]), width="stretch", hide_index=True)
    else:
        st.info("Station data and DLS checks appear automatically when the inputs are valid.")
    if selected_model is not None and (preview is None or not preview["model"]
                                      or selected_model.model_sha256 != preview["model"]["model_sha256"]):
        _model_details(selected_model, "Currently selected geological interpretation")
    if st.button("Open Correlation to select evidence"):
        st.session_state["nav_target"] = "Correlation Panel"
        st.rerun()


def render(project_root: str | None) -> None:
    render_page_header("Planning", "Set the landing geometry beside its preview, then save or download the reviewed plan.")
    if not project_root:
        st.info("Open a project first.")
        return
    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return
    models = list_prejob_models(root)
    by_id = {model.interpretation.version_id: model for model in models}
    model_ids = [None, *by_id]
    preferred_id = st.session_state.get("planning_selected_model")
    default_id = preferred_id if preferred_id in by_id else (next(iter(by_id)) if by_id else None)
    selected_id = st.selectbox(
        "Geological interpretation", model_ids, index=model_ids.index(default_id),
        format_func=lambda value: model_label(by_id[value]) if value else "No interpretation selected",
        key=f"planning_model_{root.resolve()}",
    )
    selected_model = by_id.get(selected_id)
    model_error = None
    if selected_model is not None:
        try:
            validate_prejob_model(root, selected_model)
        except ValueError as exc:
            model_error = str(exc)
            st.error(model_error)
    elif not models:
        st.caption("Prescribed geometry is available. Save an offset interpretation in Correlation to solve a geological landing.")
    workspace, details = st.tabs(["Plan & preview", "Details & data"])
    with workspace, st.container(key="planning_workspace"):
        chart_col, controls_col = st.columns([1.5, 1], gap="medium")
        with controls_col, st.container(border=True, key="planning_controls"):
            request = _planning_inputs(selected_id, selected_model, bool(models))
            preview = _refresh_preview(root, request, selected_model, model_error)
            if preview is not None:
                _save_actions(root, preview)
        with chart_col, st.container(key="planning_charts"):
            _preview_charts(preview)
    with details:
        _preview_details(preview, selected_model)
