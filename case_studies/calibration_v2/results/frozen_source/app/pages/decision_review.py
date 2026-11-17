"""Interactive review of saved decisions and their acquired evidence."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.plot.steering import build_active_window_figure
from app.services.decision_review import list_review_steps, load_decision_review
from app.services.operator_workflow import run_label
from app.services.run_paths import active_run_id
from app.ui.theme import render_page_header
from app.ui.workspace import remember_selected_run, selected_run_choice


def _interpretation_figure(view):
    path = view["frames"]["trajectory"]
    fig = go.Figure()
    if path.empty:
        return fig
    window = path.loc[path.md_ft >= max(float(path.md_ft.min()), view["revealed_md_ft"] - 750)]
    spatial = all(point.x_ft is not None for model in (view["before_interpretation"], view["interpretation"])
                  for point in [*model.top_control_points, *model.base_control_points])
    xcol = ("x_ft" if "x_ft" in window else "east_ft") if spatial else "md_ft"
    domain = [float(window[xcol].min()), float(window[xcol].max())]
    if domain[1] - domain[0] < 1:
        domain = [domain[0] - 1, domain[1] + 1]
    before, applied = view["before_interpretation"], view["interpretation"]
    changed = before.top_control_points != applied.top_control_points or before.base_control_points != applied.base_control_points
    versions = [(applied, "Decision interpretation", "#0f766e", "solid")]
    if changed:
        versions.insert(0, (before, "Previous interpretation", "#b45309", "dash"))
    for version, label, color, dash in versions:
        for boundary, points in (("top", version.top_control_points), ("base", version.base_control_points)):
            spatial = all(point.x_ft is not None for point in points)
            coordinates = [float(point.x_ft if spatial else point.md_ft) for point in points]
            # Explicitly include interior knots so revisions are not flattened
            # into one endpoint-to-endpoint line.
            knots = sorted({*domain, *(x for x in coordinates if domain[0] <= x <= domain[1])})
            fig.add_trace(go.Scatter(x=knots, y=evaluate_piecewise_linear(points, knots),
                                     name=f"{label} · {boundary}", line={"color": color, "dash": dash, "width": 2}))
    fig.add_trace(go.Scatter(x=window[xcol], y=window.tvd_ft, name="Acquired trajectory",
                             mode="lines+markers", line={"color": "#234b65", "width": 3}, marker={"size": 4}))
    fig.update_layout(height=430, margin={"t": 15, "b": 125},
                      legend={"orientation": "h", "y": -0.4, "yanchor": "top", "x": 0},
                      xaxis_title="Shared along-track x (ft)" if spatial else "Measured depth (ft)",
                      yaxis_title="Local TVD (ft; positive down)")
    fig.update_yaxes(autorange="reversed")
    return fig


def _boundary_changes(before, applied):
    rows = []
    for boundary in ("top", "base"):
        old = getattr(before, f"{boundary}_control_points")
        new = getattr(applied, f"{boundary}_control_points")
        if old == new:
            continue
        spatial = all(point.x_ft is not None for point in [*old, *new])
        knots = sorted({float(point.x_ft if spatial else point.md_ft) for point in [*old, *new]})
        for x, previous, current in zip(knots, evaluate_piecewise_linear(old, knots), evaluate_piecewise_linear(new, knots)):
            if abs(float(current - previous)) > 1e-8:
                rows.append({"Boundary": boundary.title(), "x (ft)" if spatial else "MD (ft)": x,
                             "Before TVD (ft)": float(previous), "Applied TVD (ft)": float(current),
                             "Change (ft)": float(current - previous)})
    return rows


def render(project_root: str | None) -> None:
    render_page_header("Decision Review", "Revisit the evidence, interpretation and command recorded at each saved step.")
    if not project_root:
        st.info("Open a project to review its saved decisions.")
        return
    root = Path(project_root)
    runs = sorted(path.name for path in (root / "runs").glob("*") if path.is_dir())
    if not runs:
        st.info("Initialize a steering run to start a decision history.")
        return
    selected = selected_run_choice(st.session_state, root, runs, active_run_id(root))
    run_key = f"review_run_{root.resolve()}"
    st.session_state[run_key] = selected
    run_id = st.selectbox("Saved run to review", runs, index=None,
                          format_func=lambda value: run_label(root, value), key=run_key,
                          on_change=lambda: remember_selected_run(st.session_state, root, st.session_state.get(run_key)))
    remember_selected_run(st.session_state, root, run_id)
    try:
        steps = list_review_steps(root, run_id)
    except (ValueError, FileNotFoundError) as exc:
        st.error(str(exc))
        return
    by_step = {step["step_index"]: step for step in steps}

    def step_label(index):
        step = by_step[index]
        if index == 0:
            return f"Baseline · MD {step['md_from_ft']:,.0f} ft"
        return f"Step {index} · MD {step['md_from_ft']:,.0f}–{step['md_to_ft']:,.0f} ft"

    left, right = st.columns([1.2, 1])
    with left:
        step_index = st.selectbox("Saved decision", list(by_step), index=len(by_step) - 1,
                                 format_func=step_label, key=f"review_step_{root.resolve()}_{run_id}")
    with right:
        phase = st.radio("Review phase", ["decision", "after"], horizontal=True,
                         format_func=lambda value: "At decision" if value == "decision" else "After interval",
                         key=f"review_phase_{root.resolve()}_{run_id}")
    try:
        view = load_decision_review(root, run_id, step_index, phase)
    except (ValueError, FileNotFoundError) as exc:
        st.error(str(exc))
        return
    a, b, c = st.columns(3)
    a.metric("Evidence through MD (ft)", f"{view['revealed_md_ft']:,.1f}")
    b.metric("Selected step", str(step_index))
    c.metric("Mode", view["run"]["mode"].title())
    if phase == "decision":
        st.info("Decision-time view: the next interval's logs and outcomes remain hidden. Metrics stop before this interval.")
    else:
        st.info("After-interval view: observations and persisted estimated metrics include this interval. These are not withheld-truth scores.")
    if view["run"]["parent_run_id"]:
        st.caption(f"Fork of {view['run']['parent_run_id'][:8]} at step {view['run']['forked_at_step']} · Selected run {run_id[:8]}")
    decision, interpretation = view["decision"], view["interpretation"]
    with st.container(border=True):
        if decision:
            command = decision["recommendation"]
            st.markdown("#### Recorded decision")
            st.write(f"**Recommendation: {command['action']}**")
            if command["target_inc_deg"] is not None:
                st.write(f"Requested inclination: {command['target_inc_deg']:.2f}°")
            st.markdown("**Observed evidence**")
            st.text(decision["observations"])
        else:
            st.markdown("#### Pre-job baseline")
            st.write("No command has been recorded at this baseline. The original offset interpretation is shown.")
        st.markdown("**Interpretation rationale**")
        st.text(interpretation.rationale)
        st.caption(f"Saved interpretation {interpretation.version_id[:8]} · Previous {view['before_interpretation'].version_id[:8]}")
    st.markdown("#### Acquired observations and interpretation")
    st.plotly_chart(_interpretation_figure(view), use_container_width=True)
    logs = view["frames"]["logs"]
    if not logs.empty:
        st.plotly_chart(build_active_window_figure(logs, view["revealed_md_ft"], view["run"]["window_size_ft"],
                                                   view["run"]["curves_used"]), use_container_width=True)
    else:
        st.info("No log samples were acquired by this review endpoint.")
    changes = _boundary_changes(view["before_interpretation"], interpretation)
    if changes:
        st.markdown("**Boundary revision at this decision**")
        st.dataframe(pd.DataFrame(changes), hide_index=True)
    else:
        st.caption("The top and base boundaries were carried forward without a geometric revision.")
    st.markdown("#### Persisted estimated-zone diagnostics")
    if view.get("uncertainty") is not None:
        from app.pages.uncertainty import render_snapshot
        with st.expander("Ensemble known at this review endpoint"):
            render_snapshot(view["uncertainty"], view["frames"]["trajectory"], compact=True)
            st.caption("This is the original saved ensemble at the selected phase; later measurements are excluded.")
    metric = view["metric"]
    if metric:
        a, b, c = st.columns(3)
        a.metric("Estimated in zone (%)", f"{metric['percent_in_zone']:.2f}")
        b.metric("Estimated center distance (ft)", f"{metric['avg_center_distance']:.2f}")
        c.metric("Evaluated length (ft)", f"{metric.get('evaluated_length_ft', 0):,.1f}")
        st.caption(f"Original snapshot after step {metric['step_index']} · Interpretation {metric['interpretation_version_id'][:8]}. Historical values are never recalculated using later interpretations.")
        if phase == "after" and metric.get("command_response"):
            response = metric["command_response"]
            st.write(f"Applied inclination: {response['effective_inc_deg']:.2f}° · Requested: {response['requested_inc_deg']:.2f}°")
            if response.get("clipped"):
                st.warning("The recorded command was limited by its mechanical bounds.")
    else:
        st.caption("No metric snapshot existed at this endpoint. The selected interval has not contributed a score in this view.")
    with st.expander("Download the selected acquired prefix"):
        st.caption(f"Only data through MD {view['revealed_md_ft']:,.1f} ft from the selected run and phase are included.")
        for name in ("logs", "trajectory"):
            st.download_button(f"Download reviewed {name} CSV", view["frames"][name].to_csv(index=False).encode("utf-8"),
                               file_name=f"review-{run_id}-step-{step_index}-{phase}-{name}.csv", mime="text/csv",
                               key=f"review_download_{name}_{run_id}_{step_index}_{phase}", on_click="ignore")
