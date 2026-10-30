from __future__ import annotations

import json
from pathlib import Path

from tools.bootstrap_demo_project import bootstrap_demo_project


def test_end_to_end_demo_pipeline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    report = bootstrap_demo_project(project, tmp_path / "sample")
    assert report.exists() and report.stat().st_size > 3000
    for name in ["plan_demo.csv", "decision_log.csv", "kpi_summary.json", "summary.json", "artifacts.json"]:
        assert (project / "exports" / name).is_file()
    summary = json.loads((project / "exports" / "summary.json").read_text())
    assert summary["complete"]
    assert summary["revealed_md_ft"] == 7000.0
    assert summary["steps"] == 100
    assert summary["replay_evaluation"]["metrics"]["evaluated_length_ft"] == 5000.0
    errors = summary["replay_evaluation"]["interpretation_error"]
    assert (
        errors["final_interpretation_mean_absolute_error_ft"] < errors["baseline_interpretation_mean_absolute_error_ft"]
    )
    history = summary["estimated_history"]
    assert len(history) == 100
    assert len({round(row["percent_in_zone"], 2) for row in history}) > 5
    assert {row["action"] for row in history} >= {"HOLD", "DROP"}
