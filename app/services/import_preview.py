"""Read-only folder checks for the operator import workflow."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


def parse_well_paths(raw: str) -> list[Path]:
    """Accept newline/semicolon lists, preserving quoted paths and Windows slashes."""
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    for char in raw:
        if char == '"':
            quoted = not quoted
        elif char in ";\n\r" and not quoted:
            if value := "".join(current).strip():
                parts.append(value)
            current = []
        else:
            current.append(char)
    if quoted:
        raise ValueError('A folder path has an unmatched double quote. Close it or remove the quotes.')
    if value := "".join(current).strip():
        parts.append(value)
    return [Path(value).expanduser() for value in parts]


def parse_well_names(raw: str) -> list[str]:
    return [value.strip() for value in re.split(r"[;\n,]+", raw) if value.strip()]


def check_import_folders(paths: list[Path], names: list[str], existing_names: list[str]) -> list[dict]:
    """Check files and labels without importing data or changing the project."""
    if len(paths) != len(names):
        raise ValueError("Provide one well name for each folder.")
    canonical_paths = [str(path.resolve()).casefold() for path in paths]
    path_counts = Counter(canonical_paths)
    normalized_names = [name.strip().casefold() for name in names]
    name_counts = Counter(normalized_names)
    existing = {name.casefold() for name in existing_names}
    rows = []
    for path, name, canonical, normalized in zip(paths, names, canonical_paths, normalized_names, strict=True):
        issues = []
        if not path.is_dir():
            issues.append("Folder not found")
        else:
            missing = [filename for filename in ("survey.csv", "logs.las") if not (path / filename).is_file()]
            if missing:
                issues.append(f"Missing {', '.join(missing)}")
        if path_counts[canonical] > 1:
            issues.append("Folder listed more than once")
        if not normalized:
            issues.append("Enter a well name")
        elif name_counts[normalized] > 1:
            issues.append("Choose a unique name for each well")
        elif normalized in existing:
            issues.append("Name already in project; choose a different name to import another copy")
        rows.append({
            "Well": name.strip(),
            "Folder": str(path),
            "File check": "; ".join(issues) if issues else "Ready for import",
            "Markers": "Available" if (path / "markers.csv").is_file() else "None",
            "Spatial reference": "Available" if (path / "reference.json").is_file() else "Missing — MD-only",
            "ready": not issues,
        })
    return rows
