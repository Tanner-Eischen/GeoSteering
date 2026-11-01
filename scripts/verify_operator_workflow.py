"""Exercise actual page handlers against an installed backend without a UI."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.io.project_store import atomic_write_json
from app.services.evaluation import evaluate_completed_run
from app.services.operator_workflow import export_selected_report, load_operator_view, submit_steering
from app.services.run_paths import run_root
from app.services.runs import initialize_run
from tools.release_provenance import ROOT, describe_code
from tools.run_case_study import run_case_study


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def text(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def verify(out):
    if out.exists():
        raise FileExistsError("Choose a fresh acceptance output")
    if ROOT.name != "site-packages":
        raise ValueError("Run this driver with the current installed wheel outside the checkout")
    out.mkdir(parents=True)
    provenance = describe_code()
    run_case_study(out / "bootstrap", seed=123, steps=0)
    project = out / "bootstrap/project"
    initial = json.loads((project / "exports/artifacts.json").read_text())
    baseline = load_operator_view(project, initial["run_id"])
    version = baseline["interpretation"]
    # Two genuine acquired replay intervals span the full supported truth domain.
    config = baseline["config"].model_copy(update={"step_size_ft": 2500.0})
    selected = initialize_run(project, config, version.top_control_points, version.base_control_points,
                              uncertainty_band_tvd_ft=version.uncertainty.band_tvd_ft)
    view = load_operator_view(project, selected.run_id)
    station = view["frames"]["trajectory"].iloc[-1]
    observed = view["frames"]["logs"].iloc[-1]
    x = float(station.x_ft)
    form = {
        "run_id": selected.run_id, "expected_step_index": 0,
        "interpretation_version_id": view["interpretation"].version_id,
        "action": "HOLD",
        "observations": f"Acquired MD {float(observed.md_ft):.1f} ft, GR {float(observed.GR):.6f} API",
        "rationale": "Operator workflow fixture: retain the observed offset-derived interval",
        "update_bounds": (x, float(evaluate_piecewise_linear(version.top_control_points, [x])[0]),
                          float(evaluate_piecewise_linear(version.base_control_points, [x])[0])),
    }
    first = submit_steering(project, **form)
    partial = export_selected_report(project, run_id=selected.run_id)
    assert "PARTIAL / exploratory" in text(partial)
    assert "final_interpretation_mean_absolute_error_ft" not in text(partial)
    shutil.copyfile(partial, out / "partial.pdf")
    next_view = load_operator_view(project, selected.run_id)
    current = next_view["frames"]["logs"].iloc[-1]
    submit_steering(
        project, run_id=selected.run_id, expected_step_index=1,
        interpretation_version_id=next_view["interpretation"].version_id,
        action="HOLD", observations=f"Acquired MD {float(current.md_ft):.1f} ft, GR {float(current.GR):.6f} API",
    )
    complete = export_selected_report(project, run_id=selected.run_id)
    assert "Status: COMPLETE" in text(complete) and "has not been saved for the selected run" in text(complete)
    shutil.copyfile(complete, out / "complete-unevaluated.pdf")
    alternate = initialize_run(project, config, version.top_control_points, version.base_control_points,
                               uncertainty_band_tvd_ft=version.uncertainty.band_tvd_ft)
    before_retry = hashes(project)
    assert submit_steering(project, **form) == first
    assert hashes(project) == before_retry
    evaluation = evaluate_completed_run(project, run_id=selected.run_id)
    atomic_write_json(run_root(project, selected.run_id) / "evaluation/replay.json", evaluation)
    completed = export_selected_report(project, run_id=selected.run_id)
    completed_text = text(completed)
    assert "final_interpretation_mean_absolute_error_ft" in completed_text
    assert alternate.run_id not in completed_text and selected.run_id in completed_text
    shutil.copyfile(completed, out / "complete-evaluated.pdf")
    relocated = out / "reopened-project"
    shutil.copytree(project, relocated)
    program = """
import json,sys
from app.services.operator_workflow import load_operator_view,export_selected_report
root,run_id=sys.argv[1:]
view=load_operator_view(root,run_id)
report=export_selected_report(root,run_id=run_id)
print(json.dumps({'run_id':view['state'].run_id,'step':view['state'].step_index,'complete':view['state'].complete,'report_exists':report.is_file()}))
"""
    reopened = subprocess.run([sys.executable, "-c", program, str(relocated.resolve()), selected.run_id],
                              cwd=out, capture_output=True, text=True, check=True, timeout=60)
    result = json.loads(reopened.stdout)
    assert result == {"run_id": selected.run_id, "step": 2, "complete": True, "report_exists": True}
    proof = {
        "schema_version": 1, "status": "passed", "source_provenance": provenance,
        "package_version": importlib.metadata.version("geosteering-workbench"),
        "scope": "Actual steering/report page handlers called directly through an installed backend; no UI events simulated",
        "workflow": "Acquired view -> edited form -> guarded advance -> partial report -> completion without evaluation -> independent evaluation -> selected report -> relocated fresh-process reopen",
        "selected_run_id": selected.run_id, "separate_active_run_id": alternate.run_id,
        "late_edited_form_retry": "original step1 receipt returned with all project file hashes unchanged",
        "project_files_checked_for_retry": len(before_retry), "reopened": result,
        "evaluation_interval_ft": evaluation["metrics"]["evaluated_length_ft"],
        "replay_limitation": "Two manual HOLD requests reveal a fixed path; this is handler integration, not a new policy comparison",
        "report_sha256": {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                          for name in ("partial.pdf", "complete-unevaluated.pdf", "complete-evaluated.pdf")},
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "not_verified": ["Browser/Streamlit widget behavior", "Visual PDF layout", "Multi-process writers", "Deployment"],
        "browser_used": False,
    }
    (out / "proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.out.resolve()), indent=2))
