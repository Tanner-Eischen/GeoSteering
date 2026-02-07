from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.io.project_store import create_project, load_project
from app.pages import correlation_panel, dashboard, data_qc, planning, report_export, steering_console, well_viewer


PAGES = {
    "Dashboard": dashboard.render,
    "Data QC": data_qc.render,
    "Well Viewer": well_viewer.render,
    "Correlation Panel": correlation_panel.render,
    "Planning": planning.render,
    "Steering Console": steering_console.render,
    "Report Export": report_export.render,
}


def _sidebar_project_controls() -> str | None:
    st.sidebar.header("Project")
    current_root = st.session_state.get("project_root", "")
    open_path = st.sidebar.text_input("Open project root", value=current_root, key="open_project_root")
    create_path = st.sidebar.text_input("Create project root", value=current_root, key="create_project_root")
    create_name = st.sidebar.text_input("Create project name", value="GeoSteering Demo", key="create_project_name")

    if st.sidebar.button("Open Project"):
        root = Path(open_path)
        if (root / "project.json").exists():
            st.session_state["project_root"] = str(root)
            st.sidebar.success(f"Opened {root}")
        else:
            st.sidebar.error(f"project.json not found under {root}")

    if st.sidebar.button("Create Project"):
        root = Path(create_path)
        project = create_project(root, create_name)
        st.session_state["project_root"] = str(root)
        st.sidebar.success(f"Created project {project.name}")

    return st.session_state.get("project_root")


def _render_global_header(project_root: str | None) -> None:
    if not project_root:
        st.title("Geosteering Workbench MVP")
        st.caption("No project loaded.")
        return
    try:
        project = load_project(project_root)
        active_well = project.active_well_id or "None"
        st.title("Geosteering Workbench MVP")
        st.caption(f"Project: {project.name} | Root: {project_root} | Active well: {active_well}")
    except Exception as exc:
        st.title("Geosteering Workbench MVP")
        st.caption(f"Project root set, but load failed: {exc}")


def main() -> None:
    st.set_page_config(page_title="Geosteering Workbench MVP", layout="wide")

    project_root = _sidebar_project_controls()

    st.sidebar.markdown("---")
    st.sidebar.warning("Training and portfolio tool. Not validated for live operations.")
    st.sidebar.caption("No WITSML ingestion in MVP. No guarantees about well safety or operational compliance.")

    page_name = st.sidebar.radio("Page", options=list(PAGES.keys()), index=0)
    _render_global_header(project_root)
    PAGES[page_name](project_root)


if __name__ == "__main__":
    main()

