"""Acquired-only side-by-side review of related steering branches."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.services.run_comparison import compare_runs, list_run_catalog
from app.services.run_paths import active_run_id
from app.ui.theme import render_page_header
from app.ui.workspace import selected_run_choice


def _path_figure(result):
    figure = go.Figure()
    for side, color in (("left", "#b45309"), ("right", "#0f766e")):
        run = result["runs"][side]
        path = run["trajectory"]
        figure.add_trace(go.Scatter(
            x=[row.get("x_ft", row["east_ft"]) for row in path], y=[row["tvd_ft"] for row in path],
            mode="lines+markers", name=f"{side.title()} · {run['run_id'][:8]}",
            line={"color": color, "width": 3}, marker={"size": 5},
        ))
    figure.update_xaxes(title="Acquired along-track x (ft)")
    figure.update_yaxes(title="Local TVD (ft; positive down)", autorange="reversed")
    figure.update_layout(height=380, legend={"orientation": "h"}, margin={"t": 35, "b": 40})
    return figure


def _log_figure(result, curve):
    figure = go.Figure()
    for side, color in (("left", "#b45309"), ("right", "#0f766e")):
        logs = [row for row in result["runs"][side]["logs"] if curve in row]
        figure.add_trace(go.Scatter(
            x=[row["md_ft"] for row in logs], y=[row[curve] for row in logs],
            mode="lines+markers", name=side.title(), line={"color": color}, marker={"size": 4},
        ))
    figure.update_xaxes(title="Acquisition MD (ft)")
    figure.update_yaxes(title="GR (API)" if curve == "GR" else "Resistivity (ohm·m)")
    figure.update_layout(height=290, legend={"orientation": "h"}, margin={"t": 30, "b": 40})
    return figure


def _command_table(result):
    rows = []
    for entry in result["differences"]["command_rows"]:
        row = {"Step": entry["step_index"]}
        for side in ("left", "right"):
            command = entry[side]
            if command is None:
                continue
            response = command.get("response") or {}
            row.update({
                "From MD (ft)": command["md_from_ft"], "To MD (ft)": command["md_to_ft"],
                f"{side.title()} action": command["action"],
                f"{side.title()} requested (°)": response.get("requested_inc_deg", command["target_inc_deg"]),
                f"{side.title()} applied (°)": response.get("effective_inc_deg"),
                f"{side.title()} clipped": response.get("clipped"),
            })
        rows.append(row)
    return pd.DataFrame(rows)


def _selection_context(root, available):
    """Consume navigation targets without overwriting manual picks on reruns."""
    by_id = {row["run_id"]: row for row in available}
    ids = list(by_id)
    target = st.session_state.pop("comparison_target", None)
    explicit = (
        isinstance(target, dict) and target.get("project_root")
        and Path(target["project_root"]).resolve() == root.resolve()
        and target.get("run_id") in by_id
    )
    preferred = target["run_id"] if explicit else selected_run_choice(st.session_state, root, ids, active_run_id(root))
    prefix = f"run_compare_{{}}_{root.resolve()}"
    left_key, right_key, consumed_key = (prefix.format(part) for part in ("left", "right", "context"))
    changed = st.session_state.get(consumed_key) != preferred
    invalid = st.session_state.get(left_key) not in ids or st.session_state.get(right_key) not in ids
    if explicit or changed or invalid:
        row = by_id[preferred]
        parent = row.get("parent_run_id")
        children = [item for item in available if item.get("parent_run_id") == preferred]
        if parent in by_id:
            left, right = parent, preferred
        elif children:
            left, right = preferred, children[0]["run_id"]
        else:
            left, right = preferred, next(run_id for run_id in ids if run_id != preferred)
        st.session_state[left_key] = left
        st.session_state[right_key] = right
    st.session_state[consumed_key] = preferred
    return left_key, right_key


def render(project_root: str | None) -> None:
    render_page_header(
        "Run Comparison", "Follow a fork family, compare recorded decisions, and evaluate completed branches on one scoring interval.",
        chips=["Acquired data only", "Shared experiment", "Right minus left"],
    )
    if not project_root:
        st.info("Open a project, then fork an unfinished steering run to compare alternative commands.")
        return
    root = Path(project_root)
    catalog = list_run_catalog(root)
    if not catalog:
        st.info("There are no saved runs. Start a run in Interpretation and Steering, then fork it before completion.")
        return
    st.markdown("#### Run families")
    table = [{
        "Run": row["label"], "Parent": (row.get("parent_run_id") or "Original")[:8],
        "Fork step": row.get("forked_at_step"), "Step": row.get("step_index"),
        "Acquired MD (ft)": row.get("revealed_md_ft"), "Status": row["status"],
    } for row in catalog]
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    available = [row for row in catalog if row["available"]]
    if len(available) < 2:
        st.info("Save a fork of an unfinished run to create a second branch. Earlier runs remain unchanged.")
        return
    labels = {row["run_id"]: row["label"] for row in available}
    ids = list(labels)
    left_key, right_key = _selection_context(root, available)
    left_column, right_column = st.columns(2)
    with left_column:
        left_id = st.selectbox("Left branch", ids, index=None, format_func=labels.get, key=left_key)
    with right_column:
        right_id = st.selectbox("Right branch", ids, index=None, format_func=labels.get, key=right_key)
    try:
        result = compare_runs(root, left_id, right_id)
    except (OSError, ValueError, KeyError) as exc:
        st.warning(f"These branches cannot be compared: {exc}")
        return
    interval, relationship = result["interval"], result["relationship"]
    st.markdown("#### One common acquired horizon")
    a, b, c = st.columns(3)
    a.metric("Common endpoint MD (ft)", f"{interval['end_md_ft']:,.0f}")
    b.metric("Compared lateral length (ft)", f"{interval['evaluated_length_ft']:,.0f}")
    c.metric("Shared prefix", f"Step {relationship['common_prefix_step']}")
    st.caption(f"MD {interval['start_md_ft']:,.0f}–{interval['end_md_ft']:,.0f} ft · branch alternatives begin after MD {interval['branch_start_md_ft']:,.0f} ft. Both paths and logs stop at the common recorded station; the denominator includes the shared prefix.")
    if result["runs"]["left"]["mode"] == "replay":
        st.info("Fixed-path replay: recommendations record interpretation and do not change the recorded trajectory.")
    st.plotly_chart(_path_figure(result), width="stretch")
    gr_column, res_column = st.columns(2)
    with gr_column:
        st.plotly_chart(_log_figure(result, "GR"), width="stretch")
    with res_column:
        st.plotly_chart(_log_figure(result, "RES"), width="stretch")
    st.markdown("#### Commands after the fork")
    commands = _command_table(result)
    if commands.empty:
        st.info("The branches share their entire acquired history so far. Advance both branches to review alternative commands.")
    else:
        st.dataframe(commands, hide_index=True, width="stretch")
        with st.expander("Recorded evidence behind these commands"):
            for row in result["differences"]["command_rows"]:
                st.markdown(f"**Step {row['step_index']}**")
                for side in ("left", "right"):
                    command = row[side]
                    if command:
                        st.write(f"{side.title()} · {command['action']}: {command['observations']}")
    st.markdown("#### Decision-time estimates")
    estimates = []
    for side, run in result["runs"].items():
        snapshot = run["estimated_snapshot"]
        if snapshot:
            estimates.append({"Branch": side.title(), "Estimated in target (%)": snapshot["percent_in_zone"], "Estimated center distance (ft)": snapshot["avg_center_distance"], "Lateral denominator (ft)": snapshot["evaluated_length_ft"], "Interpretation": snapshot["interpretation_version_id"][:8]})
        else:
            st.caption(f"{side.title()}: no persisted metric at this common endpoint; no later interpretation has been substituted.")
    if estimates:
        st.dataframe(pd.DataFrame(estimates), hide_index=True, width="stretch")
    st.caption("These are original persisted estimates from each branch. Interpretation revisions can differ after the fork; estimated placement is distinct from independent truth scoring.")
    st.markdown("#### Independent completed evaluation")
    if not result["both_complete"]:
        st.info("Complete both branches to unlock independent truth evaluation. Saved outcomes from a completed branch remain hidden while its comparison branch is unfinished.")
    if st.button("Evaluate completed branches", disabled=not result["both_complete"], type="primary"):
        try:
            result = compare_runs(root, left_id, right_id, evaluate=True)
        except (OSError, ValueError, KeyError) as exc:
            st.error(f"Independent evaluation unavailable: {exc}")
    if result["truth_evaluation"]:
        truth = result["truth_evaluation"]
        metrics = [{"Branch": side.title(), "True in target (%)": truth[side]["metrics"]["percent_in_zone"], "Lateral denominator (ft)": truth[side]["metrics"]["evaluated_length_ft"], "Mean center error (ft)": truth[side]["metrics"]["avg_center_distance_ft"], "DLS violations": truth[side]["metrics"]["dls_violation_count"]} for side in ("left", "right")]
        st.dataframe(pd.DataFrame(metrics), hide_index=True, width="stretch")
        st.metric("True placement difference · right minus left (pp)", f"{truth['differences']['percent_in_zone']:+.3f}")
    st.download_button(
        "Download acquired branch comparison", json.dumps(result, indent=2, allow_nan=False).encode("utf-8"),
        file_name=f"branch-comparison-{left_id[:8]}-{right_id[:8]}.json", mime="application/json", on_click="ignore",
    )
    with st.expander("Comparison contract"):
        for note in result["notes"]:
            st.write(note)
