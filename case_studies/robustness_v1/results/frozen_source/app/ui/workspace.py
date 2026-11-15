"""Project-session activation without carrying another project's derived state."""

from pathlib import Path


def activate_project(session, project_root):
    root = str(project_root)
    previous = session.get("project_root")
    changed = previous is None or Path(previous).resolve() != Path(root).resolve()
    if changed:
        for key in list(session):
            if key.startswith(("planning_", "corr_", "steering_run_", "report_", "_selected_run_context_")) or key in {
                "nav_target", "import_well_folder", "import_well_name",
            }:
                del session[key]
    session["project_root"] = root


def remember_selected_run(session, project_root, run_id):
    if run_id:
        session[f"_selected_run_context_{Path(project_root).resolve()}"] = run_id


def selected_run_choice(session, project_root, available, fallback):
    selected = session.get(f"_selected_run_context_{Path(project_root).resolve()}")
    if selected in available:
        return selected
    return fallback if fallback in available else available[0]
