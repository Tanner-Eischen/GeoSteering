from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import read_json
from app.plot.steering import build_active_window_figure, build_command_preview_figure, build_kpi_trend_figure
from app.services.operator_workflow import load_operator_view, run_label, submit_steering
from app.services.prejob import list_prejob_models, model_label, validate_prejob_model
from app.services.project_data import load_project_and_wells
from app.services.run_paths import active_run_id
from app.services.runs import fork_run, initialize_run
from app.services.steering_preview import PreviewUnavailable, preview_command
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import load_simulation_config
from app.ui.charts import chart_config, render_chart
from app.ui.theme import render_page_header
from app.ui.workspace import remember_selected_run, selected_run_choice
from app.uncertainty.models import CalibrationSettings, EnsembleSettings


def _command_workspace(root, config, state, latest, trajectory):
    """Keep the command, evidence and submit action in one compact panel."""
    st.markdown("#### Next interval")
    prefix = f"command_{root.resolve()}_{state.run_id}_{state.step_index}"
    action = st.radio(
        "Recommendation", ["HOLD", "BUILD", "DROP"], horizontal=True, key=f"{prefix}_action",
        help="Inclination is measured from vertical. Near horizontal, BUILD bends upward; DROP bends downward.",
    )
    target_inc = None
    if config.mode == "causal":
        use_target = st.checkbox("Set a target inclination", disabled=action == "HOLD", key=f"{prefix}_target_enabled")
        requested_input = st.number_input(
            "Requested inclination (degrees)", min_value=0.0, max_value=180.0,
            value=float(trajectory.iloc[-1].get("inc_deg", 90.0)) if not trajectory.empty else 90.0,
            step=0.5, key=f"{prefix}_target", disabled=not use_target or action == "HOLD",
        )
        if use_target and action != "HOLD":
            target_inc = requested_input
    legacy_preview_unavailable = False
    try:
        preview = preview_command(root, run_id=state.run_id, expected_step_index=state.step_index,
                                  action=action, target_inc_deg=target_inc)
    except PreviewUnavailable as exc:
        preview = None
        legacy_preview_unavailable = True
        st.warning(str(exc))
        st.caption("This saved run can advance using its original environment; geometry preview is unavailable.")
    except (ValueError, FileNotFoundError) as exc:
        preview = None
        st.error(str(exc))
    if preview:
        st.caption(f"Next MD {preview['md_from_ft']:,.0f}–{preview['md_to_ft']:,.0f} ft")
        if config.mode == "causal":
            st.write(f"Inclination {preview['current_inc_deg']:.2f}° → {preview['effective_inc_deg']:.2f}°")
            st.caption(f"Projected TVD {preview['station']['tvd_ft']:,.2f} ft · "
                       f"DLS {preview['station']['dls_deg_per_100ft']:.2f}°/100 ft")
            if preview["clipped"]:
                st.warning(f"Limited to the captured {preview['max_dls_deg_per_100ft']:g}°/100 ft DLS and 85–95° inclination bounds.")
        else:
            st.caption("Replay records your recommendation; the recorded path stays fixed.")
    observations = st.text_area(
        "Observed evidence (required)", key=f"{prefix}_evidence", height=90,
        placeholder="What do the acquired logs and interpretation support?",
    )
    update_bounds = None
    rationale = ""
    with st.expander("Revise interpretation", expanded=False):
        update = st.checkbox("Revise an interpreted boundary using current evidence", key=f"{prefix}_revise")
        if update:
            xcol = "x_ft" if "x_ft" in trajectory else "east_ft"
            current_x = float(trajectory[xcol].iloc[-1])
            cp_x = st.number_input("Control point x (ft)", value=current_x, key=f"{prefix}_x")
            cp_top = st.number_input("Estimated top TVD (ft)",
                                     value=float(evaluate_piecewise_linear(latest.top_control_points, [cp_x])[0]), key=f"{prefix}_top")
            cp_base = st.number_input("Estimated base TVD (ft)",
                                      value=float(evaluate_piecewise_linear(latest.base_control_points, [cp_x])[0]), key=f"{prefix}_base")
            rationale = st.text_input("Interpretation rationale", key=f"{prefix}_rationale")
            update_bounds = (cp_x, cp_top, cp_base)
            st.caption("The path preview shows saved boundaries. Your revision is recorded with this step.")
    if st.button("Record & advance", type="primary",
                 disabled=preview is None and not legacy_preview_unavailable,
                 key=f"{prefix}_advance", use_container_width=True):
        try:
            submit_steering(root, action=action, observations=observations, rationale=rationale,
                            interpretation_version_id=latest.version_id, update_bounds=update_bounds,
                            target_inc_deg=target_inc, run_id=state.run_id, expected_step_index=state.step_index)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    return preview


