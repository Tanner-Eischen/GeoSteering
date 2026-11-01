"""Verified source identity for editable checkouts and installed release wheels."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "app" / "_release_source.json"


def source_hashes(root=ROOT):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for package in ("app", "tools")
        for path in sorted((Path(root) / package).rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def fingerprint(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def git_identity(root=ROOT):
    # Never accidentally identify an enclosing unrelated checkout at installation.
    if not (Path(root) / ".git").exists():
        return None, None

    def command(*args):
        try:
            result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        except OSError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    revision, status = command("rev-parse", "HEAD"), command("status", "--porcelain")
    return revision, None if status is None else bool(status)


def describe_code(root=ROOT):
    root = Path(root)
    hashes = source_hashes(root)
    manifest_path = root / "app" / "_release_source.json"
    runtime_revision, runtime_dirty = git_identity(root)
    if manifest_path.exists():
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
        if record["source_sha256"] != hashes or record["source_fingerprint"] != fingerprint(hashes):
            raise ValueError("Release source bytes changed; regenerate the source manifest and rebuild")
        return {
            "basis": "verified_packaged_source_manifest",
            "code_revision": record["base_git_revision"],
            "dirty_working_tree": record["source_working_tree_dirty"],
            "source_fingerprint": record["source_fingerprint"],
            "source_file_count": len(hashes),
            "runtime_git_revision": runtime_revision,
            "runtime_git_dirty": runtime_dirty,
            "source_bytes_verified": True,
        }
    return {
        "basis": "current_source_tree",
        "code_revision": runtime_revision or "unavailable",
        "dirty_working_tree": runtime_dirty,
        "source_fingerprint": fingerprint(hashes),
        "source_file_count": len(hashes),
        "runtime_git_revision": runtime_revision,
        "runtime_git_dirty": runtime_dirty,
        "source_bytes_verified": True,
    }


def write_manifest(root=ROOT):
    root = Path(root)
    hashes = source_hashes(root)
    revision, dirty = git_identity(root)
    record = {
        "schema_version": 1,
        "release_version": "0.2.0",
        "base_git_revision": revision or "unavailable",
        "source_working_tree_dirty": dirty,
        "source_fingerprint": fingerprint(hashes),
        "source_sha256": hashes,
        "meaning": "Exact Python source bytes, including uncommitted release changes; base Git revision is not a claim that the snapshot equals that commit",
    }
    path = root / "app" / "_release_source.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Freeze current app/tools source before building")
    args = parser.parse_args()
    print(json.dumps(write_manifest() if args.write else describe_code(), indent=2))


if __name__ == "__main__":
    main()
