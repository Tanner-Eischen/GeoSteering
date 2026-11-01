"""Assemble a bounded owner release, requiring current machine and visual proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

from tools.release_provenance import ROOT, describe_code
from tools.release_verify import verify_project


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(case, proofs, dist, out, qa):
    case, proofs, dist, out, qa = map(Path, (case, proofs, dist, out, qa))
    if out.exists():
        raise FileExistsError("Release output already exists; choose a new path")
    report = verify_project(case / "project")
    visual = json.loads(qa.read_text(encoding="utf8"))
    assert visual["status"] == "passed" and visual["all_pages_visually_inspected"]
    assert visual["pdf_sha256"] == report["pdf_sha256"] and visual["pages"] == report["pdf_pages"]
    install = json.loads((proofs / "clean-install.json").read_text())
    saved = json.loads((proofs / "canonical-verification.json").read_text())
    reopened = json.loads((proofs / "reopened-verification.json").read_text())
    relocated = json.loads((proofs / "relocated-verification.json").read_text())
    assert saved == reopened == relocated
    assert saved["source_provenance"]["source_fingerprint"] == describe_code()["source_fingerprint"]
    assert install["source_provenance"]["source_fingerprint"] == describe_code()["source_fingerprint"]
    assert install["status"] == "passed"
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    assert sha(wheels[0]) == install["wheel_sha256"]
    with tarfile.open(sdists[0]) as archive:
        assert not any("/data/volve/" in name or "/.env" in name or "/venv/" in name for name in archive.getnames())
    out.mkdir(parents=True)
    allowed = []
    for folder, patterns in {
        "app": ["*.py", "_release_source.json"],
        "tools": ["*.py"],
        "tests": ["*.py"],
        "docs": ["*.md", "*.png"],
        "case_studies": ["*.json", "*.md"],
        ".github": ["*.yml"],
    }.items():
        for pattern in patterns:
            allowed.extend(p for p in (ROOT / folder).rglob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    allowed.extend(
        ROOT / name
        for name in (
            "README.md",
            "LICENSE",
            "pyproject.toml",
            "MANIFEST.in",
            "app.py",
            "requirements-release-windows.lock",
            "requirements-release-linux.lock",
            "requirements-release-pins.txt",
        )
    )
    for path in sorted(set(allowed)):
        destination = out / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    shutil.copytree(case, out / "case-study")
    shutil.copytree(proofs, out / "verification")
    shutil.copyfile(qa, out / "verification/pdf-visual-qa.json")
    shutil.copytree(dist, out / "dist")
    for name in (
        "requirements-release-windows.lock",
        "requirements-release-linux.lock",
        "requirements-release-pins.txt",
    ):
        shutil.copyfile(ROOT / name, out / name)
    artifact = json.loads((case / "project/exports/artifacts.json").read_text())
    shutil.copyfile(case / "project" / artifact["report"], out / "geosteering-synthetic-case-study.pdf")
    shutil.copyfile(ROOT / "docs/RELEASE.md", out / "README.md")
    summary = {
        "schema_version": 1,
        "status": "passed",
        "release_version": "0.2.0",
        "source_provenance": describe_code(),
        "current_case": report,
        "clean_install": {
            "platform": install["platform"],
            "python": install["python"],
            "locked_distributions": install["locked_distribution_count"],
            "installed_python_files": install["installed_python_file_count"],
            "wheel_sha256": install["wheel_sha256"],
        },
        "fresh_process_reopen": True,
        "relocated_project_reopen": True,
        "pdf_visual_qa": visual,
        "limits": [
            "Single synthetic scenario and calibrated signed sensor",
            "Browser interaction unverified",
            "Linux lock supplied but not executed",
            "Volve field data excluded; not a real-data performance claim",
        ],
        "publication": "Owner-only archive; no push or deployment performed",
    }
    (out / "release.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
    files = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    (out / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in files.items()), encoding="utf8")
    archive_path = out.with_suffix(".zip")
    if archive_path.exists():
        raise FileExistsError("Archive already exists")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(out).as_posix(), date_time=(2026, 10, 31, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for name, digest in files.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    archive_path.with_suffix(".zip.sha256").write_text(f"{sha(archive_path)}  {archive_path.name}\n", encoding="utf8")
    print(
        json.dumps(
            {"output": str(out), "files": len(files) + 1, "archive": str(archive_path), "sha256": sha(archive_path)},
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("case", "proofs", "dist", "out", "qa"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    package(args.case, args.proofs, args.dist, args.out, args.qa)


if __name__ == "__main__":
    main()
