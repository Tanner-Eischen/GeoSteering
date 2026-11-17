"""Local execution checks for linked marker editing and correlation charts."""

from __future__ import annotations

import base64
import json

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from app.io.project_store import create_project, load_project
from app.io.well_import import import_well_folder
from app.services.markers import add_marker, load_markers
from app.services.prejob import list_prejob_models
from tests.test_run_history import prepare_run
from tools.generate_sample_data import generate_sample_data


@pytest.fixture
def project(tmp_path):
    sample = tmp_path / "sample"
    generate_sample_data(sample, seed=123)
    root = tmp_path / "project"
    create_project(root, "Compact correlation")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(root, sample / "wells" / name, name)
    return root, {well.name: well.well_id for well in load_project(root).wells}


def page(root):
    return AppTest.from_string(
        f"from app.pages.correlation_panel import render\nrender({str(root)!r})", default_timeout=30,
    ).run()


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def figure(app):
    return json.loads(app.get("plotly_chart")[0].proto.spec)


def overlay_depths(app, color):
    return [shape["y0"] for shape in figure(app)["layout"].get("shapes", [])
            if shape.get("line", {}).get("color") == color]


def values(encoded):
    if isinstance(encoded, dict) and "bdata" in encoded:
        return np.frombuffer(base64.b64decode(encoded["bdata"]), dtype=encoded["dtype"])
    return np.asarray(encoded)


def test_draft_previews_without_writing_and_update_moves_overlay_without_resetting_zoom(project):
    root, ids = project
    well_id = ids["offset_01"]
    selected = add_marker(root, well_id, "Editable pick", 1500.0)
    app = page(root)
    widget(app, "selectbox", "Select marker").set_value(selected.marker_id).run()
    assert not app.exception
    before = load_markers(root, well_id)
    revision = figure(app)["layout"]["uirevision"]
    assert overlay_depths(app, "#0f766e") == [1500.0]
    widget(app, "number_input", "Edit MD (ft)").set_value(1525.0).run()
    assert not app.exception
    assert load_markers(root, well_id) == before
    assert overlay_depths(app, "#b45309") == [1525.0]
    assert overlay_depths(app, "#0f766e") == [1500.0]
    assert any(annotation["text"] == "Unsaved depth" for annotation in figure(app)["layout"]["annotations"])
    assert figure(app)["layout"]["uirevision"] == revision
    widget(app, "button", "Update Marker").click().run()
    assert not app.exception
    saved = next(marker for marker in load_markers(root, well_id) if marker.marker_id == selected.marker_id)
    assert saved.md_ft == 1525.0
    assert overlay_depths(app, "#0f766e") == [1525.0]
    assert not overlay_depths(app, "#b45309")
    assert figure(app)["layout"]["uirevision"] == revision
    widget(app, "button", "Reset view").click().run()
    assert figure(app)["layout"]["uirevision"] != revision


def test_marker_well_and_chart_group_follow_each_other_without_changing_evidence(project):
    root, ids = project
    app = page(root)
    selected = ["offset_01", "offset_02", "offset_03"]
    assert widget(app, "multiselect", "Wells").value == selected
    widget(app, "selectbox", "Marker well").set_value("offset_03").run()
    assert not app.exception
    assert widget(app, "selectbox", "Visible well group").value == 2
    assert figure(app)["layout"]["annotations"][0]["text"] == "offset_03"
    assert widget(app, "multiselect", "Wells").value == selected
    widget(app, "selectbox", "Visible well group").set_value(0).run()
    assert not app.exception
    assert widget(app, "selectbox", "Marker well").value == "offset_01"
    assert figure(app)["layout"]["annotations"][0]["text"] == "offset_01"
    widget(app, "selectbox", "Wells per chart").set_value(2).run()
    widget(app, "selectbox", "Marker well").set_value("offset_03").run()
    assert not app.exception
    assert widget(app, "selectbox", "Visible well group").value == 1
    assert figure(app)["layout"]["annotations"][0]["text"] == "offset_03"
    assert widget(app, "multiselect", "Wells").value == selected
    widget(app, "button", "Save pre-job interpretation from selected offset picks").click().run()
    assert not app.exception
    assert not app.error
    assert set(list_prejob_models(root)[0].offset_well_ids) == {ids[name] for name in selected}


