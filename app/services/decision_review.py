"""Read one historical decision with its original information boundary.

The decision view stops before the chosen interval is revealed. The after view
adds that interval's acquired observations and its persisted estimated metrics.
Neither view reads retrospective evaluation or recomputes historical scores.
"""

from __future__ import annotations

from copy import deepcopy

from app.io.project_store import read_json
from app.model.schemas import DecisionEntry, InterpretationVersion
from app.services.project_data import load_well_frames
from app.services.run_paths import run_root
from app.services.run_transactions import run_access_lock
from app.sim.sim_store import load_simulation_config, load_simulation_state

_METRIC_FIELDS = {
    "step_index", "revealed_md_ft", "decision_time_md_ft", "interpretation_version_id", "decision_id",
    "md_from_ft", "md_to_ft", "metric_basis", "coordinate_basis", "action", "percent_in_zone",
    "avg_center_distance", "last_step_in_zone", "in_zone_length_ft", "evaluated_length_ft",
    "max_overshoot_ft", "uncertainty_band_tvd_ft",
}
_RESPONSE_FIELDS = {"action", "requested_inc_deg", "effective_inc_deg", "clipped", "limit_reason"}


def _selected_run(project_root, run_id):
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Select a saved run for decision review")
    return run_root(project_root, run_id)


def _identity(project_root, run_id):
    config = load_simulation_config(project_root, run_id)
    state = load_simulation_state(project_root, run_id)
    if config.run_id != run_id or state.run_id != run_id:
        raise ValueError("Saved configuration/state do not match the selected run")
    return config, state


def _step_metadata(scope, config, state):
    steps = [{"step_index": 0, "md_from_ft": config.start_md_ft, "md_to_ft": config.start_md_ft}]
    for item in read_json(scope / "decisions" / "decisions.json", default=[]):
        index = item.get("step_index")
        if type(index) is int and 0 < index <= state.step_index:
            steps.append({key: item[key] for key in ("step_index", "md_from_ft", "md_to_ft")})
    if len({step["step_index"] for step in steps}) != len(steps):
        raise ValueError("Saved run has duplicate decision steps")
    return sorted(steps, key=lambda item: item["step_index"])


def list_review_steps(project_root, run_id) -> list[dict]:
    """Return selector metadata only, without actions, metrics or future logs."""
    scope = _selected_run(project_root, run_id)
    with run_access_lock(scope):
        config, state = _identity(project_root, run_id)
        return _step_metadata(scope, config, state)


def _interpretation(scope, version_id):
    selected = [row for row in read_json(scope / "interpretations" / "interpretations.json", default=[])
                if row.get("version_id") == version_id]
    if len(selected) != 1:
        raise ValueError("The selected historical interpretation is unavailable or duplicated")
    return InterpretationVersion.model_validate(selected[0])


def _metrics_prefix(scope, last_step, revealed_md_ft):
    result = []
    for row in read_json(scope / "metrics.json", default=[]):
        index = row.get("step_index")
        if type(index) is not int or not 0 < index <= last_step:
            continue
        if row.get("revealed_md_ft", float("inf")) > revealed_md_ft or row.get("md_to_ft", float("inf")) > revealed_md_ft:
            raise ValueError("Saved metric exceeds the selected historical information boundary")
        clean = {key: deepcopy(value) for key, value in row.items() if key in _METRIC_FIELDS}
        # Causal response records can also contain the newly sampled sensor
        # observation. Never copy those nested payloads into historical cards.
        if isinstance(row.get("command_response"), dict):
            clean["command_response"] = {key: deepcopy(value) for key, value in row["command_response"].items()
                                          if key in _RESPONSE_FIELDS}
        result.append(clean)
    if len({row["step_index"] for row in result}) != len(result):
        raise ValueError("Saved run has duplicate metric steps")
    return sorted(result, key=lambda row: row["step_index"])


