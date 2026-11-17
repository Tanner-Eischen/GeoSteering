from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from app.io import import_well_folder, load_project
from app.services.import_preview import check_import_folders, parse_well_paths
from app.services.upload_import import UPLOAD_FILES, collect_uploads, import_uploaded_well, upload_signature
from app.ui.theme import render_page_header


def render(project_root: str | None) -> None:
    render_page_header("Import Data", "Choose well files or folders, review their names and contents, then import into this project.")
    if not project_root:
        st.info("Open or create a project in Project Workspace, then add your well folders here.")
        if st.button("Open Project Workspace", type="primary"):
            st.session_state["nav_target"] = "Project Workspace"
            st.rerun()
        return
    root = Path(project_root)
    try:
        project = load_project(root)
    except (OSError, ValueError) as exc:
        st.error(f"Could not open the project: {exc}")
        return
    scope = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]
    preview_key = f"import_preview_{scope}"
    results_key = f"import_results_{scope}"

    method = st.radio("Import method", ["Folder paths", "Upload files"], horizontal=True, key="import_method")
    if method == "Upload files":
        _render_upload(root, project, scope, results_key)
        return

    st.subheader("1. Choose well folders")
    st.caption(f"Destination: {project.name} · {root}")
    st.markdown(
        "Each folder needs **survey.csv** and **logs.las**. Add **markers.csv** for formation picks "
        "and **reference.json** for spatial interpretation. Paths refer to the computer running this app."
    )
    with st.expander("File formats and coordinates"):
        st.markdown(
            "- Survey columns: `md_ft`, `inc_deg`, `azi_deg`, with increasing measured depth.\n"
            "- LAS curves: gamma ray and resistivity, normalized to `GR` and `RES`.\n"
            "- Optional marker columns: `marker_name`, `md_ft`, `color`, `notes`.\n"
            "- Spatial work requires an explicit `reference.json`; a folder without it remains MD-only.\n\n"
            "Import validates data and depth overlap before adding each well. Source files are left unchanged."
        )
    raw = st.text_area(
        "Well folder paths", key="import_well_folder", height=110,
        placeholder='C:\\data\\wells\\Well_A\nC:\\data\\wells\\Well_B',
        help="One folder per line, or separate folders with semicolons. Double quotes around paths are optional.",
    )
    if st.button("Review folders", type="primary"):
        try:
            paths = parse_well_paths(raw)
            if not paths:
                raise ValueError("Enter at least one well folder path.")
        except ValueError as exc:
            st.error(str(exc))
            st.session_state.pop(preview_key, None)
        else:
            st.session_state[preview_key] = {"input": raw, "paths": [str(path) for path in paths]}

    preview = st.session_state.get(preview_key)
    if preview:
        st.subheader("2. Review files and well names")
        paths = [Path(path) for path in preview["paths"]]
        names = []
        for index, path in enumerate(paths):
            identity = hashlib.sha256(str(path).encode()).hexdigest()[:12]
            names.append(st.text_input(
                f"Well name · folder {index + 1}", value=path.name,
                key=f"import_name_{scope}_{index}_{identity}", help=str(path),
            ))
        rows = check_import_folders(paths, names, [well.name for well in project.wells])
        st.dataframe(
            [{key: value for key, value in row.items() if key != "ready"} for row in rows],
            use_container_width=True, hide_index=True,
        )
        changed = raw != preview["input"]
        ready = all(row["ready"] for row in rows)
        if changed:
            st.warning("Folder paths changed. Select Review folders again before importing.")
        if not ready:
            for row in rows:
                if not row["ready"]:
                    st.warning(f"{row['Well'] or row['Folder']}: {row['File check']}")
        if any(row["Spatial reference"].startswith("Missing") for row in rows):
            st.info("Folders without reference.json can be inspected by measured depth but cannot support spatial interpretation.")
        st.caption("These are file-presence checks. Import runs the full survey, log, marker and QC validation.")
        st.subheader("3. Import and review results")
        if st.button(f"Import {len(paths)} well(s)", type="primary", disabled=changed or not ready):
            results = []
            with st.spinner("Validating and importing well data…"):
                for path, name in zip(paths, names, strict=True):
                    try:
                        result = import_well_folder(root, path, name.strip())
                    except Exception as exc:
                        results.append({"Well": name.strip(), "Folder": str(path), "Status": "Failed", "Details": str(exc)})
                    else:
                        results.append({
                            "Well": name.strip(), "Folder": str(path), "Status": "Imported",
                            "Details": f"{result['survey_rows']} survey stations · {result['log_rows']} log rows · {result['markers_loaded']} markers",
                        })
            st.session_state[results_key] = results

    _render_results(results_key)


