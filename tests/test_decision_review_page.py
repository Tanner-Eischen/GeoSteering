"""Streamlit review selectors preserve phase and explicit run boundaries."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from app.model.schemas import ControlPoint
from app.pages.decision_review import _interpretation_figure
from app.services.decision_review import load_decision_review
from app.services.run_paths import active_run_id
from app.services.runs import fork_run
from tests.test_decision_review import record
from tests.test_run_history import prepare_run


def page(root):
    return AppTest.from_string(f"""
from app.pages.decision_review import render
render({str(root)!r})
""", default_timeout=20).run()


def metric(app, label):
    return next(item.value for item in app.metric if item.label == label)


def test_baseline_and_no_project_render_without_exceptions(tmp_path):
    app = AppTest.from_string("from app.pages.decision_review import render\nrender(None)").run()
    assert not app.exception
    assert any("Open a project" in item.value for item in app.info)
    root, _, _, _ = prepare_run(tmp_path)
    app = page(root)
    assert not app.exception
    assert metric(app, "Selected step") == "0"
    assert metric(app, "Evidence through MD (ft)") == "2,000.0"
    assert not app.button
    assert any("No metric snapshot" in item.value for item in app.caption)


def test_phase_switch_uses_only_that_intervals_persisted_metrics(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    record(root, run_id)
    record(root, run_id, action="BUILD")
    app = page(root)
    assert not app.exception
    assert metric(app, "Selected step") == "2"
    assert metric(app, "Evidence through MD (ft)") == "2,100.0"
    assert any("Original snapshot after step 1" in item.value for item in app.caption)
    app.radio[0].set_value("after").run()
    assert not app.exception
    assert metric(app, "Evidence through MD (ft)") == "2,200.0"
    assert any("Original snapshot after step 2" in item.value for item in app.caption)
    app.selectbox[1].set_value(1).run()
    assert metric(app, "Evidence through MD (ft)") == "2,100.0"
    app.radio[0].set_value("decision").run()
    assert not app.exception
    assert metric(app, "Evidence through MD (ft)") == "2,000.0"
    assert not any("Original snapshot after step 2" in item.value for item in app.caption)
    assert not any(item.label == "Estimated in zone (%)" for item in app.metric)


def test_explicit_run_switch_updates_the_shared_selection_context(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    parent_id = active_run_id(root)
    record(root, parent_id)
    child = fork_run(root, parent_id)
    record(root, child.run_id, action="DROP")
    app = page(root)
    assert metric(app, "Selected step") == "2"
    app.selectbox[0].set_value(parent_id).run()
    assert not app.exception
    assert metric(app, "Selected step") == "1"
    assert metric(app, "Evidence through MD (ft)") == "2,000.0"
    assert app.session_state[f"_selected_run_context_{root.resolve()}"] == parent_id
    app.selectbox[0].set_value(child.run_id).run()
    assert not app.exception
    assert metric(app, "Selected step") == "2"
    assert any("Fork of" in item.value for item in app.caption)


def test_plot_preserves_an_interior_interpretation_knot(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    selected = active_run_id(root)
    record(root, selected)
    view = load_decision_review(root, selected, 1, "after")
    path = view["frames"]["trajectory"]
    x = float(path.x_ft.iloc[-1] - 20)
    current = view["interpretation"]
    points = sorted([*current.top_control_points, ControlPoint(md_ft=x, x_ft=x, tvd_ft=1400)], key=lambda point: point.x_ft)
    view["interpretation"] = current.model_copy(update={"top_control_points": points})
    figure = _interpretation_figure(view)
    trace = next(trace for trace in figure.data if trace.name == "Decision interpretation · top")
    assert x in trace.x
    assert list(trace.y)[list(trace.x).index(x)] == 1400