def _path_figure(config, state, latest, trajectory, preview):
    if preview and config.mode == "causal":
        return build_command_preview_figure(trajectory, preview, latest)
    window = trajectory.loc[trajectory.md_ft >= max(config.start_md_ft, state.revealed_md_ft - config.window_size_ft)]
    xcol = "x_ft" if "x_ft" in window else "east_ft"
    x = window[xcol].to_numpy(dtype=float)
    mode = "lines+markers" if len(window) == 1 else "lines"
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=x, y=window.tvd_ft, name="Acquired path", mode=mode))
    figure.add_trace(go.Scatter(x=x, y=evaluate_piecewise_linear(latest.top_control_points, x), name="Estimated top", mode=mode))
    figure.add_trace(go.Scatter(x=x, y=evaluate_piecewise_linear(latest.base_control_points, x), name="Estimated base", mode=mode))
    figure.update_yaxes(autorange="reversed", title_text="TVD (ft), positive down")
    figure.update_xaxes(title_text="Along-section x (ft)")
    return figure


def _steering_workspace(root, view):
    config, state, latest = view["config"], view["state"], view["interpretation"]
    trajectory, logs = view["frames"]["trajectory"], view["frames"]["logs"]
    with st.container(key="steering_workspace"):
        chart_column, command_column = st.columns([1.45, 1], gap="medium")
        # Populate the command first so its live preview appears beside it.
        with command_column, st.container(border=True, key="steering_command"):
            if state.complete:
                preview = None
                st.markdown("#### Run complete")
                st.info("No intervals remain. Open History & results to evaluate or export this run.")
            else:
                preview = _command_workspace(root, config, state, latest, trajectory)
        with chart_column, st.container(key="steering_charts"):
            names = ["Logs", "Path + preview" if config.mode == "causal" else "Interpreted path"]
            if view.get("uncertainty") is not None:
                names.append("Uncertainty")
            tabs = st.tabs(names)
            with tabs[0]:
                figure = build_active_window_figure(logs, state.revealed_md_ft, config.window_size_ft, config.curves_used)
                figure.update_layout(height=320, title=None, margin={"l": 45, "r": 15, "t": 35, "b": 45})
                render_chart(figure, key=f"steering_run_logs_{state.run_id}_{state.step_index}", compact=True)
                st.caption("Acquired logs only. Depth is measured along the well (MD).")
            with tabs[1]:
                if not trajectory.empty:
                    figure = _path_figure(config, state, latest, trajectory, preview)
                    figure.update_layout(height=320, title=None, margin={"l": 45, "r": 15, "t": 130, "b": 45},
                                         legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "font": {"size": 11}})
                    render_chart(figure, key=f"steering_run_path_{state.run_id}_{state.step_index}", compact=True)
                    if preview and config.mode == "causal":
                        st.caption("Dashed segment: next-command geometry. Future measurements and true geology stay hidden.")
                    st.caption(f"±{latest.uncertainty.band_tvd_ft:g} ft assumed boundary range; not calibrated confidence.")
            if len(tabs) == 3:
                from app.pages.uncertainty import render_snapshot
                with tabs[2]:
                    render_snapshot(view["uncertainty"], trajectory, compact=True)
                    if st.button("Inspect ensemble and command probabilities"):
                        st.session_state["nav_target"] = "Uncertainty"
                        st.rerun()


