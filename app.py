from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from app.io import import_well_folder
from app.io.project_store import create_project, load_project
from app.pages import (
    correlation_panel,
    dashboard,
    data_qc,
    decision_review,
    evaluation,
    planning,
    report_export,
    robustness,
    run_comparison,
    steering_console,
    uncertainty,
    well_viewer,
)
from app.ui.theme import apply_theme, render_page_header
from app.ui.workspace import activate_project

PAGES = {
    "Dashboard": dashboard.render,
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


def _sidebar_project_controls() -> str | None:
    st.caption("Open an existing project or create a clean demo workspace.")
    current_root = st.session_state.get("project_root", "")
    open_path = st.text_input("Open project root", value=current_root, key="open_project_root")
    create_path = st.text_input("Create project root", value=current_root, key="create_project_root")
    create_name = st.text_input("Create project name", value="GeoSteering Demo", key="create_project_name")

    if st.button("Open Project"):
        root = Path(open_path)
        if (root / "project.json").exists():
            activate_project(st.session_state, root)
            st.success(f"Opened {root}")
        else:
            st.error(f"project.json not found under {root}")

    if st.button("Create Project"):
        root = Path(create_path)
        try:
            project = create_project(root, create_name)
        except (OSError, ValueError) as exc:
            st.error(f"Could not create project: {exc}")
        else:
            activate_project(st.session_state, root)
            st.success(f"Created project {project.name}")

    return st.session_state.get("project_root")


def _sidebar_well_import_controls(project_root: str | None) -> None:
    if not project_root:
        return

    root = Path(project_root)
    if not (root / "project.json").exists():
        return

    st.caption("Import folders with survey.csv, logs.las, and optional markers.csv.")
    well_folder_input = st.text_area(
        "Well folder paths",
        key="import_well_folder",
        help="One path per line or separated by semicolons. Quoted paths are supported.",
        placeholder='C:\\data\\wells\\Well_A\nC:\\data\\wells\\Well_B',
    )
    well_name_input = st.text_area(
        "Well names (optional)",
        key="import_well_name",
        help="Optional. If provided, use one name per path in the same order.",
        placeholder="Well A\nWell B",
    )

    if not st.button("Import Well"):
        return

    if not well_folder_input.strip():
        st.error("Provide a well folder path.")
        return

    try:
        paths = _parse_well_paths(well_folder_input)
    except ValueError as exc:
        st.error(str(exc))
        return

    if not paths:
        st.error("Provide at least one well folder path.")
        return

    names = _parse_well_names(well_name_input)
    if names and len(names) not in (1, len(paths)):
        st.error("Provide either one name or one name per path.")
        return

    results = []
    errors = []
    for idx, well_folder in enumerate(paths):
        if not well_folder.exists():
            errors.append(f"Well folder not found: {well_folder}")
            continue

        if names:
            well_name = names[idx] if len(names) == len(paths) else names[0]
        else:
            well_name = well_folder.name

        if not well_name:
            errors.append(f"Missing well name for path: {well_folder}")
            continue

        try:
            result = import_well_folder(project_root=root, well_folder=well_folder, well_name=well_name)
            results.append(result)
        except Exception as exc:
            errors.append(f"Import failed for {well_folder}: {exc}")

    if results:
        st.success(f"Imported {len(results)} well(s).")
    if errors:
        st.error(" | ".join(errors))

    st.session_state["import_well_name"] = ""
    st.rerun()


def _parse_well_paths(raw: str) -> list[Path]:
    text = raw.strip()
    if not text:
        return []
    quoted = re.findall(r'"([^"]+)"', text)
    if quoted:
        parts = quoted
    else:
        parts = [p.strip() for p in re.split(r"[;\n]+", text) if p.strip()]
    return [Path(p).expanduser() for p in parts]


def _parse_well_names(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"[;\n,]+", text) if p.strip()]
    return parts


def _render_global_header(project_root: str | None) -> None:
    if not project_root:
        render_page_header(
            "GeoSteering Workbench",
            "Offline-first workflow for planning, correlation, steering simulation, and reporting.",
            chips=["No project loaded"],
        )
        return
    try:
        project = load_project(project_root)
        active_well = next((well.name for well in project.wells if well.well_id == project.active_well_id), "None")
        render_page_header(
            "GeoSteering Workbench",
            "Interpret geology. Review the next command. Evaluate the evidence.",
            chips=[f"Project: {project.name}", f"Active well: {active_well}"],
        )
    except Exception as exc:
        render_page_header(
            "GeoSteering Workbench",
            "Project root is set, but loading failed.",
            chips=[f"Error: {exc}"],
        )


def main() -> None:
    st.set_page_config(page_title="GeoSteering Workbench", layout="wide")
    apply_theme()

    st.sidebar.header("GeoSteering")
    if "nav_target" in st.session_state and st.session_state["nav_target"] in PAGES:
        st.session_state["sidebar_page"] = st.session_state.pop("nav_target")
    if "sidebar_page" not in st.session_state:
        st.session_state["sidebar_page"] = "Dashboard"
    page_name = st.sidebar.radio(
        "Page", options=list(PAGES), key="sidebar_page",
        help="Follow the project workflow or explore the published robustness study.",
    )
    st.sidebar.divider()
    with st.sidebar.expander("Project workspace", expanded=not bool(st.session_state.get("project_root"))):
        project_root = _sidebar_project_controls()
    if project_root:
        with st.sidebar.expander("Import well data", expanded=False):
            _sidebar_well_import_controls(project_root)
    st.sidebar.caption("Training and portfolio software · synthetic steering is not field validation.")
    _render_global_header(project_root)
    PAGES[page_name](project_root)


if __name__ == "__main__":
    main()
