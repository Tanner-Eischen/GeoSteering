"""Published, paired synthetic evaluation, independent of an operator's run."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.ui.theme import render_page_header

COLORS = {"hold": "#7b8794", "regional_plan": "#b7791f", "guided": "#0f766e"}


def results_figure(cases, labels):
    fig = go.Figure()
    for strategy, label in labels.items():
        means = [case["strategies"][strategy]["mean_percent_in_zone"] for case in cases]
        lows = [case["strategies"][strategy]["min_percent_in_zone"] for case in cases]
        highs = [case["strategies"][strategy]["max_percent_in_zone"] for case in cases]
        fig.add_trace(go.Bar(
            name=label, y=[case["label"] for case in cases], x=means, orientation="h",
            marker_color=COLORS[strategy],
            error_x={"type": "data", "symmetric": False,
                     "array": [high - mean for high, mean in zip(highs, means)],
                     "arrayminus": [mean - low for low, mean in zip(lows, means)]},
            hovertemplate="%{y}<br>Mean in zone: %{x:.1f}%<extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(barmode="group", height=max(350, len(cases) * 88),
                      margin={"t": 20, "b": 65},
                      legend={"orientation": "h", "y": -0.16, "x": 0},
                      xaxis={"title": "Completed lateral in zone (%)", "range": [0, 102]},
                      yaxis={"autorange": "reversed", "automargin": True})
    return fig


def render(project_root: str | None) -> None:
    from app.study.robustness import DEFAULT_RESULTS, load_summary

    render_page_header(
        "Robustness study",
        "How does observation-guided steering behave when geology and measurements change?",
        chips=["Paired strategies", "Frozen protocol", "Synthetic evaluation"],
    )
    st.caption("Published benchmark results are independent of the project and run currently open in the sidebar.")
    try:
        summary = load_summary()
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"The verified study results could not be loaded: {exc}")
        st.code("python -m tools.run_robustness_study --out output/robustness-study")
        return
    labels = summary["strategies"]
    evaluation = summary["evaluation"]
    st.markdown("#### Performance across held-out cases")
    a, b, c = st.columns(3)
    a.metric("Evaluation configurations", summary["counts"]["evaluation_cases"])
    b.metric("Guided · mean in zone", f"{evaluation['mean_percent_in_zone']['guided']:.1f}%")
    improvement = evaluation["paired"]["guided_minus_regional_plan_pp"]["mean"]
    c.metric("Guided − regional plan", f"{improvement:+.1f} pp")
    st.caption("Equal-weight descriptive results for the predefined cases. Whiskers below show the min–max across noise seeds; they are not confidence intervals.")
    split = st.radio("Study split", ["Held-out evaluation", "Development controls"], horizontal=True)
    split_key = "evaluation" if split == "Held-out evaluation" else "development"
    cases = [case for case in summary["case_results"] if case["split"] == split_key]
    st.plotly_chart(results_figure(cases, labels), use_container_width=True)
    st.markdown("#### Inspect a configuration")
    selected = st.selectbox("Configuration", cases, format_func=lambda case: case["label"])
    st.write(selected["description"])
    rows = []
    for strategy, label in labels.items():
        metrics = selected["strategies"][strategy]
        rows.append({"Strategy": label, "Mean in zone (%)": metrics["mean_percent_in_zone"],
                     "Worst seed (%)": metrics["min_percent_in_zone"],
                     "Mean max excursion (ft)": metrics["mean_max_overshoot_ft"],
                     "Mean inclination change (°)": metrics["mean_total_inc_change_deg"],
                     "Max DLS violations": metrics["max_dls_violation_count"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={name: st.column_config.NumberColumn(format="%.2f")
                                for name in rows[0] if name not in {"Strategy", "Max DLS violations"}})
    with st.expander("Geology, sensor assumptions and pairing"):
        st.write(f"{selected['seed_count']} paired noise seeds; the three strategies share geology, landing and mechanical limits.")
        st.json({"geology": selected["geology"], "sensor": selected["sensor"]})
    st.markdown("#### Where guidance fails")
    worst = summary["worst_guided"]
    worst_label = next((case["label"] for case in summary["case_results"] if case["case_id"] == worst["case_id"]), worst["case_id"])
    st.warning(f"Worst held-out guided trial: {worst_label}, seed {worst['seed']} — {worst['percent_in_zone']:.1f}% in zone.")
    root = DEFAULT_RESULTS
    st.image(str(root / "robustness_worst_case.png"), caption="Retrospective trajectory against withheld geology, after trial completion.")
    with st.expander("Protocol, evidence and limits", expanded=False):
        for note in summary["interpretation_notes"]:
            st.write("• " + note)
        st.caption(f"Protocol SHA-256: {summary['manifest_sha256']}")
        st.caption(f"Frozen source fingerprint: {summary['source_fingerprint']}")
        st.code("python -m tools.run_robustness_study --out output/my-robustness-study")
    a, b, c = st.columns(3)
    for column, filename, label in ((a, "trials.csv", "Download trial metrics"),
                                     (b, "paired.csv", "Download paired differences"),
                                     (c, "summary.json", "Download study summary")):
        path = root / filename
        column.download_button(label, data=path.read_bytes(), file_name=filename,
                                mime="application/json" if filename.endswith("json") else "text/csv", on_click="ignore")