def _new_run_controls(root, project, wells, run_selection_key):
    well_by_name = {well.name: well for well in wells}
    active_default = next((well.name for well in wells if well.well_id == project.active_well_id), wells[0].name)
    manifest = read_json(root / "manifest.json", default={})
    with st.expander("New isolated run", expanded=True):
        mode = st.selectbox("Run mode", ["replay", "causal"], format_func=lambda value: "Synthetic well replay" if value == "replay" else "Constrained causal simulation")
        bundled_synthetic = st.checkbox("Use bundled structural_dip_01 synthetic environment when no captured source exists", value=False)
        active_name = st.selectbox("Active well", list(well_by_name), index=list(well_by_name).index(active_default))
        models = [model for model in list_prejob_models(root) if model.active_well_id == well_by_name[active_name].well_id]
        step_size = st.number_input("Reveal interval (ft)", min_value=10.0, value=100.0)
        max_dls = st.number_input("Causal DLS limit (degrees/100 ft)", min_value=0.1, max_value=3.0, value=3.0)
        st.caption("Causal mode changes inclination under the selected DLS limit and 85–95° bounds. It uses a fixed synthetic geological field and step-seeded sensor noise.")
        lateral_start = st.number_input("Lateral start MD (ft)", min_value=0.0, value=float(manifest.get("lateral_start_md_ft", 2000.0)))
        plans = [read_json(path) for path in (root / "plans").glob("*.json")]
        plan_labels = {f"{plan['name']} ({plan['plan_id'][:8]})": plan for plan in plans}
        plan_options = ["No plan", *plan_labels]
        preferred = st.session_state.get("planning_saved_plan_id")
        preferred_label = next((label for label, plan in plan_labels.items() if plan["plan_id"] == preferred), "No plan")
        selected_plan = st.selectbox("Saved plan", plan_options, index=plan_options.index(preferred_label))
        st.caption("The selected plan pins starting geology. Causal simulation begins at the acquired landing station; it does not execute the plan's stations.")
        chosen_plan = plan_labels.get(selected_plan)
        geological_model = None
        if chosen_plan and chosen_plan.get("geological_model"):
            from app.model.schemas import PrejobModel
            geological_model = PrejobModel.model_validate(chosen_plan["geological_model"])
            st.info(f"Plan geology is pinned: {model_label(geological_model)}")
        elif chosen_plan:
            st.warning("This legacy plan has no saved geological model. Save a model-linked plan from Planning to use it in a new run.")
        elif models:
            model_ids = [model.interpretation.version_id for model in models]
            preferred_model = st.session_state.get("planning_selected_model")
            index = model_ids.index(preferred_model) if preferred_model in model_ids else 0
            geological_model = st.selectbox("Starting interpretation", models, index=index, format_func=model_label)
        else:
            st.info("Save an interpretation from selected offset picks in Correlation Panel before starting a new run.")
        model_ready = geological_model is not None
        if geological_model is not None:
            st.caption("Offset evidence: " + ", ".join(geological_model.well_names.get(identifier, identifier)
                                                      for identifier in geological_model.offset_well_ids))
            try:
                validate_prejob_model(root, geological_model, active_well_id=well_by_name[active_name].well_id)
            except ValueError as exc:
                model_ready = False
                st.error(str(exc))
        ensemble_supported = bundled_synthetic or manifest.get("scenario_version") == "structural_dip_01-v1"
        enable_ensemble = st.checkbox("Enable uncertainty ensemble · synthetic GR calibration", value=False,
                                      disabled=not ensemble_supported, key=f"uncertainty_enable_{root.resolve()}")
        ensemble_settings = None
        if enable_ensemble and ensemble_supported:
            model_version = st.selectbox("Uncertainty model", ["Calibration uncertainty (v2)", "Known calibration (legacy v1)"],
                                         key=f"uncertainty_model_version_{root.resolve()}")
            calibration_model = model_version == "Calibration uncertainty (v2)"
            if calibration_model:
                st.caption("Persistent GR bias is unknown. Five equally weighted hypotheses (−16, −8, 0, +8, +16 API) are frozen with the run; GR alone cannot identify the true bias.")
            else:
                st.caption("Legacy v1 assumes the nominal sensor calibration is known. Its weighted intervals and probability remain conditional on that assumption.")
            with st.expander("Ensemble assumptions · frozen with this run"):
                count = st.selectbox("Models per calibration hypothesis" if calibration_model else "Ensemble members", [128, 256, 512], index=1)
                prior_std = st.number_input("Initial center standard deviation (ft)", min_value=0.1, max_value=100.0, value=10.0)
                discrepancy = st.number_input("GR model discrepancy standard deviation (API)", min_value=0.1, max_value=40.0, value=4.0)
                st.caption("Nominal response: 80 API at center, 2 API/ft signed gradient, 20–160 API clipping and 0.6 API noise. Each v2 branch adjusts for one persistent bias; other settings remain at their documented defaults.")
            settings_class = CalibrationSettings if calibration_model else EnsembleSettings
            ensemble_settings = settings_class(member_count=count, prior_center_std_ft=float(prior_std),
                                               model_discrepancy_std_api=float(discrepancy))
        if st.button("Open Correlation Panel", key="new_run_correlation"):
            st.session_state["nav_target"] = "Correlation Panel"
            st.rerun()
        if st.button("Initialize new run", disabled=not model_ready):
            active = well_by_name[active_name]
            try:
                interpretation = geological_model.interpretation
                top, base = interpretation.top_control_points, interpretation.base_control_points
                uncertainty = interpretation.uncertainty.band_tvd_ft
                end_md = min(curve.depth_max_ft for curve in active.curve_inventory.values())
                config = SimulationConfig(
                    active_well_id=active.well_id, mode=mode,
                    offset_well_ids=geological_model.offset_well_ids,
                    start_md_ft=float(lateral_start), end_md_ft=end_md,
                    lateral_start_md_ft=float(lateral_start), step_size_ft=float(step_size),
                    plan_id=chosen_plan["plan_id"] if chosen_plan else None,
                    geological_model=geological_model,
                    ensemble_settings=ensemble_settings,
                    scenario_version="structural_dip_01-v1" if bundled_synthetic else manifest.get("scenario_version", "unspecified"),
                    seed=int(manifest.get("seed", 123)),
                    max_dls_deg_per_100ft=float(max_dls),
                    use_default_synthetic_scenario=bundled_synthetic,
                )
                try:
                    previous_config = load_simulation_config(root)
                except FileNotFoundError:
                    previous_config = None
                created = initialize_run(root, config, top, base, uncertainty, hidden_truth_path=previous_config.hidden_truth_path if previous_config else None)
            except (ValueError, FileNotFoundError) as exc:
                st.error(str(exc))
            else:
                st.session_state[f"{run_selection_key}_pending"] = created.run_id
                st.rerun()


