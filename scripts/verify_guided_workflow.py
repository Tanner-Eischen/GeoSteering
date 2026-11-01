"""Verify saved installed-backend results with a separate midpoint score witness."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from app.geo.formation import Scenario, formation_top_base
from tools.release_verify import verify_project


def verify(project: Path) -> dict:
    # Reuse all existing provenance, history, export and analytic-control checks.
    existing = verify_project(project, require_packaged=True)
    artifacts = json.loads((project / "exports/artifacts.json").read_text())
    scope = project / "runs" / artifacts["run_id"]
    config = json.loads((scope / "simulations/simulation_config.json").read_text())
    truth_path = (scope / config["hidden_truth_path"]).resolve()
    if not truth_path.is_relative_to(scope.resolve()):
        raise ValueError("Evaluation truth must belong to the selected isolated run")
    payload = json.loads(truth_path.read_text())
    scenario = Scenario.model_validate(payload.get("scenario", payload))
    comparison = json.loads((scope / "evaluation/comparison.json").read_text())
    checks = {}
    for name, result in comparison["runs"].items():
        trajectory, decisions, measured = result["trajectory"], result["decisions"], result["metrics"]
        if len(decisions) != 100:
            raise ValueError("Reference causal comparison must contain 100 decisions per strategy")
        if not all(d["observation"]["md_ft"] == d["md_from_ft"] for d in decisions):
            raise ValueError("Causal decision observation does not match decision-time depth")
        if not all(a["md_to_ft"] == b["md_from_ft"] for a, b in zip(decisions, decisions[1:])):
            raise ValueError("Causal decision intervals are not contiguous")
        md = np.array([row["md_ft"] for row in trajectory])
        x = np.array([row["x_ft"] for row in trajectory])
        tvd = np.array([row["tvd_ft"] for row in trajectory])
        if np.any(np.diff(md) <= 0) or md[-1] != 7000:
            raise ValueError("Stored causal trajectory has invalid depth coverage")
        # This does not call the policy, simulator, or production score integrator.
        # The same declared truth field is sampled at 50,000 lateral midpoints.
        midpoint = np.arange(2000.05, 7000.0, 0.1)
        observed_x, observed_tvd = np.interp(midpoint, md, x), np.interp(midpoint, md, tvd)
        top, base = formation_top_base(observed_x, scenario)
        percent = float(np.mean((observed_tvd >= top) & (observed_tvd <= base)) * 100)
        center = float(np.mean(np.abs(observed_tvd - (top + base) / 2)))
        if abs(percent - measured["percent_in_zone"]) >= 0.01:
            raise ValueError("Midpoint length tally differs by at least 0.01 percentage points")
        if abs(center - measured["avg_center_distance_ft"]) >= 0.01:
            raise ValueError("Midpoint center-distance tally differs by at least 0.01 ft")
        max_dls = max(row["dls_deg_per_100ft"] for row in trajectory if row["md_ft"] > 2000)
        if max_dls > 3 + 1e-8:
            raise ValueError("Stored lateral trajectory violates its separate DLS bound")
        if measured["evaluated_length_ft"] != 5000 or not math.isclose(
            measured["in_zone_length_ft"] / 5000 * 100, measured["percent_in_zone"], abs_tol=1e-10,
        ):
            raise ValueError("Stored causal length/percentage/denominator disagree")
        checks[name] = {
            "decision_rows": len(decisions), "midpoint_samples": len(midpoint),
            "midpoint_percent_in_zone": percent, "reported_percent_in_zone": measured["percent_in_zone"],
            "difference_percentage_points": percent - measured["percent_in_zone"],
            "midpoint_mean_center_distance_ft": center,
            "reported_mean_center_distance_ft": measured["avg_center_distance_ft"],
            "max_lateral_dls_deg_per_100ft": max_dls,
        }
    if comparison["runs"]["hold"]["trajectory"][:41] != comparison["runs"]["guided"]["trajectory"][:41]:
        raise ValueError("Causal strategies do not share their original landing state")
    return {
        "schema_version": 1, "status": "passed", "existing_saved_case_verifier": existing,
        "additional_witness": "Independent 0.1-ft midpoint length tally over stored causal trajectories and declared truth field",
        "witness_percentage_point_tolerance": 0.01, "witness_center_distance_tolerance_ft": 0.01,
        "causal_checks": checks,
        "mode_boundary": "100-step immutable replay history is separate from both 100-decision causal strategy histories",
        "limitations": [
            "Read-only saved-case verification; this command does not generate a new simulation",
            "One synthetic scenario, seed 123, known signed GR calibration, assumed uncertainty",
            "Midpoint witness shares the declared truth-field implementation; it is not independent field validation",
            "Browser actions, duplicate browser submissions and visual PDF layout are unverified",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--write", type=Path, required=True)
    args = parser.parse_args()
    if args.write.exists():
        raise FileExistsError("Choose an unused verification output")
    record = verify(args.project)
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "causal_checks": record["causal_checks"]}, indent=2))
