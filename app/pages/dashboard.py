from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.io.project_store import read_json
from app.services.project_data import load_project_and_wells


def render(project_root: str | None) -> None:
    st.subheader("Dashboard")
    if not project_root:
        st.info("Create or open a project from the sidebar.")
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        st.warning("Selected project root does not contain project.json.")
        return

    project, wells = load_project_and_wells(root)
    rows = []
    for w in wells:
        qc = w.qc_summary or {}
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
    st.write(f"Project: **{project.name}**")
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
