from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.io.project_store import atomic_write_json
from app.services import evaluation_view
from app.services.evaluation_view import evaluate_and_save, load_evaluation_view
from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.runs import active_run_id, initialize_run
from tests.test_run_history import prepare_run


def complete(root, config, top, base):
    state = initialize_run(root, config.model_copy(update={"step_size_ft": 2500}), top, base)
    for _ in range(2):
        view = load_operator_view(root, state.run_id)
        state = submit_steering(root, run_id=state.run_id, expected_step_index=view["state"].step_index,
                                interpretation_version_id=view["interpretation"].version_id,
                                action="HOLD", observations="Current acquired signal supports HOLD")
    return state.run_id


def snapshot(scope):
    return {path.relative_to(scope): path.read_bytes() for path in scope.rglob("*") if path.is_file()}


def test_partial_view_never_loads_truth_or_saved_future_scores(tmp_path, monkeypatch):
    root, _, _, _ = prepare_run(tmp_path)
    run_id = active_run_id(root)
    atomic_write_json(root / "runs" / run_id / "evaluation" / "replay.json", {"future_score": 999999})
    before = snapshot(root)
    monkeypatch.setattr(evaluation_view, "evaluate_completed_run", lambda *a, **kw: pytest.fail("Partial truth evaluation"))
    monkeypatch.setattr(evaluation_view, "load_completed_scenario", lambda *a, **kw: pytest.fail("Partial truth load"))
    view = load_evaluation_view(root, run_id)
    assert view["evaluation"] is view["profile"] is None
    assert view["frames"]["trajectory"].md_ft.max() == 2000
    assert snapshot(root) == before
    with pytest.raises(ValueError, match="Complete"):
        # Explicit evaluation is also completion-gated by the owning evaluator.
        from app.services.evaluation import evaluate_completed_run
        evaluate_completed_run(root, run_id=run_id)


def test_completed_unevaluated_view_waits_for_explicit_evaluation(tmp_path, monkeypatch):
    root, config, top, base = prepare_run(tmp_path)
    run_id = complete(root, config, top, base)
    before = snapshot(root)
    monkeypatch.setattr(evaluation_view, "evaluate_completed_run", lambda *a, **kw: pytest.fail("Implicit evaluation"))
    monkeypatch.setattr(evaluation_view, "load_completed_scenario", lambda *a, **kw: pytest.fail("Implicit truth load"))
    view = load_evaluation_view(root, run_id)
    assert view["state"].complete and view["evaluation"] is None
    assert view["evaluation_error"] is None
    assert snapshot(root) == before


def test_evaluation_uses_explicit_completed_run_and_keeps_other_history_intact(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    run_id = complete(root, config, top, base)
    alternate = initialize_run(root, config, top, base)
    other_before = snapshot(root / "runs" / alternate.run_id)
    saved = evaluate_and_save(root, run_id)
    assert saved["run_id"] == run_id
    before = snapshot(root)
    view = load_evaluation_view(root, run_id)
    assert view["evaluation"] == saved
    assert len(view["profile"]["md_ft"]) == 1001
    assert view["profile"]["lateral_dls_limit"] == 3
    assert snapshot(root) == before
    assert snapshot(root / "runs" / alternate.run_id) == other_before
    assert active_run_id(root) == alternate.run_id


@pytest.mark.parametrize("corruption", ("wrong_run", "score"))
def test_invalid_saved_scores_are_not_displayed(tmp_path, corruption):
    root, config, top, base = prepare_run(tmp_path)
    run_id = complete(root, config, top, base)
    saved = evaluate_and_save(root, run_id)
    if corruption == "wrong_run":
        saved["run_id"] = "another-run"
    else:
        saved["metrics"]["percent_in_zone"] = 999999
    atomic_write_json(root / "runs" / run_id / "evaluation" / "replay.json", saved)
    before = snapshot(root)
    view = load_evaluation_view(root, run_id)
    assert view["evaluation"] is view["profile"] is None
    assert "does not match" in view["evaluation_error"]
    assert snapshot(root) == before


def test_evaluation_page_completion_flow_and_selected_run(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    run_id = complete(root, config, top, base)
    script = f'''
import streamlit as st
from app.pages.evaluation import render
from app.ui.workspace import remember_selected_run
remember_selected_run(st.session_state, {str(root)!r}, {run_id!r})
render({str(root)!r})
'''
    app = AppTest.from_string(script, default_timeout=15).run()
    assert not app.exception
    assert not app.warning
    assert any("Acquisition is complete" in message.value for message in app.info)
    evaluate = next(button for button in app.button if button.label == "Evaluate completed run against withheld truth")
    evaluate.click().run()
    assert not app.exception
    assert any(metric.label == "True lateral in zone" for metric in app.metric)
    assert any("fixed-path replay" in message.value for message in app.info)
    result = json.loads((Path(root) / "runs" / run_id / "evaluation" / "replay.json").read_text())
    assert result["run_id"] == run_id


def test_replay_dls_display_matches_independent_scoring_bound(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    run_id = complete(root, config.model_copy(update={"max_dls_deg_per_100ft": 1.0}), top, base)
    evaluate_and_save(root, run_id)
    view = load_evaluation_view(root, run_id)
    assert view["profile"]["lateral_dls_limit"] == 3.0
    assert view["profile"]["command_dls_limit"] is None
