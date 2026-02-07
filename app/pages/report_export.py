from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.report.report_builder import build_report
from app.services.project_data import load_project_and_wells


def render(project_root: str | None) -> None:
    st.subheader("Report Export")
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    _, wells = load_project_and_wells(root)
    well_names = [w.name for w in wells]
    st.multiselect("Include wells", options=well_names, default=well_names, key="report_include_wells")
    st.multiselect("Include step snapshots", options=["latest"], default=["latest"], key="report_include_steps")

    st.markdown("### Included sections")
    st.write("1. Cover page")
    st.write("2. Data summary and QC")
    st.write("3. Correlation and markers")
    st.write("4. Pre-spud plan and DLS")
    st.write("5. Steering decisions and KPI results")
    st.write("6. Final interpretation")
    st.write("7. Assumptions and limitations")

    if st.button("Export Report"):
        out = build_report(root)
        st.success(f"Report exported: {out}")
        st.code(str(out))
