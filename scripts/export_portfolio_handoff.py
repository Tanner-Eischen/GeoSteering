"""Export a public-safe reference packet without regenerating scientific results."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGURES = (
    "plan_profile", "dls_profile", "correlation_snapshot", "interpretation_overlay",
    "kpi_trend", "decision_timeline", "strategy_comparison",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def export(release, out):
    if out.exists():
        raise FileExistsError("Choose a new output directory; existing evidence is never overwritten")
    release_record = read_json(release / "release.json")
    provenance = read_json(ROOT / "app/_release_source.json")
    if provenance["source_fingerprint"] != release_record["source_provenance"]["source_fingerprint"]:
        raise ValueError("Current source and release fingerprints differ")
    for name, digest in provenance["source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f"Current source differs: {name}")
    checked = 0
    for line in (release / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        source = (release / name).resolve()
        if not source.is_relative_to(release.resolve()) or sha(source) != digest:
            raise ValueError("Release checksum validation failed")
        checked += 1

    project = release / "case-study/project"
    artifact = read_json(project / "exports/artifacts.json")
    manifest = read_json(project / "runs" / artifact["run_id"] / "manifest.json")
    summary = read_json(project / "exports/summary.json")
    # This existing verifier independently recomputes replay metrics and analytic
    # controls, checks all decision/KPI/plan rows and inspects PDF text/images.
    command = [sys.executable, "-m", "tools.release_verify", str(project)]
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    verification = json.loads(result.stdout)
    if verification["status"] != "passed":
        raise ValueError("Saved-case verification did not pass")
    report = project / artifact["report"]
    if sha(report) != verification["pdf_sha256"]:
        raise ValueError("Report does not match newly verified saved case")
    figures = project / artifact["figure_directory"]
    for name in FIGURES:
        if (figures / f"{name}.png").read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Missing PNG figure: {name}")

    out.mkdir(parents=True)
    (out / "figures").mkdir()
    shutil.copyfile(report, out / "report.pdf")
    shutil.copyfile(project / "exports/decision_log.csv", out / "replay-decisions.csv")
    for name in FIGURES:
        shutil.copyfile(figures / f"{name}.png", out / "figures" / f"{name}.png")
    for name in ("methods", "limitations"):
        shutil.copyfile(ROOT / "docs" / f"{name}.md", out / f"{name}.md")
    shutil.copyfile(ROOT / "LICENSE", out / "LICENSE")
    write_json(out / "verification.json", {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "newly_executed": "Existing read-only tools.release_verify against the saved release case",
        "release_files_hash_checked": checked,
        "current_python_source_files_hash_checked": len(provenance["source_sha256"]),
        "runtime_python": sys.version.split()[0],
        "result": verification,
        "not_executed": ["Fresh simulation generation", "Full pytest suite", "Clean installation",
                         "Browser/operator walkthrough", "Linux execution", "Publication"],
    })
    write_json(out / "summary.json", {
        "scenario_version": summary["scenario_version"], "seed": summary["seed"],
        "causal_comparison": summary["causal_comparison"],
        "replay_evaluation": summary["replay_evaluation"],
        "replay_steps": summary["steps"],
        "qualifier": "Single synthetic scenario with known signed GR calibration; not field validation",
    })
    write_json(out / "run-manifest.json", {
        key: manifest[key] for key in (
            "run_id", "plan_id", "mode", "scenario_version", "seed", "input_hashes",
            "sample_input_hashes", "code_revision", "dirty_working_tree", "coordinate_reference",
            "sensor_calibration", "uncertainty_note",
        )
    })
    limits = [
        "One idealized two-dimensional synthetic scenario and seed; no geological generalization claim",
        "Known signed GR calibration; 0.6 API Gaussian noise and clipping at 20-160 API",
        "Assumed uncertainty envelope, not a calibrated statistical interval",
        "Replay recommendations do not change the recorded trajectory",
        "Simplified causal kinematics; no operational safety or field-data performance claim",
        "Browser/operator walkthrough and Linux execution unverified",
        "Tested dirty source snapshot differs from the public base commit",
    ]
    assets = {
        p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
    }
    write_json(out / "portfolio-evidence.json", {
        "schema_version": 1, "project_id": "geosteering",
        "release_id": "structural-dip-01-seed123-handoff-2026-11-01",
        "status": "ready_for_owner_review_not_published",
        "implemented_contribution": "LAS/survey QC, offset interpretation, constrained planning, immutable replay history, bounded causal steering and independently scored reports",
        "source_revision": manifest["code_revision"],
        "tested_revision": None,
        "tested_source_fingerprint": provenance["source_fingerprint"],
        "dirty_source_snapshot": True,
        "source_revision_meaning": "Base Git ancestry; exact tested bytes identified by the fingerprint",
        "source_access": {
            "base_source_url": f"https://github.com/Tanner-Eischen/GeoSteering/tree/{manifest['code_revision']}",
            "base_repository_access": "public_per_plan_not_network_checked",
            "tested_snapshot_public": False, "packet_published": False,
            "public_artifact_urls": [], "owner_approval": "pending_review",
        },
        "scenario": {"id": summary["scenario_version"], "seed": summary["seed"],
                     "coordinate_reference": manifest["coordinate_reference"],
                     "sensor_model": "signed_calibrated_reference", "sensor_calibration": manifest["sensor_calibration"],
                     "evaluated_interval_md_ft": [2000, 7000], "denominator_ft": 5000,
                     "lateral_dls_limit_deg_per_100ft": 3, "landing_dls_limit_deg_per_100ft": 6},
        "headline_results": [
            {"metric": "lateral_in_zone", "value": values["percent_in_zone"], "unit": "percent",
             "policy": name, "mode": "causal_simulation", "denominator": 5000, "denominator_unit": "ft",
             "scope": "structural_dip_01-v1 synthetic scenario, seed 123, known signed GR calibration",
             "evidence": "summary.json#/causal_comparison/" + name,
             "qualification": "Synthetic reference comparison; not operational drilling performance"}
            for name, values in summary["causal_comparison"].items()
        ],
        "checks": {"new_saved_artifact_verification": "passed", "fresh_simulation": "not_run",
                   "historical_full_suite": "98 passed per owner release; not rerun",
                   "historical_clean_install": "Windows CPython 3.12.14 per owner release; not rerun",
                   "browser": "unverified", "model_calls": "not_applicable"},
        "limitations": limits,
        "assets": assets,
        "licenses": {"code_and_generated_report_assets": "MIT; see LICENSE", "raw_field_data": "excluded"},
        "last_verified_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    (out / "README.md").write_text(
        "# GeoSteering synthetic reference evidence\n\n"
        "Prepared November 1, 2026 for owner review. This local packet is not published.\n\n"
        "HOLD places 38.0716% and guided places 97.1743% of the same 5,000-ft synthetic lateral in zone. "
        "The guided policy knows a signed GR calibration. One 2D scenario and seed do not validate operational steering.\n\n"
        "Read portfolio-evidence.json for claim scope, source fingerprint, access state and asset hashes; "
        "summary.json for values; report.pdf and all seven figures for the same saved run. "
        "replay-decisions.csv is the immutable 100-step replay, not the causal guided history.\n\n"
        "verification.json records newly recomputed saved replay metrics, analytic geometry/integration controls, "
        "decision/KPI/plan checks and PDF text/images. The simulation, full suite, clean installation, "
        "browser journey and publication were not rerun. Historical test records remain historical.\n\n"
        "Methods and limitations are included. Reproduce using the repository's documented "
        "python -m tools.run_case_study --out output/new-reference --seed 123 command in a new output directory. "
        "The public base commit is ancestry; the tested dirty snapshot is identified by its source fingerprint. "
        "No raw Volve files, credentials or private task material are included.\n",
        encoding="utf-8",
    )
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".csv", ".md"}:
            if re.search(r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|file:///|/home/|/Users/)",
                         path.read_text(encoding="utf-8")):
                raise ValueError(f"Local path in packet: {path.name}")
    (out / "SHA256SUMS").write_text(
        "".join(f"{sha(p)}  {p.relative_to(out).as_posix()}\n"
                for p in sorted(out.rglob("*")) if p.is_file()), encoding="utf-8",
    )
    print(json.dumps({"status": "passed", "files": len(list(out.rglob("*"))),
                      "release_files_hash_checked": checked, "pdf_sha256": sha(out / "report.pdf")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export(args.release, args.out)
