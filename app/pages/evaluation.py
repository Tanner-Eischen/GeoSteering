"""Readable independent evaluation of an explicitly selected completed run."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.services.evaluation_view import evaluate_and_save, load_evaluation_view
from app.services.operator_workflow import run_label
from app.services.run_paths import active_run_id
from app.ui.theme import render_page_header
from app.ui.workspace import remember_selected_run, selected_run_choice


def placement_figure(profile):
    fig = go.Figure()
    x = profile["x_ft"]
    fig.add_trace(go.Scatter(x=x, y=profile["true_top_tvd_ft"], name="Withheld true top",
                             line={"color": "#729a83", "width": 1}))
    fig.add_trace(go.Scatter(x=x, y=profile["true_base_tvd_ft"], name="Withheld true base",
                             line={"color": "#729a83", "width": 1}, fill="tonexty", fillcolor="rgba(114,154,131,0.18)"))
    for key, name in (("estimated_top_tvd_ft", "Estimated top"), ("estimated_base_tvd_ft", "Estimated base")):
        fig.add_trace(go.Scatter(x=profile["estimated_x_ft"], y=profile[key], name=name, line={"color": "#b7791f", "dash": "dot"}))
    fig.add_trace(go.Scatter(x=x, y=profile["tvd_ft"], name="Recorded path", line={"color": "#234b65", "width": 3}))
    fig.update_layout(height=430, margin={"t": 15, "b": 125},
                      legend={"orientation": "h", "y": -0.4, "yanchor": "top"},
                      xaxis_title="Along-section x (ft)")
    fig.update_yaxes(autorange="reversed", title="TVD (ft), positive down")
    return fig


def _navigation(root, run_id):
    columns = st.columns(3)
    for column, label, page in zip(columns, ("Review decisions", "Compare branches", "Open Report Export"),
                                    ("Decision Review", "Run Comparison", "Report Export")):
        if column.button(label, use_container_width=True):
            remember_selected_run(st.session_state, root, run_id)
            if page == "Report Export":
                st.session_state["report_target"] = {"project_root": str(root.resolve()), "run_id": run_id}
            if page == "Run Comparison":
                st.session_state["comparison_target"] = {"project_root": str(root.resolve()), "run_id": run_id}
            st.session_state["nav_target"] = page
            st.rerun()


def render(project_root):
    render_page_header("Evaluation", "Connect the final outcome to the interpretation and decisions that produced it.")
    if not project_root:
        st.info("Open a project or load the case study from Dashboard.")
        return
    root = Path(project_root)
    runs = sorted(path.name for path in (root / "runs").iterdir() if path.is_dir()) if (root / "runs").exists() else []
    if not runs:
        st.info("Start a steering run before evaluating its outcome.")
        return
    choice = selected_run_choice(st.session_state, root, runs, active_run_id(root))
    run_id = st.selectbox("Evaluation run", runs, index=runs.index(choice), format_func=lambda value: run_label(root, value))
    remember_selected_run(st.session_state, root, run_id)
    try:
        view = load_evaluation_view(root, run_id)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    config, state = view["config"], view["state"]
    st.caption(f"{config.mode.title()} · Run {run_id[:8]} · Seed {config.seed} · {config.scenario_version}")
    progress = (state.revealed_md_ft - config.start_md_ft) / (config.end_md_ft - config.start_md_ft)
    st.progress(max(0.0, min(1.0, progress)), text=f"Acquired to MD {state.revealed_md_ft:,.0f} / {config.end_md_ft:,.0f} ft")
    if not state.complete:
        st.info("This run is still in progress. Independent truth scores remain hidden until completion.")
        if view["metrics"]:
            st.metric("Last persisted estimated in-zone (%)", f"{view['metrics'][-1]['percent_in_zone']:.2f}")
            st.caption("An interpretation diagnostic at its recorded step, not an independent placement score.")
        _navigation(root, run_id)
        if st.button("Continue steering", type="primary"):
            st.session_state["nav_target"] = "Steering Console"
            st.rerun()
        return
    if view["evaluation_error"]:
        st.warning(view["evaluation_error"])
    if st.button("Evaluate completed run against withheld truth", type="primary"):
        try:
            evaluate_and_save(root, run_id)
        except (ValueError, OSError) as exc:
            st.error(str(exc))
        else:
            st.rerun()
    result = view["evaluation"]
    if result is None:
        st.info("Acquisition is complete. Evaluate this run to reveal its independent placement and interpretation scores.")
        _navigation(root, run_id)
        return
    st.markdown("#### Independent placement")
    metrics = result["metrics"]
    a, b, c, d = st.columns(4)
    a.metric("True lateral in zone", f"{metrics['percent_in_zone']:.2f}%")
    b.metric("Mean center distance", f"{metrics['avg_center_distance_ft']:.2f} ft")
    c.metric("Maximum excursion", f"{metrics['max_overshoot_ft']:.2f} ft")
    d.metric("Lateral DLS violations", int(metrics["dls_violation_count"]))
    st.caption(f"Scored over {metrics['evaluated_length_ft']:,.0f} ft of lateral, excluding landing. "
               f"Maximum integration interval {metrics['integration_step_max_ft']:g} ft.")
    if config.mode == "replay":
        st.info("This is a fixed-path replay. Recommendations document interpretation; they did not change the recorded placement.")
    else:
        st.caption("Bounded commands changed this synthetic trajectory. Outcome scores describe simplified kinematics and sensors.")
    st.plotly_chart(placement_figure(view["profile"]), use_container_width=True)
    st.markdown("#### Interpretation and mechanical limits")
    errors = result["interpretation_error"]
    baseline = errors["baseline_interpretation_mean_absolute_error_ft"]
    final = errors["final_interpretation_mean_absolute_error_ft"]
    left, right = st.columns(2, gap="large")
    with left:
        st.dataframe(pd.DataFrame({"Interpretation": ["Offset baseline", "Final saved interpretation"],
                                    "Mean absolute centerline error (ft)": [baseline, final]}), hide_index=True,
                     use_container_width=True, column_config={"Mean absolute centerline error (ft)": st.column_config.NumberColumn(format="%.3f")})
        if final > baseline:
            st.warning(f"Final interpretation error is {final - baseline:.2f} ft greater than the baseline. This failure is retained in the result.")
        else:
            st.write(f"Final interpretation error decreased by {baseline - final:.2f} ft.")
        st.caption("Errors are averaged at acquired lateral stations. The uncertainty band remains assumed, not statistically calibrated.")
    with right:
        trajectory = view["frames"]["trajectory"]
        lateral = trajectory.loc[trajectory.md_ft > result["lateral_start_md_ft"]]
        fig = go.Figure(go.Scatter(x=lateral.md_ft, y=lateral.dls_deg_per_100ft, name="Lateral DLS", mode="lines+markers"))
        fig.add_hline(y=view["profile"]["lateral_dls_limit"], line_dash="dash", line_color="#b45309")
        fig.update_layout(height=290, margin={"t": 15}, xaxis_title="Measured depth (ft)", yaxis_title="DLS (°/100 ft)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Scoring bound {view['profile']['lateral_dls_limit']:g}°/100 ft; landing curvature is excluded.")
        command_limit = view["profile"]["command_dls_limit"]
        if command_limit is not None and command_limit != view["profile"]["lateral_dls_limit"]:
            st.caption(f"Causal commands were separately bounded at {command_limit:g}°/100 ft.")
    rows = [{"metric": key, "value": value} for key, value in metrics.items()]
    a, b = st.columns(2)
    a.download_button("Download evaluation JSON", json.dumps(result, indent=2).encode(),
                       file_name=f"evaluation-{run_id}.json", mime="application/json", on_click="ignore")
    b.download_button("Download placement metrics CSV", pd.DataFrame(rows).to_csv(index=False).encode(),
                       file_name=f"placement-{run_id}.csv", mime="text/csv", on_click="ignore")
    with st.expander("Evaluation provenance"):
        st.write(f"Interpretation {view['interpretation'].version_id}")
        st.caption(f"Captured truth SHA-256: {result['truth_sha256']}")
        st.caption("Saved evaluation is checked against this completed run's captured evidence before display.")
    _navigation(root, run_id)
