import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app.io.project_store import create_project
from app.io.well_import import import_well_folder
from app.plot.correlation_panel import build_correlation_figure
from app.plot.log_tracks import build_log_tracks_figure
from app.services.markers import add_marker
from app.ui.charts import chart_config
from tools.generate_sample_data import generate_sample_data


def make_project(tmp_path):
    sample = tmp_path / "sample"
    generate_sample_data(sample, seed=123)
    root = tmp_path / "project"
    create_project(root, "Chart controls")
    result = import_well_folder(root, sample / "wells" / "offset_01", "Offset")
    return root, result


def page(root, module):
    return AppTest.from_string(f"from app.pages.{module} import render\nrender({str(root)!r})", default_timeout=30).run()


def labelled(elements, label):
    return next(element for element in elements if element.label == label)


def test_depth_zoom_does_not_expand_to_offscreen_markers_or_bit():
    logs = pd.DataFrame({"md_ft": [100., 150., 200.], "GR": [20., 40., 60.]})
    markers = [{"name": "Outside", "md_ft": 500.}, {"name": "Inside", "md_ft": 150.}]
    figure, _ = build_log_tracks_figure(logs, markers, ["GR"], 100., 200., bit_md_ft=900.)
    assert list(figure.layout.yaxis.range) == [200., 100.]
    assert len(figure.layout.shapes) == 1
    correlation = build_correlation_figure({"A": logs}, {"A": markers}, ["GR"], 100., 200.)
    assert len(correlation.layout.shapes) == 1
    assert list(correlation.layout.yaxis.range) == [200., 100.]
    empty, meta = build_log_tracks_figure(logs, curves=[])
    assert not empty.data and meta.rendered_points == 0
    assert chart_config()["scrollZoom"] is False


def test_viewer_empty_selection_and_invalid_depth_are_actionable(tmp_path):
    root, _ = make_project(tmp_path)
    app = page(root, "well_viewer")
    assert not app.exception
    labelled(app.multiselect, "Curves").set_value([]).run()
    assert not app.exception
    assert any("Select at least one curve" in item.value for item in app.info)
    labelled(app.multiselect, "Curves").set_value(["GR"]).run()
    labelled(app.selectbox, "Depth Range").set_value("Custom").run()
    labelled(app.number_input, "Depth Min (ft)").set_value(2000.).run()
    labelled(app.number_input, "Depth Max (ft)").set_value(1000.).run()
    assert not app.exception
    assert any("minimum must be smaller" in item.value for item in app.warning)


def test_marker_switch_populates_correct_fields_and_jump_runs_without_widget_mutation(tmp_path):
    root, _ = make_project(tmp_path)
    from app.io.project_store import load_project
    well_id = load_project(root).wells[0].well_id
    marker = add_marker(root, well_id, "Distinct marker", 1500., notes="Second marker notes")
    app = page(root, "correlation_panel")
    assert not app.exception
    marker_select = labelled(app.selectbox, "Select marker")
    marker_select.set_value(marker.marker_id).run()
    assert not app.exception
    assert labelled(app.text_input, "Edit name").value == "Distinct marker"
    assert labelled(app.number_input, "Edit MD (ft)").value == 1500.
    assert labelled(app.text_input, "Edit notes").value == "Second marker notes"
    labelled(app.button, "Jump to Marker").click().run()
    assert not app.exception
    assert labelled(app.number_input, "Depth min (ft)").value == 1350.
    assert labelled(app.number_input, "Depth max (ft)").value == 1650.
    labelled(app.selectbox, "Alignment basis").set_value("Local TVD (ft)").run()
    assert not app.exception
    labelled(app.button, "Jump to Marker").click().run()
    assert not app.exception
    assert labelled(app.selectbox, "Alignment basis").value == "Measured depth (ft)"
    assert labelled(app.number_input, "Depth min (ft)").value == 1350.
    labelled(app.button, "Full depth").click().run()
    assert not app.exception
    assert labelled(app.number_input, "Depth min (ft)").value < 1350.
    labelled(app.button, "Reset view").click().run()
    assert not app.exception


@pytest.mark.parametrize("operation,button,message", [
    ("add_marker", "Add Marker", "Could not add marker"),
    ("edit_marker", "Update Marker", "Could not update marker"),
    ("delete_marker", "Delete Marker", "Could not delete marker"),
])
def test_marker_persistence_errors_preserve_inputs_and_data(tmp_path, monkeypatch, operation, button, message):
    from app.io.project_store import load_project
    from app.pages import correlation_panel
    from app.services.markers import load_markers
    root, _ = make_project(tmp_path)
    well_id = load_project(root).wells[0].well_id
    before = load_markers(root, well_id)
    app = page(root, "correlation_panel")
    labelled(app.text_input, "Marker name").set_value("New pick")
    labelled(app.text_input, "Edit notes").set_value("Keep these notes")
    if operation == "delete_marker":
        labelled(app.checkbox, "Allow deletion of the selected marker").check().run()

    def fail(*args, **kwargs):
        raise OSError("Example write failure")

    monkeypatch.setattr(correlation_panel, operation, fail)
    labelled(app.button, button).click().run()
    assert not app.exception
    assert any(message in item.value for item in app.error)
    if operation == "add_marker":
        assert labelled(app.text_input, "Marker name").value == "New pick"
    assert labelled(app.text_input, "Edit notes").value == "Keep these notes"
    assert load_markers(root, well_id) == before


