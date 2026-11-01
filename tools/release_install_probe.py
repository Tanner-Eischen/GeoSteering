"""Attest a noneditable installed wheel, exact source bytes and locked dependencies."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.release_provenance import ROOT, describe_code


def digest(content):
    return hashlib.sha256(content).hexdigest()


def probe(wheel, source):
    source = Path(source).resolve()
    if ROOT.resolve() == source or ROOT.name != "site-packages":
        raise ValueError("Run the installed wheel from outside the source checkout")
    provenance = describe_code()
    assert provenance["runtime_git_revision"] is None
    expected = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith(".py") and name.split("/")[0] in {"app", "tools"}:
                content = archive.read(name)
                assert content == (ROOT / name).read_bytes(), name
                assert content == (source / name).read_bytes(), name
                expected[name] = digest(content)
        assert archive.read("app/_release_source.json") == (ROOT / "app/_release_source.json").read_bytes()
    assert expected == json.loads((ROOT / "app/_release_source.json").read_text())["source_sha256"]
    lock = source / "requirements-release-windows.lock"
    versions = {
        re.sub(r"[-_.]+", "-", name.lower()): version
        for name, version in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", lock.read_text(), re.M)
    }
    installed = {
        re.sub(r"[-_.]+", "-", d.metadata["Name"].lower()): d.version for d in importlib.metadata.distributions()
    }
    assert all(installed.get(name) == version for name, version in versions.items())
    unexpected = set(installed) - set(versions) - {"pip", "setuptools", "geosteering-workbench"}
    assert not unexpected, unexpected
    result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, check=True)
    return {
        "schema_version": 1,
        "status": "passed",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "package_version": importlib.metadata.version("geosteering-workbench"),
        "source_provenance": provenance,
        "wheel_sha256": digest(Path(wheel).read_bytes()),
        "installed_python_file_count": len(expected),
        "installed_python_sha256": expected,
        "locked_distribution_count": len(versions),
        "installed_versions": installed,
        "unexpected_distributions": [],
        "pip_check": result.stdout.strip(),
        "build_context_sha256": {
            name: digest((source / name).read_bytes())
            for name in (
                "pyproject.toml",
                "MANIFEST.in",
                "requirements-release-windows.lock",
                "requirements-release-linux.lock",
                "requirements-release-pins.txt",
            )
        },
        "linux_lock_executed": False,
        "browser_used": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--write", type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.wheel, args.source)
    if args.write.exists():
        raise FileExistsError("Choose an unused proof path")
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "installed_python_file_count": result["installed_python_file_count"],
                "locked_distribution_count": result["locked_distribution_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
