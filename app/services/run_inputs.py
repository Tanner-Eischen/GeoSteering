"""Immutable acquired-input snapshots for reproducible runs and reports."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from app.io.project_store import atomic_write_json, well_paths


def snapshot_run_inputs(project_root, scope, well_ids) -> None:
    for well_id in sorted(set(well_ids)):
        destination = Path(scope) / "inputs" / "wells" / well_id
        destination.mkdir(parents=True, exist_ok=False)
        for path in well_paths(project_root, well_id).values():
            if path.is_file():
                shutil.copyfile(path, destination / path.name)
        if not (destination / "markers.json").exists():
            atomic_write_json(destination / "markers.json", [])


def input_paths(project_root, scope, well_id) -> dict[str, Path]:
    original = well_paths(project_root, well_id)
    captured = Path(scope) / "inputs" / "wells" / well_id
    if captured.is_dir():
        return {key: captured / path.name for key, path in original.items()}
    return original


def describe_run_inputs(scope, config) -> dict:
    repository = Path(__file__).resolve().parents[2]
    def git(*arguments):
        try:
            result = subprocess.run(["git", *arguments], cwd=repository, capture_output=True, text=True, check=False)
            return result.stdout.strip() if result.returncode == 0 else None
        except OSError:
            return None
    revision = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    paths = sorted((Path(scope) / "inputs").rglob("*"))
    return {
        "run_id": config.run_id, "plan_id": config.plan_id, "mode": config.mode,
        "seed": config.seed, "scenario_version": config.scenario_version,
        "code_revision": revision or "unavailable",
        "dirty_working_tree": None if status is None else bool(status),
        "coordinate_reference": "LOCAL_EAST_NORTH_FT; shared declared vertical datum; TVD positive down",
        "input_hashes": {p.relative_to(scope).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()},
        "uncertainty_note": "Scenario-assumed range, not a calibrated confidence interval",
    }
