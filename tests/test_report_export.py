from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

from app.io.project_store import create_project, load_project
from app.io.well_import import import_well_folder
from app.model.schemas import ControlPoint
from app.plan.plan_generator import generate_plan
from app.plan.plan_store import save_plan
from app.report.report_builder import build_report
from app.services.decisions import create_decision
from app.services.interpretations import create_baseline_interpretation
from app.services.project_data import load_well_frames
from tools.generate_sample_data import generate_sample_data


def _setup_project_with_content(tmp_path: Path) -> Path:
    sample_root = tmp_path / "sample"
    generate_sample_data(sample_root, seed=123)
    project_root = tmp_path / "project"
    create_project(project_root, "ReportDemo")
    for name in ["active_01", "offset_01", "offset_02", "offset_03"]:
        import_well_folder(project_root, sample_root / "wells" / name, name)

    params = {
        "kickoff_md_ft": 1000.0,
        "landing_md_ft": 3000.0,
        "lateral_length_ft": 5000.0,
        "planned_azi_deg": 90.0,
        "step_ft": 100.0,
    }
    from app.model.schemas import PlanParameters

    plan_params = PlanParameters(**params)
    generated = generate_plan(plan_params, dls_max_deg_per_100ft=3.0)
    save_plan(
        project_root,
        name="PlanForReport",
        parameters=plan_params,
        stations=generated.stations,
        dls_max_deg_per_100ft=3.0,
        exceedances=generated.exceedances,
    )

    project = load_project(project_root)
    active_id = next(w.well_id for w in project.wells if w.name == "active_01")
    traj = load_well_frames(project_root, active_id)["trajectory"]
    md_min, md_max = float(traj["md_ft"].min()), float(traj["md_ft"].max())
    baseline = create_baseline_interpretation(
        project_root,
        top_control_points=[ControlPoint(md_ft=md_min, tvd_ft=1250.0), ControlPoint(md_ft=md_max, tvd_ft=1250.0)],
        base_control_points=[ControlPoint(md_ft=md_min, tvd_ft=1270.0), ControlPoint(md_ft=md_max, tvd_ft=1270.0)],
    )
    create_decision(
        project_root,
        step_index=1,
        md_from_ft=1000.0,
        md_to_ft=1100.0,
        interpretation_version_id=baseline.version_id,
        observations="Hold trajectory",
        action="HOLD",
    )
    return project_root


def test_report_export_headless_and_sections(tmp_path: Path) -> None:
    project_root = _setup_project_with_content(tmp_path)
    out = build_report(project_root)
    assert out.exists()
    assert out.stat().st_size > 3_000

    text = ""
    reader = PdfReader(str(out))
    for page in reader.pages:
        text += page.extract_text() or ""

    for header in [
        "Data summary and QC",
        "Correlation and markers",
        "Pre-spud plan and DLS",
        "Steering decisions and KPI results",
        "Assumptions and limitations",
    ]:
        assert header in text


def test_report_export_cli(tmp_path: Path) -> None:
    project_root = _setup_project_with_content(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "tools.export_report", str(project_root)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Report exported" in result.stdout
    pdfs = list((project_root / "exports").glob("report_*.pdf"))
    assert pdfs