def _render_upload(root, project, scope: str, results_key: str) -> None:
    st.subheader("1. Choose files for one well")
    st.caption(f"Destination: {project.name}")
    st.markdown(
        "Upload **one well at a time**. Select **survey.csv** and **logs.las**, plus optional "
        "**markers.csv** and **reference.json**. Keep these filenames so the app can identify each file."
    )
    uploads = st.file_uploader(
        "Well files", type=["csv", "las", "json"], accept_multiple_files=True,
        key=f"import_upload_files_{scope}", help="Select or drag all files for a single well into this area.",
    )
    name = st.text_input("Well name", key=f"import_upload_name_{scope}", placeholder="e.g. Offset Well A").strip()
    files = {}
    issue = None
    try:
        files = collect_uploads([(upload.name, upload.getvalue()) for upload in uploads])
    except ValueError as exc:
        issue = str(exc)
    st.subheader("2. Review selected files")
    st.dataframe([
        {"File": filename, "Needed": "Required" if required else "Optional",
         "Status": "Selected" if filename in files else "Missing" if required else "Optional"}
        for filename, required in UPLOAD_FILES.items()
    ], use_container_width=True, hide_index=True)
    missing = [filename for filename, required in UPLOAD_FILES.items() if required and filename not in files]
    if files and "reference.json" not in files:
        st.info("Without reference.json this well can be inspected by measured depth but cannot support spatial interpretation.")
    if missing and uploads and not issue:
        issue = f"Add the required files: {', '.join(missing)}."
    if name and any(well.name.casefold() == name.casefold() for well in project.wells):
        issue = "This well name already exists in the project. Choose a unique name."
    signature = upload_signature(files)
    signatures_key = f"import_upload_signatures_{scope}"
    imported = st.session_state.get(signatures_key, [])
    if files and signature in imported:
        issue = "These files were already imported in this session. Select files for another well to continue."
    if issue:
        st.warning(issue)
    st.caption("Import validates survey, log, marker and coordinate contents before adding the well. Source files are left unchanged.")
    if st.button("Import uploaded well", type="primary", disabled=bool(issue or missing or not name)):
        with st.spinner("Validating and importing well data…"):
            try:
                result = import_uploaded_well(root, files, name)
            except Exception as exc:
                outcome = {"Well": name, "Source": "Uploaded files", "Status": "Failed", "Details": str(exc)}
            else:
                outcome = {
                    "Well": name, "Source": "Uploaded files", "Status": "Imported",
                    "Details": f"{result['survey_rows']} survey stations · {result['log_rows']} log rows · {result['markers_loaded']} markers",
                }
                st.session_state[signatures_key] = [*imported, signature]
            st.session_state[results_key] = [outcome]
    _render_results(results_key)


def _render_results(results_key: str) -> None:
    results = st.session_state.get(results_key, [])
    if results:
        st.subheader("Latest import results")
        succeeded = sum(row["Status"] == "Imported" for row in results)
        if succeeded:
            st.success(f"Imported {succeeded} of {len(results)} wells. Review Data QC before correlation or planning.")
        for row in results:
            if row["Status"] == "Failed":
                st.error(f"{row['Well']}: {row['Details']}")
        if len(results) > 1:
            st.dataframe(results, use_container_width=True, hide_index=True)
        for row in results:
            with st.expander(f"{row['Well']} · {row['Status']}", expanded=len(results) == 1):
                st.write(row["Details"])
                st.caption(row.get("Folder", row.get("Source", "")))
        if succeeded < len(results):
            st.caption("Successful wells remain saved. Correct failed inputs and retry only those wells.")
        left, right = st.columns(2)
        if left.button("Review Data QC", use_container_width=True):
            st.session_state["nav_target"] = "Data QC"
            st.rerun()
        if right.button("Inspect Well Logs", use_container_width=True):
            st.session_state["nav_target"] = "Well Viewer"
            st.rerun()
