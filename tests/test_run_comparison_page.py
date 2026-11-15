from __future__ import annotations

from streamlit.testing.v1 import AppTest

from app.io.project_store import create_project
from app.services.interpretations import load_interpretations
from app.services.run_paths import run_root
from app.services.runs import fork_run, initialize_run
from app.sim.sim_store import load_simulation_config
from tests.test_run_comparison import advance, branch_pair


def page(root):
    return AppTest.from_string(
        f"from app.pages.run_comparison import render\nrender({str(root)!r})",
        default_timeout=20,
    ).run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_page_explains_missing_project_and_missing_runs(tmp_path):
    app = AppTest.from_string("from app.pages.run_comparison import render\nrender(None)").run()
    assert not app.exception
    assert "Open a project" in app.info[0].value
    root = tmp_path / "project"
    create_project(root, "No runs yet")
    app = page(root)
    assert not app.exception
    assert "no saved runs" in app.info[0].value


def test_partial_page_renders_common_horizon_commands_and_sealed_truth(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    advance(root, parent, "BUILD")
    advance(root, child, "DROP")
    advance(root, parent)
    app = page(root)
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Common endpoint MD (ft)"] == "2,200"
    assert metrics["Compared lateral length (ft)"] == "200"
    assert button(app, "Evaluate completed branches").disabled
    assert any("Complete both branches" in item.value for item in app.info)
    assert len(app.get("plotly_chart")) == 3
    commands = next(frame.value for frame in app.dataframe if "Left action" in frame.value.columns)
    assert commands.iloc[0]["Left action"] == "BUILD"
    assert commands.iloc[0]["Right action"] == "DROP"
    assert not any("True in target (%)" in frame.value.columns for frame in app.dataframe)


def test_selecting_same_run_displays_readable_fairness_reason(tmp_path):
    root, parent, _ = branch_pair(tmp_path)
    app = page(root)
    selector = next(item for item in app.selectbox if item.label == "Right branch")
    selector.set_value(parent).run()
    assert not app.exception
    assert any("two different saved runs" in item.value for item in app.warning)


def test_completed_page_only_shows_independent_scores_after_explicit_evaluation(tmp_path):
    root, parent, child = branch_pair(tmp_path)
    for run_id, action in ((parent, "BUILD"), (child, "DROP")):
        advance(root, run_id, action)
        advance(root, run_id, action)
    app = page(root)
    assert not app.exception
    assert not button(app, "Evaluate completed branches").disabled
    assert not any("True in target (%)" in frame.value.columns for frame in app.dataframe)
    button(app, "Evaluate completed branches").click().run()
    assert not app.exception
    truth = next(frame.value for frame in app.dataframe if "True in target (%)" in frame.value.columns)
    assert truth["Lateral denominator (ft)"].tolist() == [300, 300]
    assert any(item.label == "True placement difference · right minus left (pp)" for item in app.metric)


def test_two_family_navigation_consumes_target_and_preserves_manual_reruns(tmp_path):
    root, first_parent, first_child = branch_pair(tmp_path)
    config = load_simulation_config(root, first_parent)
    baseline = load_interpretations(root, first_parent)[0]
    second_parent = initialize_run(
        root, config.model_copy(update={"run_id": None}), baseline.top_control_points,
        baseline.base_control_points, hidden_truth_path=run_root(root, first_parent) / "environment/scenario.json",
    ).run_id
    second_child = fork_run(root, second_parent).run_id
    app = AppTest.from_string(
        f"from app.pages.run_comparison import render\nrender({str(root)!r})", default_timeout=20,
    )
    # Prior comparison selections belong to family A; navigation requests B.
    app.session_state[f"run_compare_left_{root.resolve()}"] = first_parent
    app.session_state[f"run_compare_right_{root.resolve()}"] = first_child
    app.session_state[f"_selected_run_context_{root.resolve()}"] = second_child
    app.session_state["comparison_target"] = {"project_root": str(root.resolve()), "run_id": second_child}
    app.run()
    assert not app.exception
    assert [item.value for item in app.selectbox] == [second_parent, second_child]
    # Deliberate manual picks survive ordinary widget reruns.
    next(item for item in app.selectbox if item.label == "Left branch").set_value(first_parent).run()
    next(item for item in app.selectbox if item.label == "Right branch").set_value(first_child).run()
    app.run()
    assert [item.value for item in app.selectbox] == [first_parent, first_child]
    # Re-entering from the same remembered B branch overrides stale A widgets.
    app.session_state["comparison_target"] = {"project_root": str(root.resolve()), "run_id": second_child}
    app.run()
    assert not app.exception
    assert [item.value for item in app.selectbox] == [second_parent, second_child]
