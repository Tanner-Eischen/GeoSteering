"""Actual form handlers and report services, with no Streamlit/UI automation."""

from __future__ import annotations

import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from pypdf import PdfReader

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import atomic_write_json
from app.services import operator_workflow, runs
from app.services.evaluation import evaluate_completed_run
from app.services.operator_workflow import export_selected_report, load_operator_view, submit_steering
from app.services.run_paths import run_root
from app.services.runs import initialize_run
from tests.test_run_history import prepare_run


def request(view, **changes):
    return {
        "run_id": view["state"].run_id, "expected_step_index": view["state"].step_index,
        "interpretation_version_id": view["interpretation"].version_id,
        "action": "HOLD", "observations": "Current acquired observations support inclination",
        **changes,
    }


def json_snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*.json")}


def pdf_text(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def test_view_and_form_edit_retry_remain_bound_after_later_steps_and_active_switch(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    selected = runs.active_run_id(root)
    view = load_operator_view(root, selected)
    x = float(view["frames"]["trajectory"].iloc[-1].x_ft)
    top_tvd = float(evaluate_piecewise_linear(top, [x])[0])
    base_tvd = float(evaluate_piecewise_linear(base, [x])[0])
    first_request = request(view, rationale="Observed local correction", update_bounds=(x, top_tvd + 0.5, base_tvd + 0.5))
    first = submit_steering(root, **first_request)
    second_view = load_operator_view(root, selected)
    submit_steering(root, **request(second_view, rationale="Later independent correction",
                                   update_bounds=(x + 100, top_tvd + 1, base_tvd + 1)))
    alternate = initialize_run(root, config, top, base)
    old_view = load_operator_view(root, selected)
    assert old_view["state"].run_id == old_view["config"].run_id == selected
    assert old_view["state"].step_index == len(old_view["metrics"]) == 2
    assert old_view["frames"]["trajectory"].md_ft.max() == old_view["state"].revealed_md_ft
    before = json_snapshot(root)
    assert submit_steering(root, **first_request) == first
    assert json_snapshot(root) == before
    assert runs.active_run_id(root) == alternate.run_id


def test_form_rejects_another_runs_displayed_interpretation_without_writes(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    first = load_operator_view(root, runs.active_run_id(root))
    other = initialize_run(root, config, top, base)
    before = json_snapshot(root)
    with pytest.raises(ValueError, match="interpretation does not match"):
        submit_steering(root, **{**request(first), "run_id": other.run_id})
    assert json_snapshot(root) == before


@pytest.mark.parametrize("step", (True, 0.5))
def test_form_step_types_are_checked_before_interpretation_indexing(tmp_path, step):
    root, _, _, _ = prepare_run(tmp_path)
    view = load_operator_view(root, runs.active_run_id(root))
    before = json_snapshot(root)
    with pytest.raises(ValueError, match="nonnegative integer"):
        submit_steering(root, **request(view, expected_step_index=step))
    assert json_snapshot(root) == before


def test_form_to_partial_complete_unevaluated_evaluated_export_and_reopen(tmp_path):
    root, config, top, base = prepare_run(tmp_path)
    # Two real replay intervals complete the existing 5,000-ft scoring domain.
    selected = initialize_run(root, config.model_copy(update={"step_size_ft": 2500.0}), top, base)
    submit_steering(root, **request(load_operator_view(root, selected.run_id)))
    alternate = initialize_run(root, config, top, base)
    partial = pdf_text(export_selected_report(root, run_id=selected.run_id, include_steps=[1]))
    assert selected.run_id in partial and alternate.run_id not in partial
    assert "PARTIAL / exploratory" in partial
    assert "Withheld truth evaluation unavailable until completion" in partial
    assert "final_interpretation_mean_absolute_error_ft" not in partial
    submit_steering(root, **request(load_operator_view(root, selected.run_id)))
    completed = pdf_text(export_selected_report(root, run_id=selected.run_id))
    assert "Status: COMPLETE" in completed
    assert "independent withheld-truth evaluation has not been saved" in completed
    assert "This partial report contains estimated metrics only" not in completed
    assert "final_interpretation_mean_absolute_error_ft" not in completed
    evaluation = evaluate_completed_run(root, run_id=selected.run_id)
    atomic_write_json(run_root(root, selected.run_id) / "evaluation/replay.json", evaluation)
    evaluated = pdf_text(export_selected_report(root, run_id=selected.run_id))
    assert "final_interpretation_mean_absolute_error_ft" in evaluated
    assert "has not been saved" not in evaluated
    assert runs.active_run_id(root) == alternate.run_id
    relocated = tmp_path / "reopened"
    shutil.copytree(root, relocated)
    reopened = load_operator_view(relocated, selected.run_id)
    assert reopened["state"].complete and reopened["state"].step_index == 2
    assert selected.run_id in pdf_text(export_selected_report(relocated, run_id=selected.run_id))


def test_export_form_requires_a_run_instead_of_falling_back_to_active(tmp_path):
    root, _, _, _ = prepare_run(tmp_path)
    before = json_snapshot(root)
    with pytest.raises(ValueError, match="Select a saved run"):
        export_selected_report(root, run_id=None)
    assert json_snapshot(root) == before


def test_operator_view_waits_for_same_process_advance_instead_of_mixing_documents(tmp_path, monkeypatch):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    selected = runs.active_run_id(root)
    form = request(load_operator_view(root, selected))
    saving, release, reader_started, reading = (threading.Event() for _ in range(4))
    original_save = runs.save_simulation_state
    original_load = operator_workflow.load_simulation_config

    def delayed_save(*args, **kwargs):
        saving.set()
        assert release.wait(5)
        return original_save(*args, **kwargs)

    def read_config(*args, **kwargs):
        reading.set()
        return original_load(*args, **kwargs)

    def read_view():
        reader_started.set()
        return load_operator_view(root, selected)

    monkeypatch.setattr(runs, "save_simulation_state", delayed_save)
    monkeypatch.setattr(operator_workflow, "load_simulation_config", read_config)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(submit_steering, root, **form)
        assert saving.wait(5)
        reader = pool.submit(read_view)
        try:
            assert reader_started.wait(2)
            assert not reading.wait(0.1)
        finally:
            release.set()
        writer.result()
        view = reader.result()
    assert reading.is_set()
    assert view["state"].step_index == len(view["metrics"]) == 1
    assert view["frames"]["trajectory"].md_ft.max() == view["state"].revealed_md_ft
