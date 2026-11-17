"""Import one uploaded well using the same validation as a local folder."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from app.io import import_well_folder, load_project

UPLOAD_FILES = {"survey.csv": True, "logs.las": True, "markers.csv": False, "reference.json": False}


def collect_uploads(uploads: list[tuple[str, bytes]]) -> dict[str, bytes]:
    files = {}
    for name, content in uploads:
        if name not in UPLOAD_FILES:
            raise ValueError(f"Unexpected filename: {name}. Use survey.csv, logs.las, markers.csv or reference.json.")
        if name in files:
            raise ValueError(f"More than one {name} selected. Upload files for one well at a time.")
        files[name] = content
    return files


def upload_signature(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode())
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def import_uploaded_well(project_root: Path, files: dict[str, bytes], well_name: str) -> dict:
    files = collect_uploads(list(files.items()))
    missing = [name for name, required in UPLOAD_FILES.items() if required and name not in files]
    if missing:
        raise ValueError(f"Upload the required files: {', '.join(missing)}.")
    name = well_name.strip()
    if not name:
        raise ValueError("Enter a well name.")
    if any(well.name.casefold() == name.casefold() for well in load_project(project_root).wells):
        raise ValueError("This well name already exists in the project. Choose a unique name.")
    with TemporaryDirectory(prefix="geosteering-upload-") as staging:
        folder = Path(staging)
        for filename, content in files.items():
            (folder / filename).write_bytes(content)
        try:
            return import_well_folder(project_root, folder, name)
        except Exception as exc:
            message = str(exc).replace(staging, "uploaded files").replace(folder.as_posix(), "uploaded files")
            raise ValueError(message) from None
