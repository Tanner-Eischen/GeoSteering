from __future__ import annotations

import numpy as np

from app.model.schemas import ControlPoint
from app.services.markers import load_markers
from app.services.project_data import load_project_and_wells, load_well_frames


def estimate_offset_baseline(
    project_root, offset_well_ids: list[str], *, active_well_id: str | None = None,
    top_marker_name: str = "Top_A", base_marker_name: str = "Base_A",
) -> tuple[list[ControlPoint], list[ControlPoint], float]:
    """Fit top/base regional lines to observed offset crossings only.

    The returned extrapolation spans the local case-study domain. Its 10-ft
    minimum uncertainty is an assumed scenario band, not a confidence interval.
    Spatial support remains only the offset-marker locations.
    """
    project, wells = load_project_and_wells(project_root)
    by_id = {w.well_id: w for w in wells}
    selected_active = active_well_id or project.active_well_id
    if selected_active in offset_well_ids:
        raise ValueError("The active well cannot be an offset baseline input.")
    if len(set(offset_well_ids)) < 2:
        raise ValueError("At least two distinct offset wells are required.")
    if top_marker_name.casefold() == base_marker_name.casefold():
        raise ValueError("Select different top and base marker names.")
    picks: dict[str, list[tuple[float, float]]] = {"top": [], "base": []}
    datums = set()
    for well_id in offset_well_ids:
        well = by_id[well_id]
        if well.reference is None:
            raise ValueError("Spatial interpretation requires explicit offset coordinate references; reimport with reference.json.")
        datums.add((well.reference.coordinate_system, well.reference.vertical_datum))
        if abs(well.reference.origin_north_ft) > 1e-8:
            raise ValueError("The 2D case study requires along-section offsets (north=0).")
        frames = load_well_frames(project_root, well_id, include_unrevealed=True, source_project_inputs=True)
        trajectory = frames["trajectory"]
        markers = load_markers(project_root, well_id)
        for kind, marker_name in (("top", top_marker_name), ("base", base_marker_name)):
            matching = [marker for marker in markers if marker.name.casefold() == marker_name.casefold()]
            if len(matching) != 1:
                raise ValueError(f"Offset {well.name} requires exactly one selected {marker_name} crossing.")
            marker = matching[0]
            if not trajectory.md_ft.min() <= marker.md_ft <= trajectory.md_ft.max():
                raise ValueError("Offset marker falls outside its observed survey.")
            picks[kind].append((
                float(np.interp(marker.md_ft, trajectory.md_ft, trajectory.east_ft)),
                float(np.interp(marker.md_ft, trajectory.md_ft, trajectory.tvd_ft)),
            ))
    if len(datums) != 1:
        raise ValueError("Offset wells must share coordinate system and vertical datum.")
    active = by_id.get(selected_active)
    if active is None or active.reference is None:
        raise ValueError("The active well requires an explicit spatial coordinate reference.")
    if abs(active.reference.origin_north_ft) > 1e-8:
        raise ValueError("The 2D study requires the active well on the common section (north=0).")
    if (active.reference.coordinate_system, active.reference.vertical_datum) not in datums:
        raise ValueError("Active and offset wells use different references.")
    result = []
    residuals = []
    for kind in ("top", "base"):
        values = np.asarray(picks[kind], dtype=float)
        if len(values) < 2 or np.ptp(values[:, 0]) < 1:
            raise ValueError(f"At least two spatially separated {kind} markers are required.")
        slope, intercept = np.polyfit(values[:, 0], values[:, 1], 1)
        residuals.extend(np.abs(values[:, 1] - (slope * values[:, 0] + intercept)))
        domain = [float(min(0, values[:, 0].min())), float(max(10000, values[:, 0].max()))]
        result.append([ControlPoint(md_ft=x, x_ft=x, tvd_ft=float(intercept + slope * x)) for x in domain])
    if any(b.tvd_ft <= t.tvd_ft for t, b in zip(result[0], result[1])):
        raise ValueError("Offset extrapolation produces crossing horizons in the study domain.")
    return result[0], result[1], max(10.0, float(max(residuals, default=0)) * 2)
