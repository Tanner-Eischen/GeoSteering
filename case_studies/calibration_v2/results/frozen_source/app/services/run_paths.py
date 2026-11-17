"""Resolve immutable run histories without confusing them with project input data."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.io.project_store import read_json

_SELECTED_RUN: ContextVar[tuple[Path, str] | None] = ContextVar("selected_run", default=None)


def active_run_id(project_root: str | Path) -> str | None:
    pointer = read_json(Path(project_root) / "active_run.json", default={})
    return pointer.get("run_id")


def run_root(project_root: str | Path, run_id: str | None = None) -> Path:
    root = Path(project_root)
    context = _SELECTED_RUN.get()
    selected = run_id
    if selected is None:
        selected = context[1] if context and context[0] == root.resolve() else active_run_id(root)
    if selected is None:
        return root
    if not selected or Path(selected).name != selected or selected in {".", ".."}:
        raise ValueError("Invalid run ID")
    return root / "runs" / selected


@contextmanager
def selected_run(project_root: str | Path, run_id: str | None):
    """Pin service calls to one run without changing the project's active pointer."""
    root = Path(project_root)
    scope = run_root(root, run_id)
    selected = run_id if run_id is not None else active_run_id(root)
    token = _SELECTED_RUN.set((root.resolve(), selected) if selected is not None else None)
    try:
        yield scope
    finally:
        _SELECTED_RUN.reset(token)
