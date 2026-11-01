from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from app.io.project_store import read_json
from app.services.project_data import load_project_and_wells
from app.ui.theme import render_page_header
from app.ui.workspace import activate_project


def render(project_root: str | None) -> None:
    render_page_header(
        "Dashboard",
        "Project readiness summary and quick quality signal before interpretation and steering.",
    )
    st.markdown("#### Geosteering under structural uncertainty")
    st.write("Three offsets constrain an initial regional model. Reveal active-well data, revise the interpretation, and evaluate against withheld geology after completion.")
    st.caption("Workflow: Scenario → QC → Correlation → Planning → Interpretation/steering → Evaluation → Report")
    if st.button("Load Case Study in a new workspace"):
        from tools.bootstrap_demo_project import bootstrap_demo_project
        workspace = Path("data") / "case_studies" / str(uuid4())
        try:
            bootstrap_demo_project(workspace, workspace.parent / f"{workspace.name}_inputs", steps=0)
        except (OSError, ValueError):
            st.error("The new case-study workspace could not be created. Check filesystem access and retry to create a fresh workspace.")
            return
        activate_project(st.session_state, workspace.resolve())
        st.session_state["nav_target"] = "Data QC"
        st.rerun()
    if not project_root:
        st.info("Create or open a project from the sidebar.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Selected project root does not contain project.json.")
        return

    project, wells = load_project_and_wells(root)
    rows = []
    valid_qc_count = 0
    for w in wells:
        qc = w.qc_summary or {}
        if qc.get("valid") is True:
            valid_qc_count += 1
        markers_count = 0
        if w.markers_path:
            markers_file = root / w.markers_path
            if markers_file.exists():
                markers_count = len(read_json(markers_file, default=[]))
        rows.append(
            {
                "well_name": w.name,
                "survey_loaded": bool(w.survey_path),
                "curves_present": ", ".join(sorted(w.curve_inventory.keys())),
                "markers_count": markers_count,
                "qc_valid": qc.get("valid", None),
            }
        )
    active_well_name = next((w.name for w in wells if w.well_id == project.active_well_id), "Not set")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Project", project.name)
    m2.metric("Wells", str(len(wells)))
    m3.metric("QC Valid", f"{valid_qc_count}/{len(wells)}")
    m4.metric("Active Well", active_well_name)

    st.markdown("#### Wells Summary")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### Workflow Shortcuts")
    c5, c6, c7, c8 = st.columns(4)
    if c5.button("Go to Data QC"):
        st.session_state["nav_target"] = "Data QC"
        st.rerun()
    if c6.button("Go to Correlation"):
        st.session_state["nav_target"] = "Correlation Panel"
        st.rerun()
    if c7.button("Go to Planning"):
        st.session_state["nav_target"] = "Planning"
        st.rerun()
    if c8.button("Go to Steering"):
        st.session_state["nav_target"] = "Steering Console"
        st.rerun()