def _run_review(root, selected_run, view, run_selection_key):
    config, state = view["config"], view["state"]
    st.subheader("Review this run")
    review, compare, evaluate = st.columns(3)
    for column, label, page in ((review, "Review recorded decisions", "Decision Review"),
                                  (compare, "Compare run branches", "Run Comparison"),
                                  (evaluate, "Open Evaluation", "Evaluation")):
        if column.button(label, use_container_width=True):
            remember_selected_run(st.session_state, root, selected_run)
            if page == "Run Comparison":
                st.session_state["comparison_target"] = {"project_root": str(root.resolve()), "run_id": selected_run}
            st.session_state["nav_target"] = page
            st.rerun()
    if not state.complete and st.button("Fork current run for a command comparison"):
        forked = fork_run(root, run_id=selected_run)
        st.session_state[f"{run_selection_key}_pending"] = forked.run_id
        st.rerun()
    with st.expander("Estimated-zone history and metrics", expanded=state.complete):
        metrics = view["metrics"]
        if metrics:
            st.markdown("#### Persisted estimated-zone history")
            last = metrics[-1]
            a, b, c = st.columns(3)
            a.metric("Estimated lateral in zone (%)", f"{last['percent_in_zone']:.2f}")
            b.metric("Estimated center distance (ft)", f"{last['avg_center_distance']:.2f}")
            c.metric("Evaluated lateral length (ft)", f"{last.get('evaluated_length_ft', 0):.1f}")
            if last.get("command_response"):
                st.write("Effective causal command", last["command_response"])
            st.plotly_chart(build_kpi_trend_figure([row["step_index"] for row in metrics], [row["percent_in_zone"] for row in metrics]), use_container_width=True, config=chart_config())
            with st.expander("Decision-time metric provenance"):
                st.dataframe(pd.DataFrame(metrics), hide_index=True)
    if state.complete:
        st.markdown("#### Completed retrospective evaluation")
        from app.services.evaluation_view import load_evaluation_view
        evaluation_view = load_evaluation_view(root, selected_run)
        evaluation = evaluation_view["evaluation"]
        if evaluation_view["evaluation_error"]:
            st.warning(evaluation_view["evaluation_error"])
        if st.button("Evaluate completed run against withheld truth"):
            from app.services.evaluation_view import evaluate_and_save
            try:
                evaluation = evaluate_and_save(root, selected_run)
            except ValueError as exc:
                st.error(str(exc))
        if evaluation:
            a, b = st.columns(2)
            a.metric("Independent true lateral in zone", f"{evaluation['metrics']['percent_in_zone']:.2f}%")
            b.metric("Independent maximum excursion", f"{evaluation['metrics']['max_overshoot_ft']:.2f} ft")
            st.caption("Open Evaluation for the placement plot, interpretation errors and provenance.")
        if st.button("Run constrained causal HOLD and observation-guided comparison"):
            from app.io.project_store import atomic_write_json
            from app.services.evaluation import load_completed_scenario
            from app.sim.causal import compare_strategies
            comparison = compare_strategies(scenario=load_completed_scenario(root, run_id=selected_run), seed=config.seed)
            atomic_write_json(view["scope"] / "evaluation" / "comparison.json", comparison)
        comparison = read_json(view["scope"] / "evaluation" / "comparison.json", default={})
        if comparison:
            st.caption("These are separate causal runs from the same landing state. Their bounded commands change their simulated paths.")
            st.caption("Single synthetic scenario/seed with known signed GR calibration; not field-validated steering or an operational safety claim.")
            comparison_frame = pd.DataFrame({name: value["metrics"] for name, value in comparison["runs"].items()}).T
            headline = ["percent_in_zone", "in_zone_length_ft", "evaluated_length_ft", "dls_violation_count", "avg_center_distance_ft"]
            comparison_frame = comparison_frame[headline + [name for name in comparison_frame if name not in headline]]
            st.dataframe(comparison_frame, column_config={
                "percent_in_zone": st.column_config.NumberColumn("Synthetic lateral in-zone (%)", format="%.3f"),
                "in_zone_length_ft": st.column_config.NumberColumn("In-zone length (ft)", format="%.1f"),
                "evaluated_length_ft": st.column_config.NumberColumn("Evaluated lateral (ft)", format="%.0f"),
                "avg_center_distance_ft": st.column_config.NumberColumn("Mean center distance (ft)", format="%.3f"),
            })
            comparison_download = comparison_frame.assign(
                scenario_version=comparison["scenario_version"], seed=comparison["seed"],
                scope="single synthetic scenario; known signed GR calibration; not field validation",
            )
            st.download_button("Download synthetic comparison CSV", data=comparison_download.to_csv().encode("utf-8"),
                               file_name=f"synthetic-comparison-{selected_run}-seed-{comparison['seed']}.csv",
                               mime="text/csv", on_click="ignore")
    if st.button("Open Report Export"):
        st.session_state["report_target"] = {"project_root": str(root.resolve()), "run_id": selected_run}
        st.session_state["nav_target"] = "Report Export"
        st.rerun()


