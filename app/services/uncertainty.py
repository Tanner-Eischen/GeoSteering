"""Immutable, acquired-only ensemble snapshots for explicitly opted-in runs.

The engine consumes at most one original-pose GR measurement per simulation
step. Persistence adds no geological truth access and never rebuilds history
using a later manual interpretation.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from app.io.project_store import atomic_write_json, read_json
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run, run_access_lock


def _sha(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _snapshot_path(scope, step_index):
    if type(step_index) is not int or not 0 <= step_index <= 99999999:
        raise ValueError("Ensemble step must be a nonnegative integer below 100 million")
    return Path(scope) / "uncertainty" / "steps" / f"{step_index:08d}.json"


def _measurement(frames, revealed_md_ft):
    """Pair the newest usable acquired log with its own observed survey pose.

    Logs after the last acquired survey station cannot yet be spatially located;
    interpolation is restricted to the already acquired trajectory brackets.
    """
    trajectory = frames["trajectory"].loc[frames["trajectory"].md_ft <= revealed_md_ft].sort_values("md_ft")
    if trajectory.empty:
        raise ValueError("An ensemble requires an acquired trajectory station")
    xcol = "x_ft" if "x_ft" in trajectory else "east_ft"
    if not np.isfinite(trajectory[["md_ft", xcol, "tvd_ft"]].to_numpy(dtype=float)).all():
        raise ValueError("Ensemble trajectory coordinates must be finite")
    station = {"md_ft": float(trajectory.md_ft.iloc[-1]), "x_ft": float(trajectory[xcol].iloc[-1]),
               "tvd_ft": float(trajectory.tvd_ft.iloc[-1])}
    logs = frames["logs"]
    eligible = logs.loc[(logs.md_ft >= trajectory.md_ft.min()) & (logs.md_ft <= station["md_ft"])].sort_values("md_ft")
    if eligible.empty or "GR" not in eligible:
        return station, None, "no_acquired_gr"
    row = eligible.iloc[-1]
    md = float(row.md_ft)
    try:
        gr = float(row.GR)
    except (TypeError, ValueError):
        gr = float("nan")
    observation = {"md_ft": md, "x_ft": float(np.interp(md, trajectory.md_ft, trajectory[xcol])),
                   "tvd_ft": float(np.interp(md, trajectory.md_ft, trajectory.tvd_ft)),
                   "GR": gr if math.isfinite(gr) else None}
    return station, observation, "ready" if math.isfinite(gr) else "missing_gr"


def _write_snapshot(scope, payload):
    path = _snapshot_path(scope, payload["step_index"])
    if path.exists():
        raise ValueError("Refusing to rewrite an immutable ensemble snapshot")
    record = {**payload, "snapshot_sha256": _sha(payload)}
    atomic_write_json(path, record)
    atomic_write_json(Path(scope) / "uncertainty" / "state.json", {
        "step_index": record["step_index"], "snapshot_sha256": record["snapshot_sha256"],
        "settings_sha256": record["settings_sha256"], "baseline_sha256": record["baseline_sha256"],
    })
    return record


def initialize_uncertainty(project_root, config, state, baseline, frames):
    """Capture the opt-in settings/baseline and acquired start snapshot once."""
    if config.ensemble_settings is None:
        return None
    from app.uncertainty.ensemble import initialize_ensemble, update_ensemble

    scope = run_root(project_root, config.run_id)
    settings = config.ensemble_settings.model_dump(mode="json")
    geometry = {"top_control_points": [point.model_dump(mode="json") for point in baseline.top_control_points],
                "base_control_points": [point.model_dump(mode="json") for point in baseline.base_control_points]}
    inputs = {"settings": settings, "settings_sha256": _sha(settings),
              "baseline": geometry, "baseline_sha256": _sha(geometry)}
    station, measurement, status = _measurement(frames, state.revealed_md_ft)
    initial_x = measurement["x_ft"] if measurement is not None else station["x_ft"]
    ensemble = initialize_ensemble(baseline.top_control_points, baseline.base_control_points,
                                   initial_x, settings=config.ensemble_settings, seed=config.seed)
    observation_pose = measurement if measurement is not None else station
    ensemble = update_ensemble(ensemble, x_ft=observation_pose["x_ft"], tvd_ft=observation_pose["tvd_ft"],
                               gr_api=measurement["GR"] if measurement is not None else None,
                               observation_md_ft=observation_pose["md_ft"], step_index=0)
    status = "updated" if status == "ready" else "prediction_only"
    atomic_write_json(scope / "inputs" / "ensemble_settings.json", inputs)
    return _write_snapshot(scope, {
        "schema_version": 1, "step_index": 0, "revealed_md_ft": state.revealed_md_ft,
        "acquired_station": station, "measurement": measurement, "observation_status": status,
        "settings_sha256": inputs["settings_sha256"], "baseline_sha256": inputs["baseline_sha256"],
        "previous_snapshot_sha256": None, "ensemble": ensemble,
    })


def _frozen_inputs(scope, config):
    path = Path(scope) / "inputs" / "ensemble_settings.json"
    if not path.is_file():
        raise ValueError("This run has no frozen ensemble inputs. Initialize a new opted-in run instead of enabling an old history.")
    document = read_json(path)
    settings = config.ensemble_settings.model_dump(mode="json")
    if document.get("settings") != settings or document.get("settings_sha256") != _sha(settings):
        raise ValueError("Ensemble settings no longer match the frozen run configuration")
    if document.get("baseline_sha256") != _sha(document.get("baseline")):
        raise ValueError("The frozen ensemble baseline has changed")
    manifest = read_json(Path(scope) / "manifest.json")
    expected = manifest.get("input_hashes", {}).get("inputs/ensemble_settings.json")
    if expected != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError("The frozen ensemble input snapshot has changed")
    return document


def load_uncertainty_snapshot(project_root, run_id, step_index=None):
    """Read one saved ensemble prefix, without creating data for legacy runs."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Select a saved run before opening ensemble uncertainty")
    from app.sim.sim_store import load_simulation_config, load_simulation_state

    scope = run_root(project_root, run_id)
    with run_access_lock(scope):
        recover_run(scope)
        config = load_simulation_config(project_root, run_id)
        state = load_simulation_state(project_root, run_id)
        if config.run_id != run_id or state.run_id != run_id:
            raise ValueError("Ensemble selection does not match the saved run")
        if config.ensemble_settings is None:
            return None
        selected = state.step_index if step_index is None else step_index
        if type(selected) is not int or not 0 <= selected <= state.step_index:
            raise ValueError("The selected ensemble step has not been acquired")
        inputs = _frozen_inputs(scope, config)
        pointer = read_json(scope / "uncertainty" / "state.json")
        if type(pointer.get("step_index")) is not int or pointer["step_index"] != state.step_index:
            raise ValueError("Ensemble state does not match the committed simulation step")
        if pointer.get("settings_sha256") != inputs["settings_sha256"] or pointer.get("baseline_sha256") != inputs["baseline_sha256"]:
            raise ValueError("Ensemble pointer uses different settings or baseline evidence")
        previous = None
        result = None
        for index in range(selected + 1):
            record = read_json(_snapshot_path(scope, index))
            digest = record.get("snapshot_sha256")
            payload = {key: value for key, value in record.items() if key != "snapshot_sha256"}
            if digest != _sha(payload) or record.get("step_index") != index or record.get("previous_snapshot_sha256") != previous:
                raise ValueError("Saved ensemble history has changed or lost a prefix")
            if record.get("settings_sha256") != inputs["settings_sha256"] or record.get("baseline_sha256") != inputs["baseline_sha256"]:
                raise ValueError("Saved ensemble history uses different settings or baseline evidence")
            if record["revealed_md_ft"] > state.revealed_md_ft:
                raise ValueError("Saved ensemble exceeds the acquired information boundary")
            expected_md = min(config.end_md_ft, config.start_md_ft + index * config.step_size_ft)
            if not math.isclose(record["revealed_md_ft"], expected_md, rel_tol=0, abs_tol=1e-8):
                raise ValueError("Saved ensemble depth does not match its original simulation step")
            if record["acquired_station"]["md_ft"] > record["revealed_md_ft"]:
                raise ValueError("Saved ensemble contains an unacquired survey station")
            if record.get("measurement") and record["measurement"]["md_ft"] > record["acquired_station"]["md_ft"]:
                raise ValueError("Saved ensemble contains a measurement beyond its acquired survey support")
            if record["ensemble"].get("settings") != inputs["settings"]:
                raise ValueError("Saved ensemble settings differ from the frozen inputs")
            if record["ensemble"].get("seed") != config.seed:
                raise ValueError("Saved ensemble seed differs from the frozen run configuration")
            previous, result = digest, record
        if selected == state.step_index and pointer.get("snapshot_sha256") != result["snapshot_sha256"]:
            raise ValueError("Ensemble state pointer does not match its immutable snapshot")
        return result


