from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from app.model.schemas import DLSExceedance, PlanParameters, PrejobModel
from app.plan.plan_export import export_plan_csv
from app.plan.plan_generator import generate_plan, plan_to_target
from app.plan.plan_store import save_plan
from app.plot.dls_plot import build_dls_figure
from app.plot.plan_profile import build_plan_profile_figure
from app.services.prejob import list_prejob_models, model_label, validate_prejob_model
from app.ui.theme import render_page_header


def render(project_root: str | None) -> None:
    render_page_header(
        "Planning",
        "Target-line setup with DLS constraints, station outputs, and exportable plan deliverables.",
    )
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    st.markdown("#### 1 · Choose the geological interpretation")
    models = list_prejob_models(root)
    by_id = {model.interpretation.version_id: model for model in models}
    if not models:
        st.info("Save an interpretation from selected offset picks in Correlation first. Prescribed geometry remains available below.")
        if st.button("Open Correlation to select evidence"):
            st.session_state["nav_target"] = "Correlation Panel"
            st.rerun()
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
        with st.container(border=True):
            st.write("**Frozen offset interpretation**")
            st.write("Offsets: " + ", ".join(selected_model.well_names[well_id] for well_id in selected_model.offset_well_ids))
            st.caption(f"Active well: {selected_model.well_names[selected_model.active_well_id]} · Model {selected_model.interpretation.version_id[:8]} · Hash {selected_model.model_sha256[:12]}")
            st.caption(f"±{selected_model.interpretation.uncertainty.band_tvd_ft:g} ft assumed range. Planning uses these saved boundaries without refitting other offsets.")

    st.markdown("#### 2 · Set the landing geometry")
    st.caption("Solved plans carry the selected interpretation into the steering run. Prescribed plans retain explicit geometry.")
    with st.form("planning_params_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        kickoff_md_ft = c1.number_input("Kickoff MD (ft)", value=500.0, min_value=0.0)
        landing_md_ft = c2.number_input("Landing MD · prescribed mode (ft)", value=2000.0, min_value=1.0)
        lateral_length_ft = c3.number_input("Lateral length (ft)", value=5000.0, min_value=1.0)

        c4, c5, c6 = st.columns(3)
        planned_azi_deg = c4.number_input("Azimuth (degrees)", value=90.0, min_value=0.0, max_value=359.9)
        step_ft = c5.number_input("Station spacing (ft)", value=100.0, min_value=10.0)
        max_dls = c6.number_input("Landing DLS limit (deg/100 ft)", value=6.0, min_value=0.1)
        solve_target = st.checkbox("Solve landing from offset formation picks", value=True)
        plan_name = st.text_input("Plan name", value="Plan A")
        preview_clicked = st.form_submit_button("Generate Preview")

    if preview_clicked:
        try:
            if solve_target:
                if selected_model is None:
                    raise ValueError("Select a saved geological interpretation before solving the landing")
                validate_prejob_model(root, selected_model)
                top = selected_model.interpretation.top_control_points
                base = selected_model.interpretation.base_control_points
                if abs(float(planned_azi_deg) - 90.0) > 1e-8:
                    raise ValueError("The shared-x target solver requires eastward azimuth 90 degrees.")
                params, result = plan_to_target(
                    top, base, kickoff_md_ft=float(kickoff_md_ft), lateral_length_ft=float(lateral_length_ft),
                    dls_max_deg_per_100ft=float(max_dls), step_ft=float(step_ft),
                )
            else:
                params = PlanParameters(
                    kickoff_md_ft=float(kickoff_md_ft), landing_md_ft=float(landing_md_ft),
                    lateral_length_ft=float(lateral_length_ft), planned_azi_deg=float(planned_azi_deg), step_ft=float(step_ft),
                )
                result = generate_plan(parameters=params, dls_max_deg_per_100ft=float(max_dls))
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["planning_preview_stations"] = result.stations
        st.session_state["planning_preview_exceed"] = [e.model_dump(mode="json") for e in result.exceedances]
        st.session_state["planning_preview_params"] = params.model_dump(mode="json")
        st.session_state["planning_preview_max_dls"] = float(max_dls)
        st.session_state["planning_preview_name"] = plan_name
        st.session_state["planning_preview_root"] = str(root.resolve())
        st.session_state["planning_preview_model"] = selected_model.model_dump(mode="json") if solve_target and selected_model else None
        st.session_state["planning_preview_selection"] = selected_id
        st.success(f"Generated {len(result.stations)} stations.")

    stations = st.session_state.get("planning_preview_stations") if st.session_state.get("planning_preview_root") == str(root.resolve()) else None
    exceed = st.session_state.get("planning_preview_exceed", [])
    if isinstance(stations, pd.DataFrame) and not stations.empty:
        if st.session_state.get("planning_preview_selection") != selected_id:
            st.info("The selected interpretation changed. Generate a new preview before saving a plan.")
            return
        st.markdown("#### 3 · Review and save")
        c7, c8, c9 = st.columns(3)
        c7.metric("Stations", str(len(stations)))
        c8.metric("Exceedances", str(len(exceed)))
        c9.metric("Max DLS", f"{stations['dls_deg_per_100ft'].max():.2f}")

        st.plotly_chart(build_plan_profile_figure(stations), use_container_width=True)
        st.plotly_chart(build_dls_figure(stations, max_dls_deg_per_100ft=float(st.session_state["planning_preview_max_dls"])), use_container_width=True)
        st.dataframe(pd.DataFrame(exceed), use_container_width=True, hide_index=True)

        c10, c11, c12 = st.columns(3)
        if exceed:
            st.warning("This prescribed plan exceeds its DLS limit. Adjust its geometry before saving.")
        if c10.button("Save Plan", disabled=bool(exceed)):
            params = PlanParameters.model_validate(st.session_state["planning_preview_params"])
            exceedances = [DLSExceedance.model_validate(e) for e in exceed]
            model_payload = st.session_state.get("planning_preview_model")
            try:
                plan = save_plan(
                    project_root=root,
                    name=st.session_state.get("planning_preview_name", "Plan A"),
                    parameters=params,
                    stations=stations,
                    dls_max_deg_per_100ft=float(st.session_state["planning_preview_max_dls"]),
                    exceedances=exceedances,
                    geological_model=PrejobModel.model_validate(model_payload) if model_payload else None,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f"Saved {plan.name} · {plan.plan_id[:8]}. Its geological interpretation is frozen with the plan.")
                st.session_state["planning_saved_plan_id"] = plan.plan_id

        if c11.button("Export Plan CSV"):
            plan_label = st.session_state.get("planning_preview_name", "Plan_A")
            out_path = root / "exports" / f"plan_{plan_label.replace(' ', '_')}_{uuid4().hex[:8]}.csv"
            export_plan_csv(stations, out_path)
            st.success(f"Exported {out_path}")
        if c12.button("Continue to Steering"):
            st.session_state["nav_target"] = "Steering Console"
            st.rerun()
