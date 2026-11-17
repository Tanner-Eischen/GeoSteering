"""Automatic previews stay current without saving or recomputing unrelated reruns."""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import Mock

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from app.io.project_store import create_project, load_project, read_json
from app.io.well_import import import_well_folder
from app.services.markers import edit_marker, load_markers
from app.services.prejob import save_prejob_model
from tools.generate_sample_data import generate_sample_data


def workspace(root):
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from app.pages.planning import render\n"
        "render(st.session_state['test_project'])",
        default_timeout=30,
    )
    app.session_state["test_project"] = str(root)
    return app.run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def chart(app, trace_name):
    figures = [json.loads(element.proto.spec) for element in app.get("plotly_chart")]
    return next(spec for spec in figures if any(trace.get("name") == trace_name for trace in spec["data"]))


def values(encoded):
    if isinstance(encoded, dict) and "bdata" in encoded:
        return np.frombuffer(base64.b64decode(encoded["bdata"]), dtype=encoded["dtype"])
    return np.asarray(encoded)


def hashes(root):
    return {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def assert_no_save_actions(app):
    assert not any(item.label in {"Save Plan", "Continue to Steering"} for item in app.button)
    assert not app.get("download_button")


def test_edits_refresh_chart_geometry_and_limit_without_writes_until_save(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Paired planning")
    before = hashes(root)
    app = workspace(root)
    assert not app.exception
    assert {"Plan & preview", "Details & data"} <= {tab.label for tab in app.tabs}
    assert len(app.get("plotly_chart")) == 2
    assert not any(item.label == "Generate Preview" for item in app.button)
    original = chart(app, "Plan profile")
    original_dls = chart(app, "DLS")
    assert original["layout"]["height"] == 320
    assert original_dls["layout"]["shapes"][0]["y0"] == 6.0
    app.number_input(key="planning_input_dls").set_value(8.0).run()
    assert chart(app, "DLS")["layout"]["shapes"][0]["y0"] == 8.0
    app.number_input(key="planning_input_length").set_value(4000.0).run()
    assert max(values(chart(app, "Plan profile")["data"][0]["x"])) == 6000.0
    app.number_input(key="planning_input_spacing").set_value(50.0).run()
    app.text_input(key="planning_input_name").set_value("Edited plan").run()
    assert not app.exception
    assert not any("Previous preview" in message.value for message in app.warning)
    updated = chart(app, "Plan profile")
    assert max(values(updated["data"][0]["x"])) == 6000.0
    assert len(values(updated["data"][0]["x"])) > len(values(original["data"][0]["x"]))
    assert updated["layout"]["uirevision"] != original["layout"]["uirevision"]
    assert chart(app, "DLS")["layout"]["shapes"][0]["y0"] == 8.0
    assert any("Preview: Edited plan" in caption.value and "Spacing 50" in caption.value for caption in app.caption)
    assert not button(app, "Save Plan").disabled
    assert hashes(root) == before
    button(app, "Save Plan").click().run()
    assert not app.exception
    saved = read_json(next((root / "plans").glob("*.json")))
    assert saved["name"] == "Edited plan"
    assert saved["parameters"]["lateral_length_ft"] == 4000.0
    assert saved["parameters"]["step_ft"] == 50.0
    assert saved["dls_max_deg_per_100ft"] == 8.0


def test_invalid_request_is_cached_and_correction_recovers_automatically(tmp_path, monkeypatch):
    from app.pages import planning

    generate = Mock(wraps=planning.generate_plan)
    monkeypatch.setattr(planning, "generate_plan", generate)
    root = tmp_path / "project"
    create_project(root, "Invalid geometry")
    app = workspace(root)
    assert generate.call_count == 1
    assert len(app.get("plotly_chart")) == 2
    app.number_input(key="planning_input_landing").set_value(100.0).run()
    assert not app.exception
    assert app.error
    assert not app.get("plotly_chart")
    assert_no_save_actions(app)
    assert generate.call_count == 2
    app.run()
    assert not app.exception
    assert app.error
    assert generate.call_count == 2
    assert not app.get("plotly_chart")
    app.number_input(key="planning_input_landing").set_value(2000.0).run()
    assert not app.exception
    assert not app.error
    assert len(app.get("plotly_chart")) == 2
    assert not button(app, "Save Plan").disabled
    assert not list((root / "plans").glob("*.json"))


def test_other_project_gets_its_own_preview_without_previous_saved_id(tmp_path, monkeypatch):
    from app.pages import planning

    generate = Mock(wraps=planning.generate_plan)
    monkeypatch.setattr(planning, "generate_plan", generate)
    first, second = tmp_path / "first", tmp_path / "second"
    create_project(first, "First project")
    create_project(second, "Second project")
    app = workspace(first)
    assert len(app.get("plotly_chart")) == 2
    button(app, "Save Plan").click().run()
    assert generate.call_count == 1
    first_saved = app.session_state["planning_preview_saved_id"]
    assert button(app, "Save Plan").disabled
    app.session_state["test_project"] = str(second)
    app.run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 2
    assert generate.call_count == 2
    assert app.session_state["planning_preview_root"] == str(second.resolve())
    assert not button(app, "Save Plan").disabled
    assert button(app, "Continue to Steering").disabled
    assert [path.stem for path in (first / "plans").glob("*.json")] == [first_saved]
    assert not list((second / "plans").glob("*.json"))


def test_model_change_refreshes_pinned_evidence_and_invalid_source_clears_preview(tmp_path):
    sample = tmp_path / "sample"
    generate_sample_data(sample, seed=123)
    root = tmp_path / "project"
    create_project(root, "Model evidence")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(root, sample / "wells" / name, name)
    project = load_project(root)
    offsets = [well.well_id for well in project.wells if well.well_id != project.active_well_id]
    first = save_prejob_model(root, offsets[:2])
    second = save_prejob_model(root, offsets)
    app = workspace(root)
    model_key = f"planning_model_{root.resolve()}"
    app.selectbox(key=model_key).set_value(first.interpretation.version_id).run()
    assert app.session_state["planning_preview_model"]["model_sha256"] == first.model_sha256
    app.selectbox(key=model_key).set_value(second.interpretation.version_id).run()
    assert not app.exception
    assert not button(app, "Save Plan").disabled
    assert app.session_state["planning_preview_model"]["model_sha256"] == second.model_sha256
    assert any(second.model_sha256[:12] in caption.value for caption in app.caption)
    button(app, "Save Plan").click().run()
    saved_path = next((root / "plans").glob("*.json"))
    assert read_json(saved_path)["geological_model"]["model_sha256"] == second.model_sha256
    marker = load_markers(root, offsets[0])[0]
    edit_marker(root, offsets[0], marker.marker_id, notes="Changed evidence after generating preview")
    app.run()
    assert not app.exception
    assert app.error
    assert_no_save_actions(app)
    assert not app.get("plotly_chart")
    assert read_json(saved_path)["geological_model"]["model_sha256"] == second.model_sha256
    refreshed = save_prejob_model(root, offsets)
    app.run()
    app.selectbox(key=model_key).set_value(refreshed.interpretation.version_id).run()
    assert not app.exception
    assert not app.error
    assert app.session_state["planning_preview_model"]["model_sha256"] == refreshed.model_sha256
    assert not button(app, "Save Plan").disabled
    assert len(list((root / "plans").glob("*.json"))) == 1


def test_unrelated_reruns_chart_controls_and_save_do_not_regenerate_or_reset_saved_id(tmp_path, monkeypatch):
    from app.pages import planning

    generate = Mock(wraps=planning.generate_plan)
    monkeypatch.setattr(planning, "generate_plan", generate)
    root = tmp_path / "project"
    create_project(root, "Preview reuse")
    app = workspace(root)
    assert not app.exception
    assert generate.call_count == 1
    app.run()
    app.radio(key="planning_profile_drag").set_value("Box zoom").run()
    app.checkbox(key="planning_dls_wheel").check().run()
    app.button(key="planning_profile_reset").click().run()
    assert not app.exception
    assert generate.call_count == 1
    button(app, "Save Plan").click().run()
    saved_id = app.session_state["planning_preview_saved_id"]
    app.run()
    app.radio(key="planning_profile_drag").set_value("Pan").run()
    assert not app.exception
    assert generate.call_count == 1
    assert app.session_state["planning_preview_saved_id"] == saved_id
    assert button(app, "Save Plan").disabled
    assert not button(app, "Continue to Steering").disabled
    assert len(list((root / "plans").glob("*.json"))) == 1
    app.number_input(key="planning_input_length").set_value(4500.0).run()
    assert not app.exception
    assert generate.call_count == 2
    assert not button(app, "Save Plan").disabled
    assert button(app, "Continue to Steering").disabled
    assert len(list((root / "plans").glob("*.json"))) == 1


def test_incomplete_plan_name_clears_preview_and_recovers_without_saving(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Incomplete inputs")
    before = hashes(root)
    app = workspace(root)
    app.text_input(key="planning_input_name").set_value("   ").run()
    assert not app.exception
    assert app.error
    assert not app.get("plotly_chart")
    assert_no_save_actions(app)
    app.text_input(key="planning_input_name").set_value("Recovered plan").run()
    assert not app.exception
    assert not app.error
    assert app.session_state["planning_preview_name"] == "Recovered plan"
    assert len(app.get("plotly_chart")) == 2
    assert not button(app, "Save Plan").disabled
    assert hashes(root) == before


@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf")])
def test_incomplete_or_nonfinite_numeric_input_clears_and_recovers_preview(tmp_path, monkeypatch, invalid):
    from app.pages import planning

    root = tmp_path / "project"
    create_project(root, "Incomplete numeric input")
    before = hashes(root)
    app = workspace(root)
    original = planning.st.number_input

    def incomplete(label, *args, **kwargs):
        value = original(label, *args, **kwargs)
        return invalid if label == "Kickoff MD (ft)" else value

    # Simulate an incomplete widget value at the handler boundary; AppTest's
    # numeric setter rejects nonfinite values before the page receives them.
    monkeypatch.setattr(planning.st, "number_input", incomplete)
    app.run()
    assert not app.exception
    assert any("finite value for Kickoff MD" in error.value for error in app.error)
    assert not app.get("plotly_chart")
    assert_no_save_actions(app)
    monkeypatch.setattr(planning.st, "number_input", original)
    app.run()
    assert not app.exception
    assert not app.error
    assert len(app.get("plotly_chart")) == 2
    assert app.session_state["planning_preview_params"]["kickoff_md_ft"] == 500.0
    assert not button(app, "Save Plan").disabled
    assert hashes(root) == before
