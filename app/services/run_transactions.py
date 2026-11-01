"""Recoverable single-writer transactions for a persisted simulation advance.

Each step checkpoints the small mutable run documents before writing. Exceptions
restore the checkpoint. A process interrupted during a write leaves a journal;
the next read restores it unless its commit marker was durably written.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import re
import threading
from functools import wraps
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.io.project_store import append_only_write, atomic_write_json, read_json
from app.services.run_paths import selected_run

_DOCUMENTS = (
    "interpretations/interpretations.json",
    "decisions/decisions.json",
    "metrics.json",
    "environment/state.json",
    "simulations/simulation_state.json",
    "step_requests.json",
)
_ACTIVE: set[str] = set()
_LOCKS: dict[str, threading.RLock] = {}


def run_access_lock(scope):
    """Serialize same-process views/exports with an advance of this exact run."""
    return _LOCKS.setdefault(str(Path(scope).resolve()), threading.RLock())


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
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(project_root, *args, **kwargs):
        bound = signature.bind(project_root, *args, **kwargs)
        bound.apply_defaults()
        run_id = bound.arguments.get("run_id")
        expected = bound.arguments.get("expected_step_index")
        request_id = bound.arguments.get("request_id")
        guarded = any(value is not None for value in (run_id, expected, request_id))
        if guarded and (
            not isinstance(run_id, str) or not run_id
            or type(expected) is not int or expected < 0
            or not isinstance(request_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request_id) is None
        ):
            raise ValueError("Guarded advance requires run_id, nonnegative expected_step_index and request_id")
        with selected_run(project_root, run_id) as scope, run_access_lock(scope):
            recover_run(scope)
            receipt_path = scope / "step_requests.json"
            receipts = read_json(receipt_path, default=[]) if guarded else []
            payload_hash = None
            if guarded:
                from app.sim.sim_models import SimulationState
                from app.sim.sim_store import load_simulation_config, load_simulation_state

                config = load_simulation_config(project_root)
                state = load_simulation_state(project_root)
                if config.run_id != run_id or state.run_id != run_id:
                    raise ValueError("Requested run identity does not match the saved run")
                payload = {name: value for name, value in bound.arguments.items()
                           if name not in {"project_root", "run_id", "expected_step_index", "request_id"}}
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
                                     default=lambda value: value.model_dump(mode="json"))
                payload_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                existing = [row for row in receipts if row["request_id"] == request_id]
                if existing:
                    receipt = existing[0]
                    if len(existing) != 1 or receipt["payload_sha256"] != payload_hash or receipt["expected_step_index"] != expected:
                        raise ValueError("Request identity was already used with different step or payload")
                    result = SimulationState.model_validate(receipt["result"])
                    if result.run_id != run_id or result.step_index != expected + 1:
                        raise ValueError("Invalid saved advance receipt")
                    return result
                if state.step_index != expected:
                    raise ValueError("Stale acquired step; reload the selected run before advancing")
            return transact(project_root, scope, args, kwargs, receipt_path, receipts,
                            request_id if guarded else None, expected, payload_hash)

    def transact(project_root, scope, args, kwargs, receipt_path, receipts, request_id, expected, payload_hash):
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
            if request_id is not None:
                append_only_write(receipt_path, [*receipts, {
                    "request_id": request_id, "expected_step_index": expected,
                    "payload_sha256": payload_hash, "result": result.model_dump(mode="json"),
                }], key_fields=["request_id"])
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
