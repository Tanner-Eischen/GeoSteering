from __future__ import annotations

from html import escape

import streamlit as st

from app.io.project_store import load_project
from app.pages import (
    correlation_panel,
    dashboard,
    data_import,
    data_qc,
    decision_review,
    evaluation,
    planning,
    project_workspace,
    report_export,
    robustness,
    run_comparison,
    steering_console,
    uncertainty,
    well_viewer,
)
from app.ui.navigation import reset_scroll_on_navigation
from app.ui.theme import apply_theme

PAGES = {
    "Dashboard": dashboard.render,
    "Project Workspace": project_workspace.render,
    "Import Data": data_import.render,
    "Data QC": data_qc.render,
    "Well Viewer": well_viewer.render,
    "Correlation Panel": correlation_panel.render,
    "Planning": planning.render,
    "Steering Console": steering_console.render,
    "Uncertainty": uncertainty.render,
    "Decision Review": decision_review.render,
    "Run Comparison": run_comparison.render,
    "Evaluation": evaluation.render,
    "Report Export": report_export.render,
    "Robustness Study": robustness.render,
}

PAGE_GROUPS = {
    "Prepare data": ["Dashboard", "Project Workspace", "Import Data", "Data QC", "Well Viewer"],
    "Interpret and steer": ["Correlation Panel", "Planning", "Steering Console", "Uncertainty"],
    "Review and export": ["Decision Review", "Run Comparison", "Evaluation", "Report Export"],
    "Reference study": ["Robustness Study"],
}


def _navigate(page: str) -> None:
    st.session_state["nav_target"] = page


def _remember_page() -> None:
    st.session_state["sidebar_page"] = st.session_state["sidebar_page_choice"]


def _render_navigation() -> str:
    target = st.session_state.pop("nav_target", None)
    current = target if target in PAGES else st.session_state.get("sidebar_page", "Dashboard")
    if current not in PAGES:
        current = "Dashboard"
    current_group = next(group for group, pages in PAGE_GROUPS.items() if current in pages)
    if target in PAGES or "sidebar_group" not in st.session_state:
        st.session_state["sidebar_group"] = current_group
    group = st.sidebar.selectbox("Workflow", list(PAGE_GROUPS), key="sidebar_group")
    pages = PAGE_GROUPS[group]
    if current not in pages:
        current = pages[0]
    st.session_state["sidebar_page_choice"] = current
    page = st.sidebar.radio("Page", pages, key="sidebar_page_choice", on_change=_remember_page)
    st.session_state["sidebar_page"] = page
    return page


def main() -> None:
    st.set_page_config(page_title="GeoSteering Workbench", layout="wide")
    apply_theme()
    st.sidebar.title("GeoSteering")
    root = st.session_state.get("project_root")
    project = None
    project_error = None
    if root:
        try:
            project = load_project(root)
        except (OSError, ValueError) as exc:
            project_error = str(exc)
    st.sidebar.caption(project.name if project else "No project open")
    st.sidebar.button("Open / create project", on_click=_navigate, args=("Project Workspace",), use_container_width=True)
    st.sidebar.button("Import well data", on_click=_navigate, args=("Import Data",), use_container_width=True)
    st.sidebar.divider()
    page = _render_navigation()
    st.sidebar.caption("Prepare data → interpret and steer → review and export")
    st.sidebar.divider()
    st.sidebar.caption("Training software · synthetic results are not field validation.")
    if project:
        active = next((well.name for well in project.wells if well.well_id == project.active_well_id), "Not selected")
        st.markdown(
            f'<div class="gs-project-context"><strong>{escape(project.name)}</strong>'
            f' · Active well: {escape(active)} · {len(project.wells)} wells</div>',
            unsafe_allow_html=True,
        )
    if project_error:
        st.error(f"Cannot open the selected project: {project_error}")
        st.caption("Use Open / create project to select a valid project folder.")
        root = None
    PAGES[page](root)
    reset_scroll_on_navigation(page, root)


if __name__ == "__main__":
    main()
