"""Private synthetic environment and acquired-only persistent observations.

Only this environment and completed evaluators load the scenario snapshot.
Operator loaders receive the acquired frames, never private field parameters.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.geo.formation import Scenario, default_scenario
from app.io.project_store import atomic_write_json, read_json
from app.sim.observation_sampler import sample_station
from app.sim.trajectory_response import advance_station


def load_private_scenario(scope: str | Path) -> Scenario:
    root = Path(scope) / "environment"
    payload = (root / "scenario.json").read_bytes()
    expected = read_json(root / "provenance.json", default={}).get("private_scenario_sha256")
    if not expected or hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("The private environment scenario has changed since run initialization.")
    return Scenario.model_validate(json.loads(payload))


def snapshot_replay_truth(scope: str | Path, source_path: str | Path) -> Path:
    """Capture bytes for later evaluation without interpreting hidden geology."""
    payload = Path(source_path).read_bytes()
    root = Path(scope) / "environment"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "truth.json"
    with destination.open("xb") as stream:
        stream.write(payload)
    atomic_write_json(root / "provenance.json", {"source_truth_sha256": hashlib.sha256(payload).hexdigest()})
    return destination.resolve()


def initialize_environment(scope, config, frames, hidden_truth_path=None) -> None:
    root = Path(scope) / "environment"
    if (root / "state.json").exists():
        raise FileExistsError("A causal environment already exists for this run.")
    if hidden_truth_path is None:
        scenario = default_scenario(config.seed)
    else:
        payload = read_json(Path(hidden_truth_path))
        scenario = Scenario.model_validate(payload.get("scenario", payload))
    if config.scenario_version not in {"unspecified", scenario.version}:
        raise ValueError("Run scenario version does not match the private environment.")
    if config.start_md_ft < scenario.landing_md_ft or config.end_md_ft <= scenario.landing_md_ft:
        raise ValueError("Causal runs must begin at or after the completed landing.")
    # A shorter configured experiment uses the same field over a shorter domain.
    scenario = Scenario.model_validate(scenario.model_copy(update={
        "lateral_length_ft": config.end_md_ft - scenario.landing_md_ft,
        "seed": config.seed,
    }).model_dump())
    trajectory = frames["trajectory"]
    acquired = trajectory.loc[trajectory.md_ft <= config.start_md_ft].copy()
    if acquired.empty or not np.isclose(acquired.md_ft.iloc[-1], config.start_md_ft, atol=1e-8, rtol=0):
        raise ValueError("Causal start MD must be an acquired trajectory station.")
    if "x_ft" not in acquired:
        acquired["x_ft"] = acquired["east_ft"]
    logs = frames["logs"].loc[frames["logs"].md_ft <= config.start_md_ft].copy()
    # Use an environment-owned sensor at the start. Never read a future log.
    logs = logs.loc[logs.md_ft < config.start_md_ft]
    log = sample_station(acquired.iloc[-1].to_dict(), scenario, config.seed, 0)
    logs = pd.concat([logs, pd.DataFrame([log])], ignore_index=True)
    atomic_write_json(root / "scenario.json", scenario.model_dump())
    atomic_write_json(root / "provenance.json", {
        "private_scenario_sha256": hashlib.sha256((root / "scenario.json").read_bytes()).hexdigest(),
        "source_truth_sha256": hashlib.sha256(Path(hidden_truth_path).read_bytes()).hexdigest() if hidden_truth_path else None,
    })
    atomic_write_json(root / "state.json", {"trajectory": acquired.to_dict(orient="records"),
                                           "logs": logs.to_dict(orient="records"), "commands": []})


def load_environment_frames(scope) -> dict:
    state = read_json(Path(scope) / "environment" / "state.json")
    trajectory = pd.DataFrame(state["trajectory"])
    return {"trajectory": trajectory, "survey": trajectory[["md_ft", "inc_deg", "azi_deg"]].copy(),
            "logs": pd.DataFrame(state["logs"]), "markers": []}


def preview_environment_step(scope, config, next_md_ft, step_index, action, target_inc_deg=None) -> tuple[dict, dict]:
    frames = load_environment_frames(scope)
    previous = frames["trajectory"].iloc[-1].to_dict()
    step = float(next_md_ft) - float(previous["md_ft"])
    if next_md_ft > config.end_md_ft + 1e-8:
        raise ValueError("Environment step exceeds the configured end MD.")
    scenario = load_private_scenario(scope)
    station, response = advance_station(previous, action, step,
                                        min(config.max_dls_deg_per_100ft, scenario.max_dls_deg_per_100ft),
                                        target_inc_deg)
    log = sample_station(station, scenario, config.seed, step_index)
    frames["trajectory"] = pd.concat([frames["trajectory"], pd.DataFrame([station])], ignore_index=True)
    frames["survey"] = frames["trajectory"][["md_ft", "inc_deg", "azi_deg"]].copy()
    frames["logs"] = pd.concat([frames["logs"], pd.DataFrame([log])], ignore_index=True)
    return frames, {**response, "step_index": step_index, "md_from_ft": float(previous["md_ft"]),
                    "md_to_ft": float(next_md_ft), "observation": log}


def commit_environment_step(scope, frames, response) -> None:
    path = Path(scope) / "environment" / "state.json"
    state = read_json(path)
    trajectory = frames["trajectory"].to_dict(orient="records")
    logs = frames["logs"].to_dict(orient="records")
    if trajectory[:-1] != state["trajectory"] or logs[:-1] != state["logs"]:
        raise ValueError("Environment advancement must preserve acquired history and add one station.")
    if response["md_from_ft"] != state["trajectory"][-1]["md_ft"]:
        raise ValueError("Environment response is stale.")
    atomic_write_json(path, {"trajectory": trajectory, "logs": logs,
                            "commands": state["commands"] + [response]})