def advance_uncertainty(project_root, config, next_state, frames):
    """Append exactly one after-acquisition snapshot inside the step transaction."""
    if config.ensemble_settings is None:
        return None
    from app.uncertainty.ensemble import update_ensemble

    previous = load_uncertainty_snapshot(project_root, config.run_id)
    if previous["step_index"] != next_state.step_index - 1:
        raise ValueError("Ensemble advancement requires the previous committed snapshot")
    station, measurement, status = _measurement(frames, next_state.revealed_md_ft)
    ensemble = previous["ensemble"]
    observation_pose = measurement if measurement is not None else station
    last_md = ensemble.get("last_observation_md_ft")
    if last_md is not None and observation_pose["md_ft"] <= last_md + 1e-8:
        if station["md_ft"] > last_md + 1e-8 and station["x_ft"] > ensemble["x_ft"] + 1e-8:
            # The bit moved but the newest available GR was already consumed.
            # Predict at the new acquired station with no likelihood; never
            # relabel the old GR with the bit's newer position.
            ensemble = update_ensemble(ensemble, x_ft=station["x_ft"], tvd_ft=station["tvd_ft"],
                                       gr_api=None, observation_md_ft=station["md_ft"], step_index=next_state.step_index)
            measurement = None
            status = "prediction_only_no_new_gr"
        else:
            status = "already_assimilated"
    elif observation_pose["x_ft"] <= ensemble["x_ft"] + 1e-8:
        status = "non_forward_observation"
    else:
        ensemble = update_ensemble(ensemble, x_ft=observation_pose["x_ft"], tvd_ft=observation_pose["tvd_ft"],
                                   gr_api=measurement["GR"] if measurement is not None else None,
                                   observation_md_ft=observation_pose["md_ft"], step_index=next_state.step_index)
        status = "updated" if status == "ready" else "prediction_only"
    return _write_snapshot(run_root(project_root, config.run_id), {
        "schema_version": 1, "step_index": next_state.step_index, "revealed_md_ft": next_state.revealed_md_ft,
        "acquired_station": station, "measurement": measurement, "observation_status": status,
        "settings_sha256": previous["settings_sha256"], "baseline_sha256": previous["baseline_sha256"],
        "previous_snapshot_sha256": previous["snapshot_sha256"], "ensemble": ensemble,
    })
