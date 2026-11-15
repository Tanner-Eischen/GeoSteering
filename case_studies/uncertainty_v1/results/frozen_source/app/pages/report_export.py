from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.io.project_store import read_json
from app.services.operator_workflow import export_selected_report, run_label
from app.services.project_data import load_project_and_wells
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import active_run_id, run_root
from app.ui.theme import render_page_header
from app.ui.workspace import remember_selected_run, selected_run_choice


def render(project_root: str | None) -> None:
    render_page_header(
        "Report Export",
        "Compile a reproducible PDF artifact with planning, correlation, steering, KPI, and assumptions sections.",
    )
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    _, wells = load_project_and_wells(root)
    well_names = [w.name for w in wells]
    run_ids = sorted(p.name for p in (root / "runs").glob("*") if p.is_dir())
    run_selection_key = f"report_run_{root.resolve()}"
    target = st.session_state.pop("report_target", None)
    if target and target.get("project_root") == str(root.resolve()) and target.get("run_id") in run_ids:
        remember_selected_run(st.session_state, root, target["run_id"])
    selected_run = active_run_id(root)
    if run_ids:
        st.session_state[run_selection_key] = selected_run_choice(st.session_state, root, run_ids, selected_run)
        selected_run = st.selectbox("Run", run_ids, index=None,
                                    format_func=lambda identifier: run_label(root, identifier),
                                    key=run_selection_key,
                                    on_change=lambda: remember_selected_run(st.session_state, root, st.session_state.get(run_selection_key)))
        remember_selected_run(st.session_state, root, selected_run)
    else:
        st.info("Initialize a saved run before exporting from this page. Legacy CLI export remains available.")
        return
    selection_key = f"report_{root.resolve()}_{selected_run}"
    plans = [read_json(p) for p in (root / "plans").glob("*.json")]
    plans = sorted(plans, key=lambda p: p["created_at"])
    selected_plan = None
    if plans:
        by_id = {p["plan_id"]: p for p in plans}
        scope = run_root(root, selected_run)
        config = read_json(scope / "simulations" / "simulation_config.json", default={})
        pinned = config.get("plan_id")
        selected_plan = st.selectbox(
            "Plan",
            [None, *by_id],
            index=[None, *by_id].index(pinned) if pinned in by_id else 0,
            format_func=lambda key: "Preserve run's plan selection" if key is None else f"{by_id[key]['name']} ({key})",
            key=f"{selection_key}_plan",
        )
    steps = [m["step_index"] for m in load_run_metrics(root, run_id=selected_run)] if selected_run else []
    c1, c2 = st.columns(2)
    included_wells = c1.multiselect("Include wells", options=well_names, default=well_names, key=f"{selection_key}_wells")
    included_steps = c2.multiselect("Include step snapshots", options=steps, default=steps, key=f"{selection_key}_steps")

    st.markdown("#### Included sections")
    st.write("1. Cover page")
    st.write("2. Data summary and QC")
    st.write("3. Correlation and markers")
    st.write("4. Pre-spud plan and DLS")
    st.write("5. Steering decisions and KPI results")
    st.write("6. Final interpretation")
    st.write("7. Assumptions and limitations")

    c3, c4 = st.columns(2)
    if c3.button("Export Report"):
        try:
            out = export_selected_report(
                root, run_id=selected_run, plan_id=selected_plan, include_wells=included_wells, include_steps=included_steps
            )
        except (FileNotFoundError, ValueError) as exc:
            st.error(str(exc))
            return
        st.success(f"Report exported: {out}")
        st.download_button("Download selected report", data=out.read_bytes(), file_name=out.name,
                           mime="application/pdf", on_click="ignore")
        st.caption("This download contains exactly the selected exported run/plan and filters. Change the selection and export again for a new artifact.")
    if c4.button("Back to Steering"):
        st.session_state["nav_target"] = "Steering Console"
        st.rerun()
