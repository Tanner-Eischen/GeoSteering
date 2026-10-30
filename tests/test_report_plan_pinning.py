from __future__ import annotations

import pytest

from app.io.project_store import atomic_write_json, create_project
from app.report.context import report_context


def _project(tmp_path, pinned=None):
    root = tmp_path / "project"
    create_project(root, "Report plan selection")
    scope = root / "runs" / "run-a"
    atomic_write_json(scope / "simulations" / "simulation_config.json", {"plan_id": pinned})
    atomic_write_json(scope / "simulations" / "simulation_state.json", {"revealed_md_ft": 2000})
    for identifier, timestamp in [("original", "2026-01-01"), ("later", "2026-02-01")]:
        atomic_write_json(root / "plans" / f"{identifier}.json",
                          {"plan_id": identifier, "name": identifier, "created_at": timestamp})
    return root


def test_run_with_no_plan_does_not_adopt_a_new_project_plan(tmp_path):
    root = _project(tmp_path)
    assert report_context(root, run_id="run-a")["plan"] is None


def test_run_plan_remains_pinned_after_other_plans_are_saved(tmp_path):
    root = _project(tmp_path, pinned="original")
    assert report_context(root, run_id="run-a")["plan"]["plan_id"] == "original"
    # An explicit export override remains supported and is shown in the report.
    assert report_context(root, run_id="run-a", plan_id="later")["plan"]["plan_id"] == "later"


def test_missing_pinned_plan_fails_instead_of_substituting_another(tmp_path):
    root = _project(tmp_path, pinned="deleted-plan")
    with pytest.raises(ValueError, match="Pinned plan is missing"):
        report_context(root, run_id="run-a")


def test_legacy_project_without_a_run_retains_latest_plan_fallback(tmp_path):
    root = _project(tmp_path)
    assert report_context(root)["plan"]["plan_id"] == "later"
