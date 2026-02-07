from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.io.project_store import atomic_write_json, read_json, well_paths
from app.model.schemas import Marker


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_markers(project_root: str | Path, well_id: str) -> list[Marker]:
    path = well_paths(project_root, well_id)["markers"]
    rows = read_json(path, default=[])
    return [Marker.model_validate(r) for r in rows]


def save_markers(project_root: str | Path, well_id: str, markers: list[Marker]) -> None:
    path = well_paths(project_root, well_id)["markers"]
    sorted_markers = sorted(markers, key=lambda m: m.md_ft)
    atomic_write_json(path, [m.model_dump(mode="json") for m in sorted_markers])


def add_marker(
    project_root: str | Path,
    well_id: str,
    name: str,
    md_ft: float,
    notes: Optional[str] = None,
    color: Optional[str] = None,
) -> Marker:
    markers = load_markers(project_root, well_id)
    marker = Marker(name=name, md_ft=md_ft, notes=notes, color=color)
    markers.append(marker)
    save_markers(project_root, well_id, markers)
    return marker


def edit_marker(
    project_root: str | Path,
    well_id: str,
    marker_id: str,
    *,
    name: Optional[str] = None,
    md_ft: Optional[float] = None,
    notes: Optional[str] = None,
    color: Optional[str] = None,
) -> Marker:
    markers = load_markers(project_root, well_id)
    updated: Marker | None = None
    for marker in markers:
        if marker.marker_id != marker_id:
            continue
        payload = marker.model_dump(mode="python")
        if name is not None:
            payload["name"] = name
        if md_ft is not None:
            payload["md_ft"] = md_ft
        if notes is not None:
            payload["notes"] = notes
        if color is not None:
            payload["color"] = color
        payload["updated_at"] = _now_iso()
        updated = Marker.model_validate(payload)
        markers = [m for m in markers if m.marker_id != marker_id] + [updated]
        break

    if updated is None:
        raise ValueError(f"Marker not found: {marker_id}")
    save_markers(project_root, well_id, markers)
    return updated


def delete_marker(project_root: str | Path, well_id: str, marker_id: str) -> None:
    markers = load_markers(project_root, well_id)
    filtered = [m for m in markers if m.marker_id != marker_id]
    if len(filtered) == len(markers):
        raise ValueError(f"Marker not found: {marker_id}")
    save_markers(project_root, well_id, filtered)

