from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from app.io.project_store import read_json
from app.services.project_data import load_project_and_wells
from app.ui.theme import render_page_header
from app.ui.workspace import activate_project


def _link(label: str, page: str, *, primary: bool = False) -> None:
    if st.button(label, type="primary" if primary else "secondary", use_container_width=True):
        st.session_state["nav_target"] = page
        st.rerun()


def _case_study_loader() -> None:
    st.caption("Four synthetic wells, offset picks and a replay ready at landing. Creates a separate project folder.")
    if st.button("Load Case Study in a new workspace", type="primary"):
        from tools.bootstrap_demo_project import bootstrap_demo_project
        workspace = Path("data") / "case_studies" / str(uuid4())
        try:
            with st.spinner("Preparing the four-well case study…"):
                bootstrap_demo_project(workspace, workspace.parent / f"{workspace.name}_inputs", steps=0)
        except (OSError, ValueError) as exc:
            st.error(f"Could not create the case study: {exc}")
            return
        activate_project(st.session_state, workspace.resolve())
        st.session_state["nav_target"] = "Data QC"
        st.rerun()


def render(project_root: str | None) -> None:
    render_page_header("Dashboard", "Prepare well data, build an interpretation, then steer and review a run.")
    if not project_root:
        with st.container(border=True):
            st.subheader("Start with your data")
            st.write("Open a saved project or create an empty project, then import your well folders.")
            _link("Open or create a project", "Project Workspace", primary=True)
        with st.container(border=True):
            st.subheader("Explore the example")
            _case_study_loader()
        return
    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Selected project root does not contain project.json.")
        _link("Choose a project", "Project Workspace")
        return
    project, wells = load_project_and_wells(root)
    valid_count = sum(w.qc_summary.get("valid") is True for w in wells)
    a, b = st.columns(2)
    a.metric("Imported wells", len(wells))
    b.metric("Wells passing QC", f"{valid_count} / {len(wells)}")
    if not wells:
        st.info("This project is empty. Import well folders to begin.")
        _link("Import well data", "Import Data", primary=True)
        return
    st.subheader("Project workflow")
    for column, title, description, actions in zip(
        st.columns(3),
        ["1 · Prepare data", "2 · Interpret and steer", "3 · Review and export"],
        ["Check imported wells, depth coverage and logs.",
         "Tie offset markers, save a plan and work through acquired observations.",
         "Revisit decisions, compare runs and export their evidence."],
        [[("Review Data QC", "Data QC"), ("Inspect Well Logs", "Well Viewer"), ("Import more wells", "Import Data")],
         [("Open Correlation", "Correlation Panel"), ("Open Planning", "Planning"), ("Open Steering", "Steering Console")],
         [("Decision Review", "Decision Review"), ("Run Comparison", "Run Comparison"), ("Evaluation", "Evaluation"), ("Report Export", "Report Export")]],
    ):
        with column, st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(description)
            for label, page in actions:
                _link(label, page)
    st.subheader("Imported wells")
    rows = []
    for well in wells:
        markers = read_json(root / well.markers_path, default=[]) if well.markers_path else []
        rows.append({
            "Well": well.name, "Role": "Active" if well.well_id == project.active_well_id else "Offset / available",
            "Curves": ", ".join(sorted(well.curve_inventory)), "Markers": len(markers),
            "QC": "Pass" if well.qc_summary.get("valid") else "Review",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with st.expander("Project location and reference studies"):
        st.code(str(root.resolve()), language=None)
        _case_study_loader()
        st.caption("Explore paired strategies under changed geology and imperfect sensors, including failure cases.")
        _link("Explore Robustness Study", "Robustness Study")
