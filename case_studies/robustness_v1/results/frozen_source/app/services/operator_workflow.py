"""UI-independent handlers used by the actual steering and report forms."""

from __future__ import annotations

from app.model.schemas import ControlPoint
from app.report.report_builder import build_report
from app.services.interpretations import get_latest_interpretation, load_interpretations
from app.services.project_data import load_well_frames
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.services.run_transactions import run_access_lock
from app.services.runs import advance_run
from app.sim.sim_store import load_simulation_config, load_simulation_state


def run_label(project_root, run_id):
    """Human-readable selector label while retaining the full ID as its value."""
    try:
        config = load_simulation_config(project_root, run_id)
        # Selector labels are cached by Streamlit. Keep them immutable; current
        # progress belongs in the freshly loaded state cards, not this label.
        return f"{config.mode.title()} | seed {config.seed} | {config.scenario_version} | {run_id[:8]}"
    except (FileNotFoundError, ValueError):
        return f"Unavailable run | {run_id[:8]}"


def load_operator_view(project_root, run_id):
    """Load every displayed run document using the same explicit selection."""
    if not run_id:
        raise ValueError("Select a saved run")
    scope = run_root(project_root, run_id)
    with run_access_lock(scope):
        config = load_simulation_config(project_root, run_id)
        state = load_simulation_state(project_root, run_id)
        if config.run_id != run_id or state.run_id != run_id:
            raise ValueError("Saved configuration/state do not match the selected run")
        return {
            "config": config, "state": state,
            "interpretation": get_latest_interpretation(project_root, run_id),
            "frames": load_well_frames(project_root, config.active_well_id, run_id=run_id),
            "metrics": load_run_metrics(project_root, run_id),
            "scope": scope,
        }


def _replace_point(points, x_ft, tvd_ft):
    retained = [point for point in points if abs(float(point.x_ft) - x_ft) > 1e-8]
    return sorted([*retained, ControlPoint(md_ft=x_ft, x_ft=x_ft, tvd_ft=tvd_ft)], key=lambda point: point.x_ft)


def submit_steering(
    project_root, *, run_id, expected_step_index, interpretation_version_id,
    action, observations, rationale="", update_bounds=None, target_inc_deg=None,
):
    """Submit the displayed run/step/version, including safe late form retries.

    Interpretation edits are rebuilt from the captured historical version, never
    from whichever interpretation happens to be latest when a retry arrives.
    """
    if type(expected_step_index) is not int or expected_step_index < 0:
        raise ValueError("Expected step must be a nonnegative integer")
    state = load_simulation_state(project_root, run_id)
    if expected_step_index >= len(state.version_id_by_step) or state.version_id_by_step[expected_step_index] != interpretation_version_id:
        raise ValueError("Displayed interpretation does not match the selected run/step")
    version = next((item for item in load_interpretations(project_root, run_id)
                    if item.version_id == interpretation_version_id), None)
    if version is None:
        raise ValueError("Displayed interpretation no longer exists")
    top = base = None
    if update_bounds is not None:
        if not rationale.strip():
            raise ValueError("Explain the evidence supporting the interpretation revision")
        x_ft, top_tvd_ft, base_tvd_ft = update_bounds
        if base_tvd_ft <= top_tvd_ft:
            raise ValueError("Base TVD must be below top TVD")
        top = _replace_point(version.top_control_points, x_ft, top_tvd_ft)
        base = _replace_point(version.base_control_points, x_ft, base_tvd_ft)
    return advance_run(
        project_root, action, observations, rationale=rationale or None,
        top_control_points=top, base_control_points=base, target_inc_deg=target_inc_deg,
        run_id=run_id, expected_step_index=expected_step_index,
        request_id=f"steering-{run_id}-{expected_step_index}",
    )


def export_selected_report(project_root, *, run_id, plan_id=None, include_wells=None, include_steps=None):
    """Export the form's explicit run; a changing active pointer is not a fallback."""
    if not run_id:
        raise ValueError("Select a saved run before exporting")
    with run_access_lock(run_root(project_root, run_id)):
        return build_report(
            project_root, run_id=run_id, plan_id=plan_id,
            include_wells=include_wells, include_steps=include_steps,
        )
