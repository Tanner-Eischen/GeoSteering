from __future__ import annotations

from pathlib import Path

import numpy as np
import streamlit as st

from app.alg.interpretation_model import add_or_update_control_point, evaluate_piecewise_linear
from app.alg.kpi import compute_kpis
from app.model.schemas import ControlPoint
from app.plot.steering import (
    build_active_window_figure,
    build_interpretation_overlay_figure,
    build_kpi_trend_figure,
    build_offset_comparison_figure,
)
from app.services.decisions import create_decision, load_decisions
from app.services.interpretations import (
    create_baseline_interpretation,
    create_interpretation_version,
    get_latest_interpretation,
)
from app.services.project_data import load_project_and_wells, load_well_frames
from app.sim.engine import initial_state, step_forward
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import (
    load_simulation_config,
    load_simulation_state,
    save_simulation_config,
    save_simulation_state,
)


def render(project_root: str | None) -> None:
    st.subheader("Steering Console")
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    project, wells = load_project_and_wells(root)
    if not wells:
        st.info("Import wells before starting simulation.")
        return

    well_by_name = {w.name: w for w in wells}
    name_by_id = {w.well_id: w.name for w in wells}
    active_default = next((w.name for w in wells if w.well_id == project.active_well_id), wells[0].name)

    st.markdown("### Simulation Configuration")
    c1, c2, c3, c4 = st.columns(4)
    active_well_name = c1.selectbox("Active well", options=list(well_by_name.keys()), index=list(well_by_name.keys()).index(active_default))
    offset_candidates = [name for name in well_by_name.keys() if name != active_well_name]
    offset_wells = c2.multiselect("Offset wells", options=offset_candidates, default=offset_candidates[:3])
    step_size_ft = c3.number_input("Step size (ft)", value=100.0, min_value=10.0)
    window_size_ft = c4.number_input("Window size (ft)", value=500.0, min_value=100.0)
    curves_used = st.multiselect("Guiding curves", options=["GR", "RES"], default=["GR", "RES"])

    if st.button("Initialize Simulation"):
        active_frames = load_well_frames(root, well_by_name[active_well_name].well_id)
        logs = active_frames["logs"]
        config = SimulationConfig(
            active_well_id=well_by_name[active_well_name].well_id,
            offset_well_ids=[well_by_name[name].well_id for name in offset_wells],
            curves_used=curves_used or ["GR", "RES"],
            step_size_ft=float(step_size_ft),
            window_size_ft=float(window_size_ft),
            start_md_ft=float(logs["md_ft"].min()),
            end_md_ft=float(logs["md_ft"].max()),
        )
        save_simulation_config(root, config)
        state = initial_state(config)
        save_simulation_state(root, state)

        trajectory = active_frames["trajectory"]
        md_min = float(trajectory["md_ft"].min())
        md_max = float(trajectory["md_ft"].max())
        center = np.interp([md_min, md_max], trajectory["md_ft"], trajectory["tvd_ft"])
        top = [ControlPoint(md_ft=md_min, tvd_ft=float(center[0] - 10.0)), ControlPoint(md_ft=md_max, tvd_ft=float(center[1] - 10.0))]
        base = [ControlPoint(md_ft=md_min, tvd_ft=float(center[0] + 10.0)), ControlPoint(md_ft=md_max, tvd_ft=float(center[1] + 10.0))]
        create_baseline_interpretation(root, top_control_points=top, base_control_points=base)
        st.success("Simulation initialized.")
        st.rerun()

    try:
        config = load_simulation_config(root)
        state = load_simulation_state(root)
    except Exception:
        st.info("Initialize simulation to begin steering.")
        return

    active_frames = load_well_frames(root, config.active_well_id)
    active_logs = active_frames["logs"]
    trajectory = active_frames["trajectory"]
    offset_logs = {
        name_by_id[wid]: load_well_frames(root, wid)["logs"]
        for wid in config.offset_well_ids
        if wid in name_by_id
    }

    st.markdown(f"Current step: **{state.step_index}** | Revealed MD: **{state.revealed_md_ft:.1f} ft**")
    if st.button("Step Forward", disabled=state.complete):
        next_state = step_forward(state, config)
        save_simulation_state(root, next_state)
        st.rerun()

    st.plotly_chart(
        build_active_window_figure(
            logs_df=active_logs,
            revealed_md_ft=state.revealed_md_ft,
            window_size_ft=config.window_size_ft,
            curves=config.curves_used,
        ),
        use_container_width=True,
    )
    st.plotly_chart(
        build_offset_comparison_figure(
            offset_logs=offset_logs,
            revealed_md_ft=state.revealed_md_ft,
            window_size_ft=config.window_size_ft,
            curve="GR",
        ),
        use_container_width=True,
    )

    latest = get_latest_interpretation(root)
    if latest is None:
        st.warning("No interpretation available.")
        return

    st.markdown("### Interpretation Update")
    c5, c6, c7 = st.columns(3)
    cp_md = c5.number_input("Control point md_ft", value=float(state.revealed_md_ft))
    cp_top = c6.number_input("Top tvd_ft", value=float(np.interp(cp_md, trajectory["md_ft"], trajectory["tvd_ft"]) - 10.0))
    cp_base = c7.number_input("Base tvd_ft", value=float(np.interp(cp_md, trajectory["md_ft"], trajectory["tvd_ft"]) + 10.0))
    rationale = st.text_input("Rationale (required)")

    if st.button("Create Interpretation Version"):
        top_points = add_or_update_control_point(latest.top_control_points, md_ft=float(cp_md), tvd_ft=float(cp_top))
        base_points = add_or_update_control_point(latest.base_control_points, md_ft=float(cp_md), tvd_ft=float(cp_base))
        version = create_interpretation_version(
            root,
            step_index=state.step_index,
            rationale=rationale,
            top_control_points=top_points,
            base_control_points=base_points,
        )
        while len(state.version_id_by_step) <= state.step_index:
            state.version_id_by_step.append(None)
        state.version_id_by_step[state.step_index] = version.version_id
        save_simulation_state(root, state)
        st.success(f"Created interpretation version {version.version_id}")
        st.rerun()

    st.markdown("### Decision Entry")
    observations = st.text_area("Observations")
    action = st.selectbox("Recommendation", options=["HOLD", "BUILD", "DROP"])
    target_inc = st.number_input("Target inc (optional)", value=0.0)
    target_azi = st.number_input("Target azi (optional)", value=0.0)
    risk_note = st.text_input("Risk note")

    if st.button("Log Decision"):
        decision = create_decision(
            root,
            step_index=state.step_index,
            md_from_ft=max(config.start_md_ft, state.revealed_md_ft - config.step_size_ft),
            md_to_ft=state.revealed_md_ft,
            interpretation_version_id=get_latest_interpretation(root).version_id,
            observations=observations or "No observations provided.",
            action=action,
            target_inc_deg=target_inc if target_inc != 0.0 else None,
            target_azi_deg=target_azi if target_azi != 0.0 else None,
            risk_note=risk_note or None,
        )
        while len(state.decision_id_by_step) <= state.step_index:
            state.decision_id_by_step.append(None)
        state.decision_id_by_step[state.step_index] = decision.decision_id
        save_simulation_state(root, state)
        st.success(f"Decision logged: {decision.decision_id}")
        st.rerun()

    latest = get_latest_interpretation(root)
    md_from = config.start_md_ft
    md_to = max(config.start_md_ft + 1.0, state.revealed_md_ft)
    kpi = compute_kpis(
        trajectory_df=trajectory,
        top_control_points=latest.top_control_points,
        base_control_points=latest.base_control_points,
        md_from_ft=md_from,
        md_to_ft=md_to,
        step_ft=1.0,
    )

    st.markdown("### KPI Panel")
    k1, k2, k3 = st.columns(3)
    k1.metric("% In Zone", f"{kpi.percent_in_zone:.2f}")
    k2.metric("Avg Center Distance (ft)", f"{kpi.avg_center_distance:.2f}")
    k3.metric("Last-step In Zone", f"{kpi.last_step_in_zone:.2f}")

    md_grid = np.linspace(md_from, md_to, 300)
    top_tvd = evaluate_piecewise_linear(latest.top_control_points, md_grid, hold_constant=True)
    base_tvd = evaluate_piecewise_linear(latest.base_control_points, md_grid, hold_constant=True)
    st.plotly_chart(
        build_interpretation_overlay_figure(trajectory_df=trajectory, md_grid=md_grid, top_tvd=top_tvd, base_tvd=base_tvd),
        use_container_width=True,
    )

    decisions = load_decisions(root)
    if decisions:
        st.plotly_chart(
            build_kpi_trend_figure(
                step_index=[d.step_index for d in decisions],
                percent_in_zone=[kpi.percent_in_zone for _ in decisions],
            ),
            use_container_width=True,
        )
