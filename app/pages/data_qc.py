from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.services.project_data import load_project_and_wells
from app.ui.theme import render_page_header


def render(project_root: str | None) -> None:
    render_page_header(
        "Data QC",
        "Depth overlap, curve presence, and sampling checks for deterministic downstream behavior.",
    )
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    _, wells = load_project_and_wells(root)
    if not wells:
        st.info("No wells imported yet. Import well folders, then return here to check their data.")
        if st.button("Import well data", type="primary"):
            st.session_state["nav_target"] = "Import Data"
            st.rerun()
        return
    qc_rows = []
    warning_count = 0
    valid_count = 0
    for w in wells:
        qc = w.qc_summary or {}
        if qc.get("valid") is True:
            valid_count += 1
        warning_count += len(qc.get("warnings", []))
        qc_rows.append(
            {
                "well_name": w.name,
                "valid": qc.get("valid"),
                "md_min_ft": qc.get("md_min_ft"),
                "md_max_ft": qc.get("md_max_ft"),
                "survey_station_count": qc.get("survey_station_count"),
                "curves_present": ", ".join(qc.get("curves_present", [])),
                "sample_step_ft_est": qc.get("sample_step_ft_est"),
                "overlap_ratio": qc.get("overlap_ratio"),
                "warnings": "; ".join([x.get("message", "") for x in qc.get("warnings", [])]),
            }
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Wells Checked", str(len(wells)))
    c2.metric("Valid Wells", str(valid_count))
    c3.metric("Warnings", str(warning_count))

    frame = pd.DataFrame(qc_rows)
    st.dataframe(frame[["well_name", "valid", "md_min_ft", "md_max_ft", "curves_present"]],
                 use_container_width=True, hide_index=True, column_config={
                     "well_name": "Well", "valid": "QC passed", "md_min_ft": "Start MD (ft)",
                     "md_max_ft": "End MD (ft)", "curves_present": "Curves",
                 })
    st.caption("Depth basis: MD (ft). Vertical reference: TVD (ft).")
    st.subheader("Well details and warnings")
    by_id = {well.well_id: well for well in wells}
    selected = st.selectbox("Inspect well", list(by_id), format_func=lambda identifier: by_id[identifier].name)
    qc = by_id[selected].qc_summary or {}
    st.write(f"Survey stations: {qc.get('survey_station_count', '—')} · "
             f"Estimated sample spacing: {qc.get('sample_step_ft_est', '—')} ft · "
             f"Depth overlap ratio: {qc.get('overlap_ratio', '—')}")
    for warning in qc.get("warnings", []):
        st.warning(warning.get("message", "QC warning"))
    if not qc.get("warnings"):
        st.success("No import QC warnings recorded for this well.")
    st.download_button("Download full QC summary", frame.to_csv(index=False).encode("utf-8"),
                       file_name="well-qc.csv", mime="text/csv", on_click="ignore")

    c4, c5 = st.columns(2)
    if c4.button("Open Well Viewer"):
        st.session_state["nav_target"] = "Well Viewer"
        st.rerun()
    if c5.button("Open Correlation Panel"):
        st.session_state["nav_target"] = "Correlation Panel"
        st.rerun()