def test_add_selects_new_marker_and_does_not_repeat_on_rerun(project):
    root, ids = project
    app = page(root)
    before = load_markers(root, ids["offset_01"])
    widget(app, "text_input", "Marker name").set_value("New picked horizon")
    widget(app, "number_input", "Marker MD (ft)").set_value(1450.0)
    widget(app, "text_input", "Notes").set_value("Picked from acquired logs")
    widget(app, "button", "Add Marker").click().run()
    assert not app.exception
    after = load_markers(root, ids["offset_01"])
    assert len(after) == len(before) + 1
    created = next(marker for marker in after if marker.name == "New picked horizon")
    assert widget(app, "selectbox", "Select marker").value == created.marker_id
    assert widget(app, "text_input", "Edit name").value == created.name
    assert widget(app, "number_input", "Edit MD (ft)").value == 1450.0
    assert widget(app, "text_input", "Edit notes").value == "Picked from acquired logs"
    assert overlay_depths(app, "#0f766e") == [1450.0]
    app.run()
    assert load_markers(root, ids["offset_01"]) == after


def test_update_failure_preserves_draft_overlay_and_persisted_marker(project, monkeypatch):
    from app.pages import correlation_panel

    root, ids = project
    selected = add_marker(root, ids["offset_01"], "Saved pick", 1500.0, notes="Original notes")
    app = page(root)
    widget(app, "selectbox", "Select marker").set_value(selected.marker_id).run()
    before = load_markers(root, ids["offset_01"])
    widget(app, "number_input", "Edit MD (ft)").set_value(1540.0).run()
    widget(app, "text_input", "Edit notes").set_value("Keep this unsaved rationale").run()

    def fail(*args, **kwargs):
        raise OSError("Marker file is temporarily unavailable")

    monkeypatch.setattr(correlation_panel, "edit_marker", fail)
    widget(app, "button", "Update Marker").click().run()
    assert not app.exception
    assert any("Could not update marker" in error.value for error in app.error)
    assert widget(app, "number_input", "Edit MD (ft)").value == 1540.0
    assert widget(app, "text_input", "Edit notes").value == "Keep this unsaved rationale"
    assert overlay_depths(app, "#b45309") == [1540.0]
    assert overlay_depths(app, "#0f766e") == [1500.0]
    assert load_markers(root, ids["offset_01"]) == before


def test_active_run_hides_unacquired_markers_and_bounds_editor_to_acquired_survey(tmp_path):
    root, config, _, _ = prepare_run(tmp_path, "replay")
    visible = add_marker(root, config.active_well_id, "Visible acquired pick", 1500.0)
    future = add_marker(root, config.active_well_id, "Unacquired secret pick", 2500.0)
    app = page(root)
    widget(app, "multiselect", "Wells").set_value(["active_01"]).run()
    assert not app.exception
    marker_select = widget(app, "selectbox", "Select marker")
    assert any("Visible acquired pick" in label for label in marker_select.options)
    assert not any("Unacquired secret pick" in label for label in marker_select.options)
    marker_select.set_value(visible.marker_id).run()
    assert widget(app, "number_input", "Edit MD (ft)").max <= config.start_md_ft
    assert widget(app, "number_input", "Marker MD (ft)").max <= config.start_md_ft
    spec = figure(app)
    assert all(max(values(trace["y"])) <= config.start_md_ft for trace in spec["data"])
    assert not any("Unacquired secret pick" in annotation.get("text", "")
                   for annotation in spec["layout"].get("annotations", []))
    assert any(marker.marker_id == future.marker_id for marker in load_markers(root, config.active_well_id))
