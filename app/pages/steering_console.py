from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import read_json
from app.model.schemas import ControlPoint
from app.plot.steering import build_active_window_figure, build_kpi_trend_figure
from app.services.baseline import estimate_offset_baseline
from app.services.interpretations import get_latest_interpretation
from app.services.project_data import load_project_and_wells, load_well_frames
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.services.runs import advance_run, fork_run, initialize_run
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import load_simulation_config, load_simulation_state
from app.ui.theme import render_page_header


def _replace_spatial_point(points: list[ControlPoint], x_ft: float, tvd_ft: float) -> list[ControlPoint]:
    retained = [point for point in points if abs(float(point.x_ft) - x_ft) > 1e-8]
    return sorted([*retained, ControlPoint(md_ft=x_ft, x_ft=x_ft, tvd_ft=tvd_ft)], key=lambda p: p.x_ft)


def render(project_root: str | None) -> None:
    render_page_header(
        "Interpretation and Steering",
        "Replay a fixed record or steer a simplified causal path using progressively acquired observations.",
    )
    st.caption("Replay recommendations do not change the recorded trajectory. Estimated-zone diagnostics and completed truth evaluation are reported separately.")
    if not project_root:
        st.info("Open a project or load the case study from Dashboard.")
        return
    root = Path(project_root)
    project, wells = load_project_and_wells(root)
    if not wells:
        st.info("Import wells before starting a replay.")
        return
    well_by_name = {well.name: well for well in wells}
    active_default = next((well.name for well in wells if well.well_id == project.active_well_id), wells[0].name)
    manifest = read_json(root / "manifest.json", default={})
    with st.expander("New isolated run", expanded=False):
        mode = st.selectbox("Run mode", ["replay", "causal"], format_func=lambda value: "Synthetic well replay" if value == "replay" else "Constrained causal simulation")
        bundled_synthetic = st.checkbox("Use bundled structural_dip_01 synthetic environment when no captured source exists", value=False)
        active_name = st.selectbox("Active well", list(well_by_name), index=list(well_by_name).index(active_default))
        offsets = [name for name in well_by_name if name != active_name]
        offset_names = st.multiselect("Offset evidence", offsets, default=offsets[:3])
        step_size = st.number_input("Reveal interval (ft)", min_value=10.0, value=100.0)
        max_dls = st.number_input("Causal DLS limit (degrees/100 ft)", min_value=0.1, max_value=3.0, value=3.0)
        st.caption("Causal mode changes inclination under the selected DLS limit and 85–95° bounds. It uses a fixed synthetic geological field and step-seeded sensor noise.")
        lateral_start = st.number_input("Lateral start MD (ft)", min_value=0.0, value=float(manifest.get("lateral_start_md_ft", 2000.0)))
        plans = [read_json(path) for path in (root / "plans").glob("*.json")]
        plan_labels = {f"{plan['name']} ({plan['plan_id'][:8]})": plan["plan_id"] for plan in plans}
        selected_plan = st.selectbox("Saved plan", ["No plan", *plan_labels])
        if st.button("Initialize new run"):
            active = well_by_name[active_name]
            try:
                top, base, uncertainty = estimate_offset_baseline(root, [well_by_name[name].well_id for name in offset_names], active_well_id=active.well_id)
                end_md = min(curve.depth_max_ft for curve in active.curve_inventory.values())
                config = SimulationConfig(
                    active_well_id=active.well_id, mode=mode,
                    offset_well_ids=[well_by_name[name].well_id for name in offset_names],
                    start_md_ft=float(lateral_start), end_md_ft=end_md,
                    lateral_start_md_ft=float(lateral_start), step_size_ft=float(step_size),
                    plan_id=plan_labels.get(selected_plan),
                    scenario_version="structural_dip_01-v1" if bundled_synthetic else manifest.get("scenario_version", "unspecified"),
                    seed=int(manifest.get("seed", 123)),
                    max_dls_deg_per_100ft=float(max_dls),
                    use_default_synthetic_scenario=bundled_synthetic,
                )
                try:
                    previous_config = load_simulation_config(root)
                except FileNotFoundError:
                    previous_config = None
                initialize_run(root, config, top, base, uncertainty, hidden_truth_path=previous_config.hidden_truth_path if previous_config else None)
            except (ValueError, FileNotFoundError) as exc:
                st.error(str(exc))
            else:
                st.rerun()
    try:
        config = load_simulation_config(root)
        state = load_simulation_state(root)
    except FileNotFoundError:
        st.info("Initialize a replay with offset formation picks. Old MD-only interpretations require a new spatial run.")
        return
    latest = get_latest_interpretation(root)
    if latest is None or not all(point.x_ft is not None for point in latest.top_control_points):
        st.warning("This legacy run has an MD-based interpretation. Initialize a new spatial replay from offset picks.")
        return
    frames = load_well_frames(root, config.active_well_id)
    trajectory, logs = frames["trajectory"], frames["logs"]
    a, b, c = st.columns(3)
    a.metric("Step", state.step_index)
    b.metric("Revealed MD (ft)", f"{state.revealed_md_ft:.1f}")
    c.metric("Status", "Complete" if state.complete else "Running")
    st.caption(f"{config.mode.title()} run {config.run_id} · Seed {config.seed} · {config.scenario_version}")
    if not state.complete and st.button("Fork current run for a command comparison"):
        fork_run(root)
        st.rerun()
    st.plotly_chart(build_active_window_figure(logs, state.revealed_md_ft, config.window_size_ft, config.curves_used), use_container_width=True)
    st.caption("Offset logs remain available over their full acquired depth. Use Correlation Panel for marker-aligned geological ties; matching MD alone is not a stratigraphic correlation.")
    if not trajectory.empty:
        xcol = "x_ft" if "x_ft" in trajectory else "east_ft"
        x = trajectory[xcol].to_numpy(dtype=float)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=trajectory.tvd_ft, name="Observed trajectory"))
        fig.add_trace(go.Scatter(x=x, y=evaluate_piecewise_linear(latest.top_control_points, x), name="Estimated top"))
        fig.add_trace(go.Scatter(x=x, y=evaluate_piecewise_linear(latest.base_control_points, x), name="Estimated base"))
        fig.update_yaxes(autorange="reversed", title_text="Local TVD, positive down (ft)")
        fig.update_xaxes(title_text="Shared along-track x (ft)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Uncertainty: ±{latest.uncertainty.band_tvd_ft:g} ft scenario-assumed range; not a calibrated confidence interval.")
    if not state.complete:
        current_x = float(trajectory[xcol].iloc[-1])
        with st.form(f"recommend_and_reveal_{state.run_id}_{state.step_index}"):
            st.markdown("#### Evidence and next-interval recommendation")
            observations = st.text_area("Observed evidence (required)")
            action = st.selectbox("Recommendation", ["HOLD", "BUILD", "DROP"])
            use_target = st.checkbox("Set a target inclination for causal BUILD/DROP")
            target_inc = st.number_input("Requested inclination (degrees)", min_value=0.0, max_value=180.0, value=90.0)
            update = st.checkbox("Revise an interpreted boundary using current evidence")
            cp_x = st.number_input("Interpreted control point x (ft)", value=current_x)
            cp_top = st.number_input("Estimated top TVD (ft)", value=float(evaluate_piecewise_linear(latest.top_control_points, [current_x])[0]))
            cp_base = st.number_input("Estimated base TVD (ft)", value=float(evaluate_piecewise_linear(latest.base_control_points, [current_x])[0]))
            rationale = st.text_input("Interpretation rationale")
            submitted = st.form_submit_button("Record evidence and advance next interval")
            if submitted:
                if update and not rationale.strip():
                    st.error("Explain the evidence supporting the interpretation revision.")
                elif update and cp_base <= cp_top:
                    st.error("Base TVD must be below top TVD.")
                else:
                    try:
                        advance_run(
                            root, action, observations, rationale=rationale or None,
                            top_control_points=_replace_spatial_point(latest.top_control_points, cp_x, cp_top) if update else None,
                            base_control_points=_replace_spatial_point(latest.base_control_points, cp_x, cp_base) if update else None,
                            target_inc_deg=float(target_inc) if use_target and config.mode == "causal" else None,
                            run_id=state.run_id,
                            expected_step_index=state.step_index,
                            request_id=f"steering-{state.run_id}-{state.step_index}",
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()
    metrics = load_run_metrics(root)
    if metrics:
        st.markdown("#### Persisted estimated-zone history")
        last = metrics[-1]
        a, b, c = st.columns(3)
        a.metric("Estimated lateral in zone (%)", f"{last['percent_in_zone']:.2f}")
        b.metric("Estimated center distance (ft)", f"{last['avg_center_distance']:.2f}")
        c.metric("Evaluated lateral length (ft)", f"{last.get('evaluated_length_ft', 0):.1f}")
        if last.get("command_response"):
            st.write("Effective causal command", last["command_response"])
        st.plotly_chart(build_kpi_trend_figure([row["step_index"] for row in metrics], [row["percent_in_zone"] for row in metrics]), use_container_width=True)
        with st.expander("Decision-time metric provenance"):
            st.dataframe(pd.DataFrame(metrics), hide_index=True)
    if state.complete:
        st.markdown("#### Completed retrospective evaluation")
        evaluation = read_json(run_root(root) / "evaluation" / "replay.json", default={})
        if st.button("Evaluate completed replay against withheld truth"):
            from app.io.project_store import atomic_write_json
            from app.services.evaluation import evaluate_completed_run
            try:
                evaluation = evaluate_completed_run(root)
                atomic_write_json(run_root(root) / "evaluation" / "replay.json", evaluation)
            except ValueError as exc:
                st.error(str(exc))
        if evaluation:
            st.json(evaluation)
        if st.button("Run constrained causal HOLD and observation-guided comparison"):
            from app.io.project_store import atomic_write_json
            from app.services.evaluation import load_completed_scenario
            from app.sim.causal import compare_strategies
            comparison = compare_strategies(scenario=load_completed_scenario(root), seed=config.seed)
            atomic_write_json(run_root(root) / "evaluation" / "comparison.json", comparison)
        comparison = read_json(run_root(root) / "evaluation" / "comparison.json", default={})
        if comparison:
            st.caption("These are separate causal runs from the same landing state. Their bounded commands change their simulated paths.")
            st.dataframe(pd.DataFrame({name: value["metrics"] for name, value in comparison["runs"].items()}).T)
    if st.button("Open Report Export"):
        st.session_state["nav_target"] = "Report Export"
        st.rerun()
