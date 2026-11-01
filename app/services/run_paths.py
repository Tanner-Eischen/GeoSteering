"""Resolve immutable run histories without confusing them with project input data."""

from __future__ import annotations

from pathlib import Path

from app.io.project_store import read_json


def active_run_id(project_root: str | Path) -> str | None:
    pointer = read_json(Path(project_root) / "active_run.json", default={})
    return pointer.get("run_id")


def run_root(project_root: str | Path, run_id: str | None = None) -> Path:
    root = Path(project_root)
    selected = run_id or active_run_id(root)
    if selected is None:
        return root
    if not selected or Path(selected).name != selected or selected in {".", ".."}:
        raise ValueError("Invalid run ID")
    return root / "runs" / selected
