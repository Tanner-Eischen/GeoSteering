from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.services.project_data import load_project_and_wells


def render(project_root: str | None) -> None:
    st.subheader("Data QC")
    if not project_root:
        st.info("Open a project first.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Project not found at selected path.")
        return

    _, wells = load_project_and_wells(root)
    qc_rows = []
    for w in wells:
        qc = w.qc_summary or {}
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

    st.dataframe(pd.DataFrame(qc_rows), use_container_width=True)
    st.caption("Depth basis: MD (ft). Vertical reference: TVD (ft).")

