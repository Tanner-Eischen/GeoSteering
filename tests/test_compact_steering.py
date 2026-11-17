"""Compact steering contracts exercised in-process, without browser access."""

from __future__ import annotations

import base64
import hashlib
import json

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from app.services.decisions import load_decisions
from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.run_paths import active_run_id, run_root
from app.services.runs import initialize_run
from app.services.steering_preview import preview_command
from tests.test_run_history import prepare_run


def workspace(root, run_id, *, full_page=False):
    body = (
        "from app.pages.steering_console import render\nrender(str(root))"
        if full_page else
        f"from app.pages.steering_console import _steering_workspace\n"
        f"_steering_workspace(root, load_operator_view(root, {run_id!r}))"
    )
    app = AppTest.from_string(
        "from pathlib import Path\n"
        "from app.services.operator_workflow import load_operator_view\n"
        f"root = Path({str(root)!r})\n" + body,
        default_timeout=30,
    )
    if full_page:
        app.session_state[f"_selected_run_context_{root.resolve()}"] = run_id
    return app.run()


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def figures(app):
    return [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]


def trace(app, name):
    return next(item for fig in figures(app) for item in fig["data"] if item.get("name") == name)


def values(encoded):
    if isinstance(encoded, dict) and "bdata" in encoded:
        return np.frombuffer(base64.b64decode(encoded["bdata"]), dtype=encoded["dtype"])
    return np.asarray(encoded)


def hashes(scope):
    return {
        path.relative_to(scope): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in scope.rglob("*") if path.is_file()
    }


def test_causal_command_changes_geometry_without_revealing_or_advancing(tmp_path, monkeypatch):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    before = load_operator_view(root, run_id)
    snapshot = hashes(run_root(root, run_id))
    from app.sim import environment

    monkeypatch.setattr(environment, "load_private_scenario", lambda *a, **k: pytest.fail("Private geology read"))
    monkeypatch.setattr(environment, "sample_station", lambda *a, **k: pytest.fail("Future measurement sampled"))
    app = workspace(root, run_id)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Logs", "Path + preview"]
    initial_projection = values(trace(app, "Next station projection")["y"]).copy()
    widget(app, "radio", "Recommendation").set_value("BUILD").run()
    widget(app, "checkbox", "Set a target inclination").check().run()
    widget(app, "number_input", "Requested inclination (degrees)").set_value(93.0).run()
    assert not app.exception
    expected = preview_command(root, run_id=run_id, expected_step_index=0, action="BUILD", target_inc_deg=93.0)
    projection = trace(app, "Next station projection")
    assert values(projection["y"])[-1] == pytest.approx(expected["station"]["tvd_ft"])
    assert values(projection["x"])[-1] == pytest.approx(expected["station"]["x_ft"])
    assert not np.allclose(initial_projection, values(projection["y"]))
    for curve in before["config"].curves_used:
        assert max(values(trace(app, curve)["x"])) <= before["state"].revealed_md_ft
    assert max(values(trace(app, "Acquired path")["x"])) <= before["frames"]["trajectory"].x_ft.max()
    assert hashes(run_root(root, run_id)) == snapshot
    assert load_operator_view(root, run_id)["state"].step_index == 0


def test_compact_submit_records_once_and_uses_fresh_evidence_for_next_step(tmp_path):
    root, config, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    app = workspace(root, run_id)
    evidence = "The acquired landing signal supports a bounded build."
    widget(app, "radio", "Recommendation").set_value("BUILD").run()
    widget(app, "checkbox", "Set a target inclination").check().run()
    widget(app, "number_input", "Requested inclination (degrees)").set_value(92.0).run()
    widget(app, "text_area", "Observed evidence (required)").set_value(evidence).run()
    old_key = widget(app, "text_area", "Observed evidence (required)").key
    widget(app, "button", "Record & advance").click().run()
    assert not app.exception
    updated = load_operator_view(root, run_id)
    assert updated["state"].step_index == 1
    assert updated["state"].revealed_md_ft == config.start_md_ft + config.step_size_ft
    decisions = load_decisions(root, run_id)
    assert len(decisions) == 1
    assert decisions[0].observations == evidence
    assert decisions[0].recommendation.action == "BUILD"
    assert decisions[0].recommendation.target_inc_deg == 92.0
    assert widget(app, "text_area", "Observed evidence (required)").value == ""
    assert widget(app, "text_area", "Observed evidence (required)").key != old_key
    app.run()
    assert not app.exception
    assert load_operator_view(root, run_id)["state"].step_index == 1
    widget(app, "button", "Record & advance").click().run()
    assert not app.exception
    assert app.error  # Empty evidence cannot silently reuse the previous decision.
    assert load_operator_view(root, run_id)["state"].step_index == 1
    assert len(load_decisions(root, run_id)) == 1


def test_full_page_advances_selected_run_when_another_run_is_active(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    selected = active_run_id(root)
    other = initialize_run(root, config, top, base)
    assert active_run_id(root) == other.run_id
    app = workspace(root, selected, full_page=True)
    assert not app.exception
    assert widget(app, "selectbox", "Saved steering run").value == selected
    assert {"Steer", "History & results", "Run setup"} <= {tab.label for tab in app.tabs}
    widget(app, "text_area", "Observed evidence (required)").set_value("Evidence for the selected historical branch").run()
    widget(app, "button", "Record & advance").click().run()
    assert not app.exception
    assert widget(app, "selectbox", "Saved steering run").value == selected
    assert load_operator_view(root, selected)["state"].step_index == 1
    assert load_operator_view(root, other.run_id)["state"].step_index == 0
    assert active_run_id(root) == other.run_id
    assert len(load_decisions(root, selected)) == 1
    assert not load_decisions(root, other.run_id)


def test_completed_workspace_has_no_command_or_future_projection(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    complete = initialize_run(root, config.model_copy(update={"end_md_ft": config.start_md_ft + config.step_size_ft}), top, base)
    view = load_operator_view(root, complete.run_id)
    submit_steering(root, run_id=complete.run_id, expected_step_index=0,
                    interpretation_version_id=view["interpretation"].version_id,
                    action="HOLD", observations="Complete the single-interval test run")
    snapshot = hashes(run_root(root, complete.run_id))
    app = workspace(root, complete.run_id)
    assert not app.exception
    assert load_operator_view(root, complete.run_id)["state"].complete
    assert not any(button.label == "Record & advance" for button in app.button)
    assert not any(radio.label == "Recommendation" for radio in app.radio)
    assert not app.text_area
    assert not any(item.get("name") == "Next station projection" for fig in figures(app) for item in fig["data"])
    assert any("No intervals remain" in message.value for message in app.info)
    assert hashes(run_root(root, complete.run_id)) == snapshot
