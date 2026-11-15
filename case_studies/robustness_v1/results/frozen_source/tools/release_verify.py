"""Read-only release checks for the fixed structural_dip_01 seed-123 study."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pypdf import PdfReader

from app.alg.kpi import compute_kpis
from app.alg.trajectory_min_curve import compute_trajectory
from app.io.project_store import read_json
from app.model.schemas import ControlPoint
from app.plan.plan_store import load_plan
from app.services.decisions import load_decisions
from app.services.evaluation import evaluate_completed_run
from app.services.interpretations import load_interpretations
from app.services.project_data import load_well_frames
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.sim.sim_store import load_simulation_config, load_simulation_state
from tools.release_provenance import describe_code

REFERENCE = {"hold": 38.07162079659706, "guided": 97.17426567844367}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_references():
    radius, degrees = 1000.0, np.linspace(0.0, 37.0, 38)
    radians = np.deg2rad(degrees)
    survey = pd.DataFrame({"md_ft": radius * radians, "inc_deg": degrees, "azi_deg": 90.0})
    trajectory = compute_trajectory(survey)
    position_error = max(
        float(np.max(np.abs(trajectory.tvd_ft - radius * np.sin(radians)))),
        float(np.max(np.abs(trajectory.east_ft - radius * (1 - np.cos(radians))))),
    )
    require(position_error < 1e-8, "Circular reference exceeds 1e-8 ft tolerance")
    tiny = compute_trajectory(pd.DataFrame({"md_ft": [0.0, 100.0], "inc_deg": [0.0, 1e-7], "azi_deg": [0.0, 0.0]}))
    require(math.isclose(tiny.iloc[-1].dls_deg_per_100ft, 1e-7, rel_tol=1e-12), "Tiny DLS lost")
    straight = pd.DataFrame({"md_ft": [0.0, 100.0], "tvd_ft": [0.0, 100.0]})
    top = [ControlPoint(md_ft=x, tvd_ft=40.0) for x in (0.0, 100.0)]
    base = [ControlPoint(md_ft=x, tvd_ft=60.0) for x in (0.0, 100.0)]
    metric = compute_kpis(straight, top, base, 0.0, 100.0)
    require(
        math.isclose(metric.percent_in_zone, 20.0, abs_tol=1e-10)
        and math.isclose(metric.avg_center_distance, 25.0, abs_tol=1e-10),
        "Independent interval integral failed",
    )
    return {
        "circular_radius_ft": radius,
        "circular_angle_deg": 37.0,
        "max_position_error_ft": position_error,
        "position_tolerance_ft": 1e-8,
        "tiny_expected_dls_deg_per_100ft": 1e-7,
        "tiny_actual_dls_deg_per_100ft": float(tiny.iloc[-1].dls_deg_per_100ft),
        "analytic_in_zone_percent": metric.percent_in_zone,
        "analytic_mean_center_distance_ft": metric.avg_center_distance,
    }


def verify_project(project, *, require_packaged=False):
    project = Path(project).resolve()
    artifacts = read_json(project / "exports/artifacts.json")
    run_id, plan_id = artifacts["run_id"], artifacts["plan_id"]
    scope = run_root(project, run_id)
    summary = read_json(project / "exports/summary.json")
    state = load_simulation_state(project, run_id)
    config = load_simulation_config(project, run_id)
    require(
        summary["complete"] and state.complete and state.step_index == summary["steps"] == 100,
        "Incomplete release study",
    )
    require(
        summary["scenario_version"] == "structural_dip_01-v1" and summary["seed"] == 123,
        "Unexpected release scenario/seed",
    )
    require(state.revealed_md_ft == summary["revealed_md_ft"] == 7000.0, "Wrong revealed MD")
    require(config.run_id == run_id and config.plan_id == plan_id, "Pinned run/plan mismatch")
    truth = Path(config.hidden_truth_path).resolve()
    require(truth.is_relative_to(scope.resolve()) and truth.is_file(), "Captured truth escapes relocated run")
    manifest = read_json(scope / "manifest.json")
    provenance = describe_code()
    require(
        manifest["code_provenance"]["source_fingerprint"] == provenance["source_fingerprint"],
        "Run source differs from executing code",
    )
    if require_packaged:
        require(
            provenance["basis"] == "verified_packaged_source_manifest" and provenance["runtime_git_revision"] is None,
            "Verification must execute installed package outside Git",
        )
    for relative, digest in manifest["input_hashes"].items():
        path = (scope / relative).resolve()
        require(
            path.is_relative_to(scope.resolve()) and path.is_file() and sha(path) == digest,
            f"Input hash mismatch: {relative}",
        )
    decisions = load_decisions(project, run_id)
    metrics = load_run_metrics(project, run_id)
    interpretations = {r.version_id: r for r in load_interpretations(project, run_id)}
    require(len(decisions) == len(metrics) == 100, "Missing decision or KPI row")
    require(
        state.version_id_by_step[1:] == [d.interpretation_version_id for d in decisions],
        "State interpretation links differ",
    )
    require(state.decision_id_by_step[1:] == [d.decision_id for d in decisions], "State decision links differ")
    require(
        summary["estimated_history"]
        == [
            {k: v for k, v in row.items() if k not in {"run_id", "interpretation_version_id", "decision_id"}}
            for row in metrics
        ],
        "Summary history differs from persisted metrics",
    )
    require(read_json(project / "exports/kpi_summary.json") == metrics[-1], "Final KPI export differs")
    frames = load_well_frames(project, config.active_well_id, run_id=run_id)
    kpi_checks = 0
    for decision, row in zip(decisions, metrics):
        require(
            row["decision_id"] == decision.decision_id
            and row["interpretation_version_id"] == decision.interpretation_version_id,
            "Decision/KPI links differ",
        )
        interpreted = interpretations[decision.interpretation_version_id]
        calculated = compute_kpis(
            frames["trajectory"],
            interpreted.top_control_points,
            interpreted.base_control_points,
            row["md_from_ft"],
            row["md_to_ft"],
        )
        for field in (
            "percent_in_zone",
            "avg_center_distance",
            "last_step_in_zone",
            "in_zone_length_ft",
            "evaluated_length_ft",
            "max_overshoot_ft",
        ):
            require(
                math.isclose(getattr(calculated, field), row[field], rel_tol=1e-12, abs_tol=1e-9),
                f"KPI calculation mismatch: {field}",
            )
            kpi_checks += 1
    with (project / "exports/decision_log.csv").open(newline="", encoding="utf8") as stream:
        exported = list(csv.DictReader(stream))
    require(len(exported) == len(decisions), "Decision CSV row count differs")
    for row, d in zip(exported, decisions):
        expected = {
            "step_index": d.step_index,
            "md_from_ft": d.md_from_ft,
            "md_to_ft": d.md_to_ft,
            "revealed_md_ft": d.md_from_ft,
            "curves_used": "",
            "offsets_used": "",
            "interpretation_version_id": d.interpretation_version_id,
            "interpretation_delta_summary": "",
            "recommendation_action": d.recommendation.action,
            "target_inc_deg": d.recommendation.target_inc_deg,
            "target_azi_deg": d.recommendation.target_azi_deg,
            "observations": d.observations,
            "risk_note": d.risk_note,
            "created_at": d.created_at,
        }
        require(set(row) == set(expected), "Decision CSV columns differ")
        for key, value in expected.items():
            if isinstance(value, datetime):
                require(datetime.fromisoformat(row[key].replace("Z", "+00:00")) == value, "Decision timestamp differs")
            elif isinstance(value, (int, float)):
                require(float(row[key]) == value, f"Decision CSV value differs: {key}")
            else:
                require(row[key] == ("" if value is None else value), f"Decision CSV value differs: {key}")
    plan, stations = load_plan(project, plan_id)
    plan_csv = pd.read_csv(project / "exports/plan_demo.csv")
    require(len(plan_csv) == len(stations) and len(stations) > 1, "Plan CSV count differs")
    require(
        list(plan_csv) == ["md_ft", "inc_deg", "azi_deg", "tvd_ft", "north_ft", "east_ft", "dls_deg_per_100ft"],
        "Plan CSV columns differ",
    )
    for column in plan_csv:
        require(
            np.allclose(plan_csv[column], stations[column], rtol=1e-12, atol=1e-9), f"Plan CSV value differs: {column}"
        )
    comparison = read_json(scope / "evaluation/comparison.json")["runs"]
    require(
        summary["causal_comparison"] == {name: r["metrics"] for name, r in comparison.items()},
        "Comparison summary differs",
    )
    for name, expected in REFERENCE.items():
        result = comparison[name]["metrics"]
        require(abs(result["percent_in_zone"] - expected) < 1e-6, f"Independent frozen reference differs: {name}")
        require(
            result["evaluated_length_ft"] == 5000.0 and result["dls_violation_count"] == 0,
            f"Denominator/constraint differs: {name}",
        )
    persisted_evaluation = read_json(scope / "evaluation/replay.json")
    fresh_evaluation = evaluate_completed_run(project, run_id=run_id)
    require(
        all(persisted_evaluation.get(k) == v for k, v in fresh_evaluation.items()),
        "Fresh withheld-truth evaluation differs",
    )
    require(
        summary["replay_evaluation"] == {k: v for k, v in persisted_evaluation.items() if k != "run_id"},
        "Replay summary differs",
    )
    pdf = (project / artifacts["report"]).resolve()
    require(pdf.is_relative_to(project), "Report path escapes project")
    reader = PdfReader(pdf)
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    flat = re.sub(r"\s+", " ", text)
    for token in (
        "COMPLETE",
        "Independent evaluation",
        "SHA-256",
        "LOCAL_TVD",
        "seed: 123",
        run_id,
        plan_id,
        "not a calibrated",
        "5000-ft lateral",
        "38.07%",
        "97.17%",
    ):
        require(token in flat, f"PDF omitted required value: {token}")
    for row in metrics:
        expected = f"{row['step_index']} {row['revealed_md_ft']:.0f} {row['percent_in_zone']:.3f} {row['avg_center_distance']:.3f}"
        require(expected in flat, f"PDF KPI row differs: {row['step_index']}")
    for name, run in comparison.items():
        m = run["metrics"]
        row = f"{name} {m['percent_in_zone']:.3f} {m['in_zone_length_ft']:.1f} / {m['evaluated_length_ft']:.1f} {m['max_dls_deg_per_100ft']:.4f}"
        require(row in flat, f"PDF comparison row differs: {name}")
    figures = sum(len(p.images) for p in reader.pages)
    require(figures >= 7, "PDF missing figures")
    require(not re.search(r"(?:[A-Za-z]:[\\/](?:Users|home)[\\/]|/home/)", text), "Report contains owner path")
    return {
        "schema_version": 1,
        "status": "passed",
        "run_id": run_id,
        "plan_id": plan_id,
        "source_provenance": provenance,
        "decision_rows": len(decisions),
        "decision_csv_fields_checked": len(exported) * 15,
        "plan_rows": len(plan_csv),
        "plan_csv_values_checked": len(plan_csv) * 7,
        "kpi_values_recomputed": kpi_checks,
        "pdf_kpi_rows_checked": len(metrics),
        "pdf_pages": len(reader.pages),
        "pdf_figures": figures,
        "pdf_sha256": sha(pdf),
        "summary_sha256": sha(project / "exports/summary.json"),
        "causal_comparison": summary["causal_comparison"],
        "independent_references": independent_references(),
        "browser_used": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, nargs="?")
    parser.add_argument("--write", type=Path)
    parser.add_argument("--require-packaged", action="store_true")
    args = parser.parse_args()
    result = (
        verify_project(args.project, require_packaged=args.require_packaged)
        if args.project
        else independent_references()
    )
    if args.write:
        if args.write.exists():
            raise FileExistsError("Choose an unused proof output")
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
