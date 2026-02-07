from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from app.model.schemas import DLSExceedance, PlanParameters
from app.plan.plan_export import export_plan_csv
from app.plan.plan_generator import generate_plan
from app.plan.plan_store import save_plan
from app.plot.dls_plot import build_dls_figure
from app.plot.plan_profile import build_plan_profile_figure


def render(project_root: str | None) -> None:
    st.subheader("Planning")
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    st.markdown("### Plan Parameters")
    c1, c2, c3 = st.columns(3)
    kickoff_md_ft = c1.number_input("kickoff_md_ft", value=1000.0)
    landing_md_ft = c2.number_input("landing_md_ft", value=3000.0)
    lateral_length_ft = c3.number_input("lateral_length_ft", value=5000.0)

    c4, c5, c6 = st.columns(3)
    planned_azi_deg = c4.number_input("planned_azi_deg", value=90.0)
    step_ft = c5.number_input("step_ft", value=100.0, min_value=10.0)
    max_dls = c6.number_input("max_dls_deg_per_100ft", value=3.0, min_value=0.1)

    plan_name = st.text_input("Plan name", value="Plan A")

    if st.button("Generate Preview"):
        params = PlanParameters(
            kickoff_md_ft=float(kickoff_md_ft),
            landing_md_ft=float(landing_md_ft),
            lateral_length_ft=float(lateral_length_ft),
            planned_azi_deg=float(planned_azi_deg),
            step_ft=float(step_ft),
        )
        result = generate_plan(parameters=params, dls_max_deg_per_100ft=float(max_dls))
        st.session_state["planning_preview_stations"] = result.stations
        st.session_state["planning_preview_exceed"] = [e.model_dump(mode="json") for e in result.exceedances]
        st.session_state["planning_preview_params"] = params.model_dump(mode="json")
        st.session_state["planning_preview_max_dls"] = float(max_dls)
        st.success(f"Generated {len(result.stations)} stations.")

    stations = st.session_state.get("planning_preview_stations")
    exceed = st.session_state.get("planning_preview_exceed", [])
    if isinstance(stations, pd.DataFrame) and not stations.empty:
        st.markdown("### Preview")
        st.plotly_chart(build_plan_profile_figure(stations), use_container_width=True)
        st.plotly_chart(build_dls_figure(stations, max_dls_deg_per_100ft=float(st.session_state["planning_preview_max_dls"])), use_container_width=True)
        st.dataframe(pd.DataFrame(exceed), use_container_width=True)

        c7, c8 = st.columns(2)
        if c7.button("Save Plan"):
            params = PlanParameters.model_validate(st.session_state["planning_preview_params"])
            exceedances = [DLSExceedance.model_validate(e) for e in exceed]
            plan = save_plan(
                project_root=root,
                name=plan_name,
                parameters=params,
                stations=stations,
                dls_max_deg_per_100ft=float(st.session_state["planning_preview_max_dls"]),
                exceedances=exceedances,
            )
            st.success(f"Saved plan {plan.plan_id}")

        if c8.button("Export Plan CSV"):
            out_path = root / "exports" / f"plan_{plan_name.replace(' ', '_')}_{uuid4().hex[:8]}.csv"
            export_plan_csv(stations, out_path)
            st.success(f"Exported {out_path}")
