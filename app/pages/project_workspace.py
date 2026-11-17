"""Full-width project setup, separated from day-to-day navigation."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.io.project_store import create_project, load_project
from app.ui.theme import render_page_header
from app.ui.workspace import activate_project


def _project_path(raw: str) -> Path:
    value = raw.strip().strip('"')
    if not value:
        raise ValueError("Enter a project folder path.")
    return Path(value).expanduser().resolve()


def render(project_root: str | None) -> None:
    render_page_header("Project Workspace", "Open a saved project or create an empty workspace, then import your wells.")
    if project_root:
        st.caption(f"Current project folder: {project_root}")
    action = st.radio("Project action", ["Open existing", "Create new"], horizontal=True)
    if action == "Open existing":
        st.write("Choose the folder containing project.json. Well data and saved work stay in this folder.")
        with st.form("workspace_open"):
            raw = st.text_input("Project folder", value=project_root or "", placeholder=r"C:\data\my-project")
            submitted = st.form_submit_button("Open Project", type="primary")
        if submitted:
            try:
                root = _project_path(raw)
                load_project(root)
            except (OSError, ValueError) as exc:
                st.error(f"Could not open project: {exc}")
            else:
                activate_project(st.session_state, root)
                st.session_state["nav_target"] = "Dashboard"
                st.rerun()
    else:
        st.write("Choose a new or empty folder. Existing projects will not be overwritten.")
        with st.form("workspace_create"):
            name = st.text_input("Project name", placeholder="My geosteering project")
            raw = st.text_input("New project folder", placeholder=r"C:\data\my-new-project")
            submitted = st.form_submit_button("Create Project", type="primary")
        if submitted:
            try:
                if not name.strip():
                    raise ValueError("Enter a project name.")
                root = _project_path(raw)
                create_project(root, name.strip())
            except (OSError, ValueError) as exc:
                st.error(f"Could not create project: {exc}")
            else:
                activate_project(st.session_state, root)
                st.session_state["nav_target"] = "Import Data"
                st.rerun()
    st.divider()
    st.caption("Trying the workbench? Dashboard can load the bundled four-well case study in a separate workspace.")
    if st.button("Go to Dashboard"):
        st.session_state["nav_target"] = "Dashboard"
        st.rerun()
