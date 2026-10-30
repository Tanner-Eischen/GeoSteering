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

    st.dataframe(pd.DataFrame(qc_rows), use_container_width=True, hide_index=True)
    st.caption("Depth basis: MD (ft). Vertical reference: TVD (ft).")

    c4, c5 = st.columns(2)
    if c4.button("Open Well Viewer"):
        st.session_state["nav_target"] = "Well Viewer"
        st.rerun()
    if c5.button("Open Correlation Panel"):
        st.session_state["nav_target"] = "Correlation Panel"
        st.rerun()
