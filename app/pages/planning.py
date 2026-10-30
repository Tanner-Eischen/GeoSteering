from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from app.model.schemas import DLSExceedance, PlanParameters
from app.plan.plan_export import export_plan_csv
from app.plan.plan_generator import generate_plan, plan_to_target
from app.plan.plan_store import save_plan
from app.plot.dls_plot import build_dls_figure
from app.plot.plan_profile import build_plan_profile_figure
from app.services.baseline import estimate_offset_baseline
from app.services.project_data import load_project_and_wells
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

    st.markdown("#### Plan Parameters")
    st.caption("Landing is solved against offset-derived geology when selected. Prescribed geometry is checked for DLS violations before saving.")
    with st.form("planning_params_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        kickoff_md_ft = c1.number_input("kickoff_md_ft", value=500.0, min_value=0.0)
        landing_md_ft = c2.number_input("landing_md_ft (prescribed mode)", value=2000.0, min_value=1.0)
        lateral_length_ft = c3.number_input("lateral_length_ft", value=5000.0)

        c4, c5, c6 = st.columns(3)
        planned_azi_deg = c4.number_input("planned_azi_deg", value=90.0)
        step_ft = c5.number_input("step_ft", value=100.0, min_value=10.0)
        max_dls = c6.number_input("Landing DLS limit (deg/100 ft)", value=6.0, min_value=0.1)
        solve_target = st.checkbox("Solve landing from offset formation picks", value=True)
        plan_name = st.text_input("Plan name", value="Plan A")
        preview_clicked = st.form_submit_button("Generate Preview")

    if preview_clicked:
        try:
            if solve_target:
                project, wells = load_project_and_wells(root)
                offset_ids = [w.well_id for w in wells if w.well_id != project.active_well_id]
                top, base, _ = estimate_offset_baseline(root, offset_ids)
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
        st.success(f"Generated {len(result.stations)} stations.")

    stations = st.session_state.get("planning_preview_stations")
    exceed = st.session_state.get("planning_preview_exceed", [])
    if isinstance(stations, pd.DataFrame) and not stations.empty:
        st.markdown("#### Preview")
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
            plan = save_plan(
                project_root=root,
                name=st.session_state.get("planning_preview_name", "Plan A"),
                parameters=params,
                stations=stations,
                dls_max_deg_per_100ft=float(st.session_state["planning_preview_max_dls"]),
                exceedances=exceedances,
            )
            st.success(f"Saved plan {plan.plan_id}")

        if c11.button("Export Plan CSV"):
            plan_label = st.session_state.get("planning_preview_name", "Plan_A")
            out_path = root / "exports" / f"plan_{plan_label.replace(' ', '_')}_{uuid4().hex[:8]}.csv"
            export_plan_csv(stations, out_path)
            st.success(f"Exported {out_path}")
        if c12.button("Open Report Export"):
            st.session_state["nav_target"] = "Report Export"
            st.rerun()
