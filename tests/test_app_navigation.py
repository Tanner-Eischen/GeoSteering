"""Exercise the real app shell in-process without browser access."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.io import create_project, load_project

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app():
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def _input(app, label):
    return next(field for field in app.text_input if field.label == label)


def _assert_page(app, group, page):
    assert not app.exception
    assert app.selectbox(key="sidebar_group").value == group
    assert app.radio(key="sidebar_page_choice").value == page
    assert app.session_state["sidebar_page"] == page


def test_grouped_navigation_persists_and_follows_cross_group_targets():
    app = _app()
    _assert_page(app, "Prepare data", "Dashboard")
    app.selectbox(key="sidebar_group").set_value("Interpret and steer").run()
    _assert_page(app, "Interpret and steer", "Correlation Panel")
    app.radio(key="sidebar_page_choice").set_value("Planning").run()
    _assert_page(app, "Interpret and steer", "Planning")
    app.run()
    _assert_page(app, "Interpret and steer", "Planning")
    app.session_state["nav_target"] = "Report Export"
    app.run()
    _assert_page(app, "Review and export", "Report Export")
    app.run()
    _assert_page(app, "Review and export", "Report Export")
    _button(app, "Import well data").click().run()
    _assert_page(app, "Prepare data", "Import Data")
    _button(app, "Open / create project").click().run()
    _assert_page(app, "Prepare data", "Project Workspace")


def test_loaded_project_renders_every_route_without_mutating_project(tmp_path):
    from tests.test_run_history import prepare_run

    root, _, _, _ = prepare_run(tmp_path)
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    app = _app()
    app.session_state["project_root"] = str(root)
    routes = {
        "Prepare data": ["Dashboard", "Project Workspace", "Import Data", "Data QC", "Well Viewer"],
        "Interpret and steer": ["Correlation Panel", "Planning", "Steering Console", "Uncertainty"],
        "Review and export": ["Decision Review", "Run Comparison", "Evaluation", "Report Export"],
        "Reference study": ["Robustness Study"],
    }
    for group, pages in routes.items():
        for page in pages:
            app.session_state["nav_target"] = page
            app.run(timeout=30)
            _assert_page(app, group, page)
    after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert before == after


def test_create_project_redirects_to_import_and_open_redirects_to_dashboard(tmp_path):
    created = tmp_path / "created"
    existing = tmp_path / "existing"
    create_project(existing, "Existing project")
    app = _app()
    _button(app, "Open / create project").click().run()
    next(radio for radio in app.radio if radio.label == "Project action").set_value("Create new").run()
    _input(app, "Project name").set_value("New project")
    _input(app, "New project folder").set_value(str(created))
    _button(app, "Create Project").click().run()
    _assert_page(app, "Prepare data", "Import Data")
    assert load_project(created).name == "New project"
    assert Path(app.session_state["project_root"]) == created.resolve()

    _button(app, "Open / create project").click().run()
    next(radio for radio in app.radio if radio.label == "Project action").set_value("Open existing").run()
    _input(app, "Project folder").set_value(f'"{existing}"')
    _button(app, "Open Project").click().run()
    _assert_page(app, "Prepare data", "Dashboard")
    assert Path(app.session_state["project_root"]) == existing.resolve()
    assert any("Existing project" in caption.value for caption in app.sidebar.caption)


def test_malformed_selected_project_can_recover_via_workspace(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "project.json").write_text("{malformed", encoding="utf-8")
    valid = tmp_path / "valid"
    create_project(valid, "Recovered project")
    app = _app()
    app.session_state["project_root"] = str(broken)
    app.session_state["nav_target"] = "Planning"
    app.run()
    _assert_page(app, "Interpret and steer", "Planning")
    assert any("Cannot open the selected project" in error.value for error in app.error)
    _button(app, "Open / create project").click().run()
    _assert_page(app, "Prepare data", "Project Workspace")
    _input(app, "Project folder").set_value(str(valid))
    _button(app, "Open Project").click().run()
    _assert_page(app, "Prepare data", "Dashboard")
    assert not app.error
    assert Path(app.session_state["project_root"]) == valid.resolve()


def test_invalid_open_keeps_current_project_and_empty_create_is_rejected(tmp_path):
    current = tmp_path / "current"
    create_project(current, "Current project")
    app = _app()
    app.session_state["project_root"] = str(current)
    _button(app, "Open / create project").click().run()
    _input(app, "Project folder").set_value(str(tmp_path / "missing"))
    _button(app, "Open Project").click().run()
    _assert_page(app, "Prepare data", "Project Workspace")
    assert any("Could not open project" in error.value for error in app.error)
    assert app.session_state["project_root"] == str(current)
    next(radio for radio in app.radio if radio.label == "Project action").set_value("Create new").run()
    _button(app, "Create Project").click().run()
    assert not app.exception
    assert any("Enter a project name" in error.value for error in app.error)
    assert app.session_state["project_root"] == str(current)
