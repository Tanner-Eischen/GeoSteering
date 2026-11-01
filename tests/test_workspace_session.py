from pathlib import Path

from app.ui.workspace import activate_project, remember_selected_run, selected_run_choice


def test_switching_projects_discards_derived_controls_and_preview(tmp_path):
    session = {
        "project_root": str(tmp_path / "first"), "planning_preview_stations": "old stations",
        "planning_preview_root": str(tmp_path / "first"), "corr_depth_max": 1800,
        "report_target": {"run_id": "old"}, "steering_run_old": "old",
        "import_well_folder": "old import", "sidebar_page": "Planning",
    }
    activate_project(session, tmp_path / "second")
    assert session == {"project_root": str(tmp_path / "second"), "sidebar_page": "Planning"}


def test_reopening_same_canonical_project_preserves_its_session(tmp_path):
    root = tmp_path / "first"
    session = {"project_root": str(root), "planning_preview_stations": "same project"}
    activate_project(session, root / ".." / "first")
    assert session["planning_preview_stations"] == "same project"
    assert Path(session["project_root"]).resolve() == root.resolve()


def test_initial_activation_clears_orphaned_context_without_erasing_navigation():
    session = {"planning_preview_stations": "orphan", "nav_target": "Report Export", "sidebar_page": "Dashboard"}
    activate_project(session, "new-project")
    assert session == {"project_root": "new-project", "sidebar_page": "Dashboard"}


def test_non_widget_run_selection_survives_page_widget_cleanup(tmp_path):
    session = {}
    activate_project(session, tmp_path / "project")
    remember_selected_run(session, tmp_path / "project", "older-selected")
    session["steering_run_widget"] = "older-selected"
    del session["steering_run_widget"]
    assert selected_run_choice(session, tmp_path / "project", ["new-active", "older-selected"], "new-active") == "older-selected"
    remember_selected_run(session, tmp_path / "project", "new-active")
    assert selected_run_choice(session, tmp_path / "project", ["new-active", "older-selected"], "older-selected") == "new-active"


def test_run_choice_is_scoped_and_cleared_on_project_activation(tmp_path):
    session = {}
    activate_project(session, tmp_path / "first")
    remember_selected_run(session, tmp_path / "first", "first-run")
    assert selected_run_choice(session, tmp_path / "second", ["second-run"], "second-run") == "second-run"
    activate_project(session, tmp_path / "second")
    assert not any(key.startswith("_selected_run_context_") for key in session)
