"""Live conditional ensembles and separately scored calibration evidence."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.plot.uncertainty import ensemble_figure
from app.services.operator_workflow import load_operator_view, run_label
from app.services.run_paths import active_run_id
from app.services.uncertainty import load_uncertainty_snapshot
from app.services.uncertainty_assessment import assess_commands
from app.ui.theme import render_page_header
from app.ui.workspace import remember_selected_run, selected_run_choice
from app.uncertainty.ensemble import forecast_ensemble, summarize_ensemble, target_probability

PHASES = {"prior_current": "Before observation", "posterior_current": "After observation",
          "forecast_250": "250-ft forecast", "forecast_500": "500-ft forecast"}


def render_snapshot(snapshot, trajectory, compact=False):
    state = snapshot["ensemble"]
    anchor = float(state["x_ft"])
    bit = trajectory.iloc[-1] if not trajectory.empty else None
    bit_x = float(bit.get("x_ft", bit.get("east_ft"))) if bit is not None else anchor
    grid = sorted({*np.linspace(anchor, anchor + 500, 11).tolist(),
                   *([bit_x] if anchor <= bit_x <= anchor + 500 else [])})
    forecast = forecast_ensemble(state, grid)
    index = grid.index(bit_x) if bit_x in grid else 0
    cards = forecast
    if bit is None or abs(bit_x - anchor) <= 1e-8:
        # Forecast paths may replicate a concentrated posterior. Current cards
        # must retain the exact saved weights used by posterior calibration.
        cards = summarize_ensemble(state)
        index = 0
    width = cards["center"]["q95"][index] - cards["center"]["q05"][index]
    a, b, c = st.columns(3)
    a.metric("90% center interval width", f"{width:.2f} ft")
    b.metric("Effective model count", f"{state['ess']:.1f} / {len(state['members'])}")
    if bit is not None and bit_x in grid:
        probability = target_probability(cards, index, float(bit.tvd_ft))
        c.metric("Model probability in target", f"{100 * probability:.1f}%")
    else:
        c.metric("Model probability in target", "Unavailable")
    st.caption("Probabilities and nominal 90% intervals are conditional on the declared synthetic sensor and geological process model. They are not field-calibrated confidence.")
    st.caption("Effective model count measures weight concentration, not whether the geological or sensor assumptions are correct.")
    if state["ess"] < len(state["members"]) / 4:
        st.warning("Few ensemble members carry most of the weight. The interval may be unreliable; inspect calibration and measurement diagnostics.")
    diagnostic = state.get("last_update", {})
    if diagnostic.get("predictive_conflict"):
        st.warning("The measurement conflicts with the model's prior prediction. A narrow posterior does not resolve possible model mismatch.")
    measurement = snapshot.get("measurement")
    if measurement:
        st.caption(f"Last selected measurement: MD {measurement['md_ft']:,.1f} ft · {snapshot['observation_status']} · snapshot after acquired step {snapshot['step_index']}")
    else:
        st.caption(f"No new located GR measurement · {snapshot['observation_status']} · acquired step {snapshot['step_index']}")
    if not compact:
        st.plotly_chart(ensemble_figure(forecast, trajectory), width="stretch")
        st.caption("The shaded region describes uncertainty in the target center; median top/base lines describe layer geometry. Thickness uncertainty is retained independently because this GR model cannot identify it.")
    return forecast


def _live(project_root):
    if not project_root:
        st.info("Open a project to inspect a run ensemble. The calibration evidence is available in the other tab.")
        return
    root = Path(project_root)
    runs = sorted(path.name for path in (root / "runs").glob("*") if path.is_dir())
    if not runs:
        st.info("Initialize a new steering run with the uncertainty ensemble enabled.")
        return
    selected = selected_run_choice(st.session_state, root, runs, active_run_id(root))
    key = f"uncertainty_run_{root.resolve()}"
    st.session_state[key] = selected
    run_id = st.selectbox("Ensemble run", runs, index=None, format_func=lambda value: run_label(root, value), key=key,
                          on_change=lambda: remember_selected_run(st.session_state, root, st.session_state.get(key)))
    remember_selected_run(st.session_state, root, run_id)
    try:
        view = load_operator_view(root, run_id)
        current = view.get("uncertainty")
        if current is None:
            st.info("This saved run has no ensemble. Start a new isolated run and enable uncertainty; existing histories are preserved.")
            if st.button("Open Steering to configure a new run"):
                st.session_state["nav_target"] = "Steering Console"
                st.rerun()
            return
        step = st.selectbox("Ensemble snapshot", list(range(view["state"].step_index + 1)),
                            index=view["state"].step_index, format_func=lambda value: f"After acquired step {value}",
                            key=f"uncertainty_step_{root.resolve()}_{run_id}")
        snapshot = load_uncertainty_snapshot(root, run_id, step)
        trajectory = view["frames"]["trajectory"]
        trajectory = trajectory.loc[trajectory.md_ft <= snapshot["revealed_md_ft"]]
        st.caption(f"Acquired through MD {snapshot['revealed_md_ft']:,.1f} ft · snapshot {snapshot['snapshot_sha256'][:12]}")
        forecast = render_snapshot(snapshot, trajectory)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.markdown("#### Compare next-command probabilities")
    if step != view["state"].step_index:
        st.info("Select the latest acquired step to assess current commands. This historical view does not use later observations.")
    elif view["config"].mode != "causal" or view["state"].complete:
        st.info("Command assessment is available during an unfinished causal run. These saved ensemble intervals remain inspectable.")
    else:
        try:
            assessment = assess_commands(root, run_id, step)
            st.dataframe(pd.DataFrame(assessment["actions"]), hide_index=True, width="stretch",
                         column_config={"Model probability in target (%)": st.column_config.NumberColumn(format="%.1f"),
                                        "Center interval width (ft)": st.column_config.NumberColumn(format="%.2f")})
            st.caption("All three commands use the same geological forecast draws. These are probabilities at the next projected station, not whole-well success rates or a command commitment.")
        except (ValueError, OSError) as exc:
            st.info(str(exc))
    with st.expander("Frozen assumptions and measurement diagnostics"):
        st.write("The prior starts from the frozen offset model. Manual boundary revisions are not assimilated again as measurements.")
        settings = snapshot["ensemble"]["settings"]
        st.dataframe(pd.DataFrame([{"Setting": name, "Value": str(value)} for name, value in settings.items()]), hide_index=True, width="stretch")
        st.json(snapshot["ensemble"].get("last_update", {}))
        st.caption(f"Settings hash: {snapshot['settings_sha256']} · Baseline hash: {snapshot['baseline_sha256']}")
    columns = {"x_ft": forecast["x_ft"], **{f"center_{q}_tvd_ft": values for q, values in forecast["center"].items()}}
    a, b = st.columns(2)
    a.download_button("Download ensemble snapshot", json.dumps(snapshot, indent=2, allow_nan=False).encode(),
                       file_name=f"ensemble-{run_id}-step-{step}.json", mime="application/json", on_click="ignore")
    b.download_button("Download forecast intervals CSV", pd.DataFrame(columns).to_csv(index=False).encode(),
                       file_name=f"ensemble-forecast-{run_id}-step-{step}.csv", mime="text/csv", on_click="ignore")


def _calibration():
    try:
        from app.study.uncertainty_calibration import DEFAULT_RESULTS, load_uncertainty_summary
        summary = load_uncertainty_summary()
    except (ImportError, OSError, ValueError) as exc:
        st.info(f"Calibration evidence is unavailable: {exc}")
        return
    st.markdown("#### Does the nominal 90% interval cover the truth?")
    st.caption("This separate synthetic study measures coverage and width. It does not tune the model or change the existing steering benchmark.")
    phases = summary["evaluation"]["phases"]
    a, b, c = st.columns(3)
    a.metric("Evaluation configurations", summary["counts"]["evaluation_cases"])
    b.metric("After-observation coverage", f"{phases['posterior_current']['mean_coverage_pct']:.1f}%")
    c.metric("500-ft forecast coverage", f"{phases['forecast_500']['mean_coverage_pct']:.1f}%")
    cases = [case for case in summary["case_results"] if case["split"] == "evaluation"]
    fig = go.Figure()
    for phase, label in PHASES.items():
        fig.add_trace(go.Bar(name=label, y=[case["label"] for case in cases],
                             x=[case["phases"][phase]["mean_coverage_pct"] for case in cases], orientation="h"))
    fig.add_vline(x=90, line_dash="dash", line_color="#b45309")
    fig.update_layout(barmode="group", height=max(450, len(cases) * 100),
                      xaxis={"range": [0, 102], "title": "Empirical center coverage (%)"},
                      yaxis={"autorange": "reversed", "automargin": True},
                      legend={"orientation": "h", "y": -0.25, "yanchor": "top"}, margin={"b": 130})
    st.plotly_chart(fig, width="stretch")
    selected = st.selectbox("Calibration configuration", cases, format_func=lambda item: item["label"])
    st.write(selected["description"])
    st.dataframe(pd.DataFrame([{"Phase": PHASES[phase], **values} for phase, values in selected["phases"].items()]), hide_index=True, width="stretch")
    st.caption("Coverage averages are descriptive for handpicked cases. Correlated points along a well are not independent trials; horizons have explicit valid-domain point counts.")
    worst = summary.get("worst_trial", {})
    if worst:
        st.warning(f"Failure example: {worst.get('case_id', 'evaluation case')}, seed {worst.get('seed')} — "
                   f"{worst.get('coverage_pct', 0):.2f}% center coverage. A well-behaved weight distribution does not establish calibrated uncertainty.")
    failure_plot = DEFAULT_RESULTS / "uncertainty_failure.png"
    if failure_plot.is_file():
        st.image(str(failure_plot), caption="Retrospective interval coverage against withheld center; truth is used only by the separate study scorer.")
    with st.expander("Calibration protocol and limits"):
        for note in summary["interpretation_notes"]:
            st.write("• " + note)
        st.caption(f"Executed protocol hash: {summary['manifest_sha256']}")
        st.code("python -m tools.run_uncertainty_study --out output/my-uncertainty-study")
        for filename in ("summary.json", "trial_metrics.csv", "frozen_source.zip"):
            path = DEFAULT_RESULTS / filename
            if path.is_file():
                st.download_button(f"Download {filename}", path.read_bytes(), file_name=f"uncertainty-{filename}", on_click="ignore")


def render(project_root):
    render_page_header("Uncertainty", "Inspect plausible geology, conditional command probabilities and measured interval coverage.",
                       chips=["Acquired measurements only", "Frozen model assumptions", "Nominal 90% intervals"])
    live, calibration = st.tabs(["Run ensemble", "Calibration evidence"])
    with live:
        _live(project_root)
    with calibration:
        _calibration()
