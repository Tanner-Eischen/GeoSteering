"""Recoverable single-writer transactions for a persisted simulation advance.

Each step checkpoints the small mutable run documents before writing. Exceptions
restore the checkpoint. A process interrupted during a write leaves a journal;
the next read restores it unless its commit marker was durably written.
"""
from __future__ import annotations

import base64
from functools import wraps
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.io.project_store import atomic_write_json, read_json
from app.services.run_paths import run_root

_DOCUMENTS = (
    "interpretations/interpretations.json",
    "decisions/decisions.json",
    "metrics.json",
    "environment/state.json",
    "simulations/simulation_state.json",
)
_ACTIVE: set[str] = set()


def _restore(scope: Path, files: dict) -> None:
    for relative, encoded in files.items():
        if relative not in _DOCUMENTS:
            raise ValueError("Invalid transaction checkpoint path")
        target = scope / relative
        if encoded is None:
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="wb", dir=target.parent, delete=False, suffix=".recovery") as stream:
            stream.write(base64.b64decode(encoded, validate=True))
            temporary = Path(stream.name)
        temporary.replace(target)


def recover_run(scope: str | Path) -> None:
    scope = Path(scope)
    if str(scope.resolve()) in _ACTIVE:
        return
    journal = scope / "pending_step.json"
    if not journal.exists():
        return
    payload = read_json(journal)
    if payload["status"] == "pending":
        _restore(scope, payload["files"])
    elif payload["status"] != "committed":
        raise ValueError("Unknown step journal status")
    journal.unlink()


def atomic_run_step(function):
    @wraps(function)
    def wrapped(project_root, *args, **kwargs):
        scope = run_root(project_root)
        recover_run(scope)
        files = {
            relative: base64.b64encode((scope / relative).read_bytes()).decode("ascii")
            if (scope / relative).exists() else None
            for relative in _DOCUMENTS
        }
        journal = scope / "pending_step.json"
        atomic_write_json(journal, {"status": "pending", "files": files})
        key = str(scope.resolve())
        _ACTIVE.add(key)
        try:
            result = function(project_root, *args, **kwargs)
            atomic_write_json(journal, {"status": "committed"})
        except BaseException:
            _restore(scope, files)
            journal.unlink(missing_ok=True)
            raise
        else:
            journal.unlink(missing_ok=True)
            return result
        finally:
            _ACTIVE.discard(key)
    return wrapped
