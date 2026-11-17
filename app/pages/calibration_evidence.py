"""Paired calibration-sensitivity evidence, separate from live estimates."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.study.calibration_sensitivity import DEFAULT_RESULTS, load_calibration_summary

LABELS = {
    "v1_nominal": "Original nominal 90%",
    "v2_pooled": "Assumed calibration mixture 90%",
    "v2_envelope": "Calibration envelope",
}
PHASES = {"prior_current": "Before observation", "posterior_current": "After observation",
          "forecast_250": "250-ft forecast", "forecast_500": "500-ft forecast"}
COLORS = {"v1_nominal": "#6b8190", "v2_pooled": "#0f766e", "v2_envelope": "#b45309"}


def render():
    try:
        summary = load_calibration_summary()
    except (OSError, ValueError) as exc:
        st.info(f"Calibration sensitivity evidence is unavailable: {exc}")
        return
    st.markdown("#### Can repeated GR resolve a calibration error?")
    st.write("A persistent sensor bias can resemble a shifted geological layer. The new model keeps five calibration assumptions alive instead of letting repeated readings erase that ambiguity.")
    st.info("The calibration envelope spans the conditional 90% intervals across the declared bias assumptions. It is a sensitivity range, not a calibrated 90% confidence interval. The narrower mixture interval assumes equal weights for those assumptions.")
    cases = [case for case in summary["case_results"] if case["split"] == "evaluation"]
    st.caption(f"{len(cases)} new evaluation configurations · {sum(case['seed_count'] for case in cases)} paired trials · identical measurements for both models. Historical failures are separate development diagnostics.")
    phase = st.selectbox("Interval being assessed", list(PHASES), index=1, format_func=PHASES.get,
                        key="uncertainty_calibration_phase")
    intervals = summary["evaluation"]["intervals"]
    for column, (kind, label) in zip(st.columns(3), LABELS.items()):
        metrics = intervals[kind]["phases"][phase]
        column.metric(label, f"{metrics['mean_coverage_pct']:.1f}%")
        column.caption(f"Measured center coverage · mean width {metrics['mean_width_ft']:.2f} ft")
    fig = go.Figure()
    for kind, label in LABELS.items():
        fig.add_trace(go.Bar(name=label, orientation="h", marker_color=COLORS[kind],
                             y=[case["label"] for case in cases],
                             x=[case["intervals"][kind]["phases"][phase]["mean_coverage_pct"] for case in cases]))
    fig.add_vline(x=90, line_dash="dash", line_color="#334155")
    fig.update_layout(barmode="group", height=max(500, len(cases) * 100),
                      xaxis={"range": [0, 102], "title": "Measured center coverage (%)"},
                      yaxis={"autorange": "reversed", "automargin": True},
                      legend={"orientation": "h", "y": -0.22, "yanchor": "top"},
                      margin={"t": 10, "b": 150, "l": 5, "r": 15})
    st.plotly_chart(fig, width="stretch")
    st.caption("The dashed line marks 90% for comparison. It is not a coverage guarantee for the envelope. Wider intervals must be assessed alongside coverage; correlated stations are not independent trials.")
    historical = summary.get("historical_diagnostic")
    if historical:
        diagnostic = historical["intervals"]
        original = diagnostic["v1_nominal"]["posterior_current"]["coverage_pct"]
        mixture = diagnostic["v2_pooled"]["posterior_current"]["coverage_pct"]
        envelope = diagnostic["v2_envelope"]["posterior_current"]["coverage_pct"]
        st.caption(f"Reused +8 API diagnostic, seed {historical['seed']}: after-observation coverage {original:.2f}% originally, {mixture:.2f}% for the mixture and {envelope:.2f}% for the envelope. This known failure informed the change; it is not fresh validation.")
    selected = st.selectbox("Sensitivity configuration", cases, format_func=lambda case: case["label"],
                            key="uncertainty_calibration_case")
    st.write(selected.get("description", selected.get("evidence_status", "")))
    rows = []
    for kind, label in LABELS.items():
        for name, metrics in selected["intervals"][kind]["phases"].items():
            rows.append({"Interval": label, "Phase": PHASES[name],
                         "Coverage (%)": metrics["mean_coverage_pct"], "Mean width (ft)": metrics["mean_width_ft"],
                         "Scored points": metrics["total_point_count"]})
    st.caption(f"{PHASES[phase]} · selected configuration")
    compact = []
    for kind, label in (("v1_nominal", "Original"), ("v2_pooled", "Mixture"), ("v2_envelope", "Envelope")):
        metrics = selected["intervals"][kind]["phases"][phase]
        compact.append({"Range": label, "Coverage (%)": metrics["mean_coverage_pct"],
                        "Width (ft)": metrics["mean_width_ft"]})
    st.dataframe(pd.DataFrame(compact), hide_index=True, width="stretch",
                 column_config={"Coverage (%)": st.column_config.NumberColumn(format="%.2f"),
                                "Width (ft)": st.column_config.NumberColumn(format="%.2f")})
    with st.expander("All phases and scored point counts"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Coverage (%)": st.column_config.NumberColumn(format="%.2f"),
                                    "Mean width (ft)": st.column_config.NumberColumn(format="%.2f")})
    worst = summary.get("worst_fresh_trial")
    if worst:
        metrics = worst["intervals"]["v2_envelope"]["posterior_current"]
        label = next((case["label"] for case in cases if case["case_id"] == worst["case_id"]), worst["case_id"])
        st.warning(f"Observed failure: {label}, seed {worst['seed']} — the posterior envelope covers {metrics['covered_count']}/{metrics['point_count']} stations. GR does not establish which calibration assumption is correct. A good fit and healthy effective model count do not certify coverage.")
    else:
        st.warning("GR does not establish which calibration assumption is correct. Bias outside the declared range, structural mismatch and clipping can still cause poor coverage.")
    failure = DEFAULT_RESULTS / "calibration_failure.png"
    if failure.is_file():
        st.image(str(failure), caption="Retrospective failure evidence. Geological truth is read only by the separate study scorer.")
    with st.expander("Frozen protocol, assumptions and evidence downloads"):
        for note in summary.get("interpretation_notes", []):
            st.write("• " + note)
        st.caption(f"Executed protocol hash: {summary['manifest_sha256']}")
        st.caption(f"Frozen study source: {summary['source_fingerprint']}")
        st.json(summary.get("historical_diagnostic", {}))
        st.code("python -m tools.run_calibration_study --out output/my-calibration-study")
        for filename in ("summary.json", "trial_metrics.csv", "paired_metrics.csv", "frozen_source.zip"):
            path = DEFAULT_RESULTS / filename
            if path.is_file():
                st.download_button(f"Download calibration {filename}", path.read_bytes(), file_name=f"calibration-{filename}",
                                   on_click="ignore", key=f"uncertainty_calibration_download_{filename}")