def render(project_root: str | None) -> None:
    render_page_header("Interpretation and Steering", "Inspect acquired data, preview a command, and advance.")
    if not project_root:
        st.info("Open a project or load the case study from Dashboard.")
        return
    root = Path(project_root)
    run_selection_key = f"steering_run_{root.resolve()}"
    pending_run = st.session_state.pop(f"{run_selection_key}_pending", None)
    if pending_run is not None:
        remember_selected_run(st.session_state, root, pending_run)
    project, wells = load_project_and_wells(root)
    if not wells:
        st.info("Import wells before starting a replay.")
        return
    run_ids = sorted(path.name for path in (root / "runs").glob("*") if path.is_dir())
    if not run_ids:
        st.info("Create a run from saved offset picks to begin steering.")
        _new_run_controls(root, project, wells, run_selection_key)
        return
    active = active_run_id(root)
    st.session_state[run_selection_key] = selected_run_choice(st.session_state, root, run_ids, active)
    run_column, status_column = st.columns([3, 2], vertical_alignment="center")
    with run_column:
        selected_run = st.selectbox("Saved steering run", run_ids, index=None, label_visibility="collapsed",
                                    format_func=lambda identifier: run_label(root, identifier), key=run_selection_key,
                                    on_change=lambda: remember_selected_run(st.session_state, root, st.session_state.get(run_selection_key)))
    remember_selected_run(st.session_state, root, selected_run)
    try:
        view = load_operator_view(root, selected_run)
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        _new_run_controls(root, project, wells, run_selection_key)
        return
    config, state, latest = view["config"], view["state"], view["interpretation"]
    if latest is None or not all(point.x_ft is not None for point in latest.top_control_points):
        st.warning("This legacy run has an MD-based interpretation. Initialize a new spatial replay from offset picks.")
        _new_run_controls(root, project, wells, run_selection_key)
        return
    status = "Complete" if state.complete else "Running"
    status_column.caption(f"{config.mode.title()} · Step {state.step_index} · Acquired MD {state.revealed_md_ft:,.1f} ft · {status}")
    steer, history, setup = st.tabs(
        ["Steer", "History & results", "Run setup"], key=f"steering_run_workspace_{selected_run}",
        default="History & results" if state.complete else "Steer",
    )
    with steer:
        _steering_workspace(root, view)
    with history:
        _run_review(root, selected_run, view, run_selection_key)
    with setup:
        st.markdown("#### Current run")
        st.caption(f"Run {config.run_id} · Seed {config.seed} · {config.scenario_version}")
        if config.geological_model is not None:
            model = config.geological_model
            st.info(f"Starting geology · {model_label(model)}")
            st.caption(f"Frozen model {model.model_sha256[:12]} · {len(model.offset_well_ids)} offset wells. "
                       "Interpretation revisions remain specific to this run.")
        if config.scenario_version == "structural_dip_01-v1":
            st.caption("Synthetic sensor calibration: GR = 80 + 2 × signed center distance (ft), with 0.6 API Gaussian noise, clipped to 20–160 API. This known signed signal and one 2D scenario are not field validation.")
        st.caption("Replay recommendations do not change the recorded trajectory. Estimated-zone diagnostics and completed truth evaluation are reported separately.")
        _new_run_controls(root, project, wells, run_selection_key)