def test_marker_edit_rejects_out_of_support_depth_and_keeps_duplicate_picks(tmp_path, monkeypatch):
    from app.io.project_store import load_project
    from app.services.markers import load_markers
    from app.services.project_data import load_well_frames
    root, _ = make_project(tmp_path)
    well_id = load_project(root).wells[0].well_id
    first = add_marker(root, well_id, "Duplicate", 1500., notes="First")
    second = add_marker(root, well_id, "Duplicate", 1500., notes="Second")
    before = load_markers(root, well_id)
    app = page(root, "correlation_panel")
    labelled(app.selectbox, "Select marker").set_value(first.marker_id).run()
    assert labelled(app.text_input, "Edit notes").value == "First"
    labelled(app.selectbox, "Select marker").set_value(second.marker_id).run()
    assert labelled(app.text_input, "Edit notes").value == "Second"
    survey = load_well_frames(root, well_id)["trajectory"]
    depth_input = labelled(app.number_input, "Edit MD (ft)")
    assert depth_input.min == float(survey.md_ft.min())
    assert depth_input.max == float(survey.md_ft.max())
    from app.pages import correlation_panel
    original_number_input = correlation_panel.st.number_input
    for depth in [-1., float(survey.md_ft.max()) + 1.]:
        def inject_invalid_depth(label, *args, **kwargs):
            value = original_number_input(label, *args, **kwargs)
            return depth if label == "Edit MD (ft)" else value

        monkeypatch.setattr(correlation_panel.st, "number_input", inject_invalid_depth)
        labelled(app.button, "Update Marker").click().run()
        assert not app.exception
        assert any("within the acquired survey support" in item.value for item in app.error)
        assert load_markers(root, well_id) == before



def test_chart_interaction_mode_preserves_view_but_data_and_reset_invalidate_it():
    import json
    app = AppTest.from_string("""
import streamlit as st
import plotly.graph_objects as go
from app.ui.charts import render_chart
scale = st.number_input("Scale", value=1)
render_chart(go.Figure(go.Scatter(x=[0, 1], y=[0, scale])), key="chart_test")
""").run()

    def revision():
        return json.loads(app.get("plotly_chart")[0].proto.spec)["layout"]["uirevision"]

    initial = revision()
    labelled(app.radio, "Drag to").set_value("Box zoom").run()
    assert revision() == initial
    labelled(app.checkbox, "Wheel zoom").check().run()
    assert revision() == initial
    labelled(app.number_input, "Scale").set_value(2).run()
    changed = revision()
    assert changed != initial
    labelled(app.button, "Reset view").click().run()
    assert revision() != changed
    assert not app.exception



def test_correlation_display_groups_preserve_selected_interpretation_evidence(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from app.io.project_store import load_project
    from app.pages import correlation_panel

    sample = tmp_path / "sample"
    generate_sample_data(sample, seed=123)
    root = tmp_path / "project"
    create_project(root, "Display groups")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(root, sample / "wells" / name, name)
    project = load_project(root)
    expected_offsets = [well.well_id for well in project.wells if well.well_id != project.active_well_id]
    captured = []

    def capture_save(project_root, offset_ids):
        captured.extend(offset_ids)
        return SimpleNamespace(interpretation=SimpleNamespace(version_id="display-test"))

    monkeypatch.setattr(correlation_panel, "save_prejob_model", capture_save)
    app = page(root, "correlation_panel")
    labelled(app.multiselect, "Curves").set_value(["GR"]).run()
    assert not app.exception
    assert labelled(app.selectbox, "Wells per chart").value == 1
    labelled(app.selectbox, "Wells per chart").set_value(3).run()
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(spec["data"]) == 3
    assert spec["layout"]["yaxis"]["title"]["text"] == "Measured depth (ft)"
    for axis in ["yaxis2", "yaxis3"]:
        assert not spec["layout"][axis].get("title", {}).get("text")
        assert spec["layout"][axis]["matches"] == "y"

    labelled(app.selectbox, "Wells per chart").set_value(1).run()
    labelled(app.selectbox, "Visible well group").set_value(1).run()
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(spec["data"]) == 1
    assert spec["layout"]["annotations"][0]["text"] == "offset_02"
    assert labelled(app.multiselect, "Wells").value == ["offset_01", "offset_02", "offset_03"]
    labelled(app.button, "Save pre-job interpretation from selected offset picks").click().run()
    assert not app.exception
    assert captured == expected_offsets



def test_correlation_depth_range_recovers_after_page_widget_cleanup(tmp_path):
    from app.io.project_store import load_project
    from app.services.project_data import load_well_frames

    root, _ = make_project(tmp_path)
    well_id = load_project(root).wells[0].well_id
    logs = load_well_frames(root, well_id)["logs"]
    acquired_min = float(logs.md_ft.min())
    acquired_max = float(logs.md_ft.max())
    app = AppTest.from_string(f"""
import streamlit as st
from app.pages.correlation_panel import render
page = st.radio("Test page", ["Correlation", "Import Data"], key="test_page")
if page == "Correlation":
    render({str(root)!r})
else:
    st.write("Import workspace")
""", default_timeout=30).run()
    assert not app.exception
    labelled(app.number_input, "Depth min (ft)").set_value(acquired_min + 25.).run()
    labelled(app.number_input, "Depth max (ft)").set_value(acquired_max - 25.).run()
    labelled(app.radio, "Drag to").set_value("Box zoom").run()
    assert labelled(app.number_input, "Depth min (ft)").value == acquired_min + 25.
    assert labelled(app.number_input, "Depth max (ft)").value == acquired_max - 25.
    labelled(app.radio, "Test page").set_value("Import Data").run()
    assert "corr_depth_context" in app.session_state
    assert "corr_depth_min" not in app.session_state
    assert "corr_depth_max" not in app.session_state
    labelled(app.radio, "Test page").set_value("Correlation").run()
    assert not app.exception
    assert labelled(app.number_input, "Depth min (ft)").value == acquired_min
    assert labelled(app.number_input, "Depth max (ft)").value == acquired_max
