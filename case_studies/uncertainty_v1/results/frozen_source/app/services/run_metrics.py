"""Version-specific decision-time diagnostics, never retrospective truth scores."""

from __future__ import annotations

from pathlib import Path

from app.io.project_store import append_only_write, read_json
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run


def load_run_metrics(project_root: str | Path, run_id: str | None = None) -> list[dict]:
    recover_run(run_root(project_root, run_id))
    return read_json(run_root(project_root, run_id) / "metrics.json", default=[])


def save_metric_snapshot(project_root: str | Path, snapshot: dict) -> None:
    snapshots = load_run_metrics(project_root)
    if any(row["step_index"] == snapshot["step_index"] for row in snapshots):
        raise ValueError("A metric snapshot already exists for this step")
    append_only_write(
        run_root(project_root) / "metrics.json", snapshots + [snapshot], key_fields=["step_index"]
    )
