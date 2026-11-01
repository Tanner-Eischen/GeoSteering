import json
from pathlib import Path

import pytest

from app.io import project_store


def denied(code=32):
    error = PermissionError("Synthetic Windows sharing denial")
    error.winerror = code
    return error


def test_transient_sharing_denial_retries_only_atomic_replace(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"old": true}')
    original = Path.replace
    attempts, delays = [], []

    def transient(source, destination):
        attempts.append(source)
        if len(attempts) < 3:
            assert json.loads(target.read_text()) == {"old": True}
            raise denied()
        return original(source, destination)

    monkeypatch.setattr(Path, "replace", transient)
    monkeypatch.setattr(project_store.time, "sleep", delays.append)
    project_store.atomic_write_json(target, {"new": True})
    assert len(attempts) == 3 and delays == [0.025, 0.05]
    assert json.loads(target.read_text()) == {"new": True}
    assert list(tmp_path.glob("*.tmp")) == []


def test_persistent_denial_is_bounded_and_preserves_original(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    original = b'{"old": true}'
    target.write_bytes(original)
    attempts = []

    def persistent(*args):
        attempts.append(args)
        raise denied(5)

    monkeypatch.setattr(Path, "replace", persistent)
    monkeypatch.setattr(project_store.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        project_store.atomic_write_json(target, {"new": True})
    assert len(attempts) == 6 and target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_ordinary_permission_failure_is_not_retried(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    attempts = []

    def rejected(*args):
        attempts.append(args)
        raise PermissionError("No Windows sharing code")

    monkeypatch.setattr(Path, "replace", rejected)
    with pytest.raises(PermissionError):
        project_store.atomic_write_json(target, {"new": True})
    assert len(attempts) == 1 and not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []
