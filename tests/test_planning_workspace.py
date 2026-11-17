"""Local Streamlit execution checks for preview/edit/save handoffs; no browser."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.io.project_store import create_project, load_project, read_json
from app.io.well_import import import_well_folder
from app.services.prejob import save_prejob_model
from tools.generate_sample_data import generate_sample_data


def workspace(root):
    return AppTest.from_string(
        f"from app.pages.planning import render\nrender({str(root)!r})",
        default_timeout=30,
    ).run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


@pytest.mark.parametrize("key,value", [
    ("planning_input_kickoff", 600.0),
    ("planning_input_landing", 2500.0),
    ("planning_input_length", 4000.0),
    ("planning_input_azimuth", 80.0),
    ("planning_input_spacing", 50.0),
    ("planning_input_dls", 7.0),
])
def test_any_geometry_edit_refreshes_preview_without_saving(tmp_path, key, value):
    root = tmp_path / "project"
    create_project(root, "Planning")
    app = workspace(root)
    assert not app.exception
    assert not button(app, "Save Plan").disabled
    assert len(app.get("download_button")) == 1
    app.number_input(key=key).set_value(value).run()
    assert not app.exception
    parameter = {
        "planning_input_kickoff": "kickoff_md_ft",
        "planning_input_landing": "landing_md_ft",
        "planning_input_length": "lateral_length_ft",
        "planning_input_azimuth": "planned_azi_deg",
        "planning_input_spacing": "step_ft",
    }.get(key)
    if parameter:
        assert app.session_state["planning_preview_params"][parameter] == value
    else:
        assert app.session_state["planning_preview_max_dls"] == value
    assert len(app.get("download_button")) == 1
    assert not any(item.label == "Generate Preview" for item in app.button)
    assert not list((root / "plans").glob("*.json"))


def test_invalid_geometry_clears_preview_and_correction_recovers_automatically(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Planning")
    app = workspace(root)
    app.number_input(key="planning_input_landing").set_value(100.0).run()
    assert not app.exception
    assert app.error
    assert not any(item.label == "Save Plan" for item in app.button)
    assert not app.get("download_button")
    assert not app.get("plotly_chart")
    app.number_input(key="planning_input_landing").set_value(2000.0).run()
    assert not app.exception
    assert not app.error
    assert not button(app, "Save Plan").disabled
    assert len(app.get("download_button")) == 1
    assert len(app.get("plotly_chart")) == 2
    assert not list((root / "plans").glob("*.json"))


def test_save_is_persistent_and_does_not_duplicate_on_rerun(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Planning")
    app = workspace(root)
    assert button(app, "Continue to Steering").disabled
    button(app, "Save Plan").click().run()
    assert not app.exception
    assert len(list((root / "plans").glob("*.json"))) == 1
    assert button(app, "Save Plan").disabled
    assert not button(app, "Continue to Steering").disabled
    app.run()
    assert len(list((root / "plans").glob("*.json"))) == 1
    assert any("Saved Plan A" in item.value for item in app.success)
    app.text_input(key="planning_input_name").set_value("Renamed").run()
    assert not app.exception
    assert not button(app, "Save Plan").disabled
    assert button(app, "Continue to Steering").disabled
    assert app.session_state["planning_preview_name"] == "Renamed"
    assert len(app.get("download_button")) == 1
    assert len(list((root / "plans").glob("*.json"))) == 1


def test_solved_preview_pins_model_and_ignores_disabled_prescribed_fields(tmp_path):
    sample = tmp_path / "sample"
    generate_sample_data(sample, seed=123)
    root = tmp_path / "project"
    create_project(root, "Planning")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(root, sample / "wells" / name, name)
    project = load_project(root)
    model = save_prejob_model(root, [well.well_id for well in project.wells if well.well_id != project.active_well_id])
    app = workspace(root)
    assert app.checkbox(key="planning_input_solve").value
    assert app.number_input(key="planning_input_azimuth").disabled
    assert app.number_input(key="planning_input_landing").disabled
    assert not app.exception
    assert not app.error
    button(app, "Save Plan").click().run()
    assert not app.exception
    saved = read_json(next((Path(root) / "plans").glob("*.json")))
    assert saved["geological_model"]["model_sha256"] == model.model_sha256
    assert saved["parameters"]["planned_azi_deg"] == 90


def test_exceedances_block_save_but_leave_preview_download_available(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Planning")
    app = workspace(root)
    app.number_input(key="planning_input_landing").set_value(600.0).run()
    assert not app.exception
    assert button(app, "Save Plan").disabled
    assert button(app, "Continue to Steering").disabled
    assert len(app.get("download_button")) == 1
    assert any("exceeds its DLS limit" in item.value for item in app.warning)
