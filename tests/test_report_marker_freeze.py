from __future__ import annotations

from pypdf import PdfReader

from app.io.project_store import atomic_write_json
from app.model.schemas import Marker
from app.report.context import report_context, report_markers
from app.report.report_builder import build_report
from app.services.markers import edit_marker, load_markers
from tools.run_case_study import run_case_study


def test_old_run_marker_evidence_and_figures_survive_current_marker_edits(tmp_path):
    run_case_study(tmp_path / "case", steps=1)
    root = tmp_path / "case" / "project"
    context = report_context(root)
    offset = next(well for well in context["wells"] if well.name == "offset_01")
    original = report_markers(context, offset.well_id)
    directory = context["scope"] / "cache" / "report_snapshots"
    correlation = (directory / "correlation_snapshot.png").read_bytes()
    interpretation = (directory / "interpretation_overlay.png").read_bytes()
    pick = original[0]
    edit_marker(root, offset.well_id, pick.marker_id, name="EditedAfterRun", md_ft=pick.md_ft + 3.0)
    assert load_markers(root, offset.well_id) != original
    assert report_markers(report_context(root), offset.well_id) == original
    regenerated = build_report(root, run_id=context["run_id"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(regenerated).pages)
    assert "EditedAfterRun" not in text
    assert (directory / "correlation_snapshot.png").read_bytes() == correlation
    assert (directory / "interpretation_overlay.png").read_bytes() == interpretation


def test_empty_run_marker_snapshot_stays_empty_with_legacy_fallback(tmp_path):
    context = {"root": tmp_path / "project", "scope": tmp_path / "run"}
    marker = Marker(name="Added later", md_ft=200.0)
    atomic_write_json(context["root"] / "wells" / "well-a" / "markers.json", [marker.model_dump(mode="json")])
    assert report_markers(context, "well-a") == [marker]
    atomic_write_json(context["scope"] / "inputs" / "wells" / "well-a" / "markers.json", [])
    assert report_markers(context, "well-a") == []
