from __future__ import annotations

import json
from pathlib import Path

from tools.bootstrap_demo_project import bootstrap_demo_project
from tools.generate_sample_data import generate_sample_data


def test_end_to_end_demo_pipeline(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample_project"
    project_root = tmp_path / "demo_project"
    generate_sample_data(sample_root, seed=123)
    report_path = bootstrap_demo_project(project_root=project_root, sample_root=sample_root, steps=10)

    assert report_path.exists()
    assert report_path.stat().st_size > 3000
    assert (project_root / "exports" / "plan_demo.csv").exists()
    assert (project_root / "exports" / "decision_log.csv").exists()
    assert (project_root / "exports" / "kpi_summary.json").exists()

    kpi = json.loads((project_root / "exports" / "kpi_summary.json").read_text(encoding="utf-8"))
    assert "percent_in_zone" in kpi
    assert "avg_center_distance" in kpi

