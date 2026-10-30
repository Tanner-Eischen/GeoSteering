from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from app.report.report_builder import build_report
from tools.run_case_study import run_case_study


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    out = tmp_path_factory.mktemp("scientific_report")
    report = run_case_study(out)
    project = out / "project"
    artifacts = json.loads((project / "exports" / "artifacts.json").read_text())
    return project, report, artifacts


def test_pdf_contains_actual_figures_methods_and_independent_outcomes(completed):
    project, report, artifacts = completed
    reader = PdfReader(report)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for required in [
        "COMPLETE",
        "Independent evaluation",
        "SHA-256",
        "LOCAL_TVD",
        "seed: 123",
        "Recommendations did not change",
        "not a calibrated",
        "hold",
        "guided",
    ]:
        assert required in text
    assert sum(len(page.images) for page in reader.pages) >= 7
    files = list((project / artifacts["figure_directory"]).glob("*.png"))
    assert len(files) >= 7
    for path in files:
        with Image.open(path) as image:
            assert image.width >= 1000 and image.height >= 300
            assert any(lo != hi for lo, hi in image.convert("RGB").getextrema())
    summary = json.loads((project / "exports" / "summary.json").read_text())
    comparison = summary["causal_comparison"]
    assert comparison["guided"]["dls_violation_count"] == comparison["hold"]["dls_violation_count"] == 0
    assert comparison["guided"]["evaluated_length_ft"] == comparison["hold"]["evaluated_length_ft"] == 5000.0
    expected = json.loads(
        (Path(__file__).parents[1] / "case_studies" / "structural_dip_01" / "expected.json").read_text()
    )
    for strategy, references in expected["causal_comparison"].items():
        for name, value in references.items():
            assert comparison[strategy][name] == pytest.approx(value, abs=1e-6)


def test_midrun_report_withholds_truth_and_applies_selection(tmp_path):
    report = run_case_study(tmp_path / "partial", steps=3)
    project = tmp_path / "partial" / "project"
    artifacts = json.loads((project / "exports" / "artifacts.json").read_text())
    scope = project / "runs" / artifacts["run_id"]
    assert not (scope / "evaluation").exists()
    text = "\n".join(page.extract_text() or "" for page in PdfReader(report).pages)
    assert "PARTIAL" in text
    assert "Withheld truth evaluation unavailable until completion" in text
    assert "final_interpretation_mean_absolute_error_ft" not in text
    selected = build_report(
        project,
        run_id=artifacts["run_id"],
        plan_id=artifacts["plan_id"],
        include_wells=["offset_01"],
        include_steps=[1],
    )
    selected_text = "\n".join(page.extract_text() or "" for page in PdfReader(selected).pages)
    assert "offset_01" in selected_text
    assert "offset_02" not in selected_text and "offset_03" not in selected_text
    with pytest.raises(ValueError, match="Unknown plan"):
        build_report(project, plan_id="does-not-exist")


def test_repeated_seed_produces_identical_numerical_summary(completed, tmp_path):
    project, _, _ = completed
    run_case_study(tmp_path / "repeat")
    first = json.loads((project / "exports" / "summary.json").read_text())
    second = json.loads((tmp_path / "repeat" / "project" / "exports" / "summary.json").read_text())
    assert first == second
    with pytest.raises(FileExistsError):
        run_case_study(tmp_path / "repeat")


def test_report_uses_selected_runs_active_well_and_reveal_bound(tmp_path):
    from app.services.interpretations import get_latest_interpretation
    from app.services.project_data import load_project_and_wells
    from app.services.runs import initialize_run
    from app.sim.sim_models import SimulationConfig

    run_case_study(tmp_path / "runs", steps=1)
    project = tmp_path / "runs" / "project"
    artifacts = json.loads((project / "exports" / "artifacts.json").read_text())
    previous = artifacts["run_id"]
    metadata, wells = load_project_and_wells(project)
    alternate = next(w for w in wells if w.name == "offset_01")
    interpretation = get_latest_interpretation(project, previous)
    config = SimulationConfig(active_well_id=alternate.well_id, start_md_ft=100.0, end_md_ft=300.0)
    state = initialize_run(project, config, interpretation.top_control_points, interpretation.base_control_points)
    # Alternate run active well is different from the project's original active well.
    assert alternate.well_id != metadata.active_well_id
    selected = build_report(project, run_id=state.run_id, include_wells=["offset_01"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(selected).pages)
    assert "100.0" in text
    assert "Top_A" not in text and "Base_A" not in text
    # An explicit prior run remains bounded and uses its own state despite a new active pointer.
    selected = build_report(project, run_id=previous, include_wells=["active_01"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(selected).pages)
    assert "2050.0" in text and previous in text


def test_required_figure_rendering_failure_stops_report(completed, monkeypatch):
    from matplotlib.figure import Figure

    project, _, artifacts = completed

    def unavailable(*args, **kwargs):
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(Figure, "savefig", unavailable)
    with pytest.raises(RuntimeError, match="renderer unavailable"):
        build_report(project, run_id=artifacts["run_id"], plan_id=artifacts["plan_id"], strict=True)