def load_decision_review(project_root, run_id, step_index, phase="decision") -> dict:
    """Load an explicit selected run/step without looking ahead.

    Step zero is the pre-job baseline. At decision n the selected revision is
    the interpretation recorded with that decision; its before-model is the
    version acquired at n-1, and metrics stop at n-1. At after n, the same
    decision is shown with the revealed interval and metric snapshot n.
    """
    if type(step_index) is not int or step_index < 0:
        raise ValueError("Select a nonnegative integer decision step")
    if phase not in {"decision", "after"}:
        raise ValueError("Review phase must be decision or after")
    scope = _selected_run(project_root, run_id)
    with run_access_lock(scope):
        config, state = _identity(project_root, run_id)
        steps = {item["step_index"]: item for item in _step_metadata(scope, config, state)}
        if step_index not in steps:
            raise ValueError("The selected decision step is not saved in this run")
        interval = steps[step_index]
        decision = None
        if step_index:
            selected = [row for row in read_json(scope / "decisions" / "decisions.json", default=[])
                        if row.get("step_index") == step_index]
            entry = DecisionEntry.model_validate(selected[0])
            if step_index >= len(state.decision_id_by_step) or state.decision_id_by_step[step_index] != entry.decision_id:
                raise ValueError("Saved decision does not match the selected run/step")
            chosen_id = entry.interpretation_version_id
            before_id = state.version_id_by_step[step_index - 1]
            decision = entry.model_dump(mode="json", include={
                "decision_id", "step_index", "md_from_ft", "md_to_ft", "interpretation_version_id",
                "observations", "recommendation", "created_at",
            })
        else:
            if not state.version_id_by_step:
                raise ValueError("Saved run has no baseline interpretation")
            chosen_id = before_id = state.version_id_by_step[0]
        if step_index >= len(state.version_id_by_step) or state.version_id_by_step[step_index] != chosen_id:
            raise ValueError("Saved interpretation does not match the selected run/step")
        interpretation = _interpretation(scope, chosen_id)
        before_interpretation = _interpretation(scope, before_id)
        revealed = interval["md_from_ft"] if phase == "decision" else interval["md_to_ft"]
        if revealed > state.revealed_md_ft:
            raise ValueError("The selected interval has not been acquired")
        # The operator loader already excludes unacquired data. Reclip that
        # acquired prefix to the historical endpoint without interpolation.
        acquired = load_well_frames(project_root, config.active_well_id, run_id=run_id)
        frames = {name: acquired[name].loc[acquired[name].md_ft <= revealed].copy().reset_index(drop=True)
                  for name in ("survey", "trajectory", "logs")}
        # Current marker edits are not historical evidence. Only the run's
        # immutable input snapshot may appear in a review.
        marker_path = scope / "inputs" / "wells" / config.active_well_id / "markers.json"
        frames["markers"] = [marker for marker in read_json(marker_path, default=[])
                             if float(marker["md_ft"]) <= revealed]
        metric_step = max(0, step_index - 1) if phase == "decision" else step_index
        metrics = _metrics_prefix(scope, metric_step, revealed)
        manifest = read_json(scope / "manifest.json", default={})
        from app.services.uncertainty import load_uncertainty_snapshot
        return {
            "run": {"run_id": run_id, "mode": config.mode, "seed": config.seed,
                    "scenario_version": config.scenario_version, "active_well_id": config.active_well_id,
                    "curves_used": config.curves_used, "window_size_ft": config.window_size_ft,
                    "parent_run_id": manifest.get("parent_run_id"), "forked_at_step": manifest.get("forked_at_step")},
            "step_index": step_index, "phase": phase, "revealed_md_ft": revealed,
            "interval": interval, "decision": decision, "interpretation": interpretation,
            "before_interpretation": before_interpretation, "frames": frames,
            "metrics": metrics, "metric": metrics[-1] if metrics else None,
            "uncertainty": load_uncertainty_snapshot(project_root, run_id, metric_step),
        }
