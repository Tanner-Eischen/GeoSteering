from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory
from app.geo.evaluation import evaluate_trajectory
from app.geo.formation import Scenario, default_scenario
from app.geo.observation_model import observed_center_tvd
from app.sim.observation_sampler import sample_station
from app.sim.trajectory_response import advance_station


def guided_command(station: dict[str, float], observations: list[dict[str, float]]) -> tuple[str, float]:
    """Feedback policy: observed layer position, not withheld field parameters."""
    current = observations[-1]
    center = observed_center_tvd(current["tvd_ft"], current["GR"])
    # Regional slope is estimated from trailing sensor observations only.
    recent = observations[-6:]
    if len(recent) >= 3:
        x = np.array([o["x_ft"] for o in recent])
        y = np.array([observed_center_tvd(o["tvd_ft"], o["GR"]) for o in recent])
        slope = float(np.polyfit(x - x[-1], y, 1)[0])
    else:
        slope = 0.0
    desired_slope = np.clip(slope + (center - station["tvd_ft"]) / 150.0, -0.08, 0.08)
    desired_inc = math.degrees(math.acos(float(desired_slope)))
    delta = desired_inc - station["inc_deg"]
    action = "HOLD" if abs(delta) < 0.03 else ("BUILD" if delta > 0 else "DROP")
    return action, float(desired_inc)


def landing_trajectory(scenario: Scenario) -> pd.DataFrame:
    md = np.unique(np.append(np.arange(0.0, scenario.landing_md_ft, 50.0), [scenario.kickoff_md_ft, scenario.landing_md_ft]))
    inc = np.clip((md - scenario.kickoff_md_ft) / (scenario.landing_md_ft - scenario.kickoff_md_ft), 0, 1) * 90.0
    traj = compute_trajectory(pd.DataFrame({"md_ft": md, "inc_deg": inc, "azi_deg": np.full(len(md), 90.0)}))
    traj["x_ft"] = traj["east_ft"]
    return traj


def run_strategy(strategy: str = "guided", scenario: Scenario | None = None, seed: int = 123) -> dict:
    if strategy not in {"hold", "guided"}:
        raise ValueError("Strategy must be hold or guided.")
    scenario = scenario or default_scenario(seed)
    initial = landing_trajectory(scenario)
    records = initial.to_dict(orient="records")
    station = {key: float(value) for key, value in records[-1].items()}
    observations: list[dict[str, float]] = []
    decisions = []
    step_index = 0
    while station["md_ft"] < scenario.max_md_ft - 1e-9:
        log = sample_station(station, scenario, seed, step_index)
        observations.append({**station, **log})
        action, target = ("HOLD", station["inc_deg"]) if strategy == "hold" else guided_command(station, observations)
        next_station, response = advance_station(
            station, action, min(scenario.step_ft, scenario.max_md_ft - station["md_ft"]),
            scenario.max_dls_deg_per_100ft, target,
        )
        decisions.append({"step_index": step_index, "md_from_ft": station["md_ft"], "md_to_ft": next_station["md_ft"],
                          "observation": log, "observed_x_ft": station["x_ft"], "observed_tvd_ft": station["tvd_ft"], **response})
        records.append(next_station)
        station = next_station
        step_index += 1
    # Truth scoring is intentionally performed only after the completed run.
    metrics = evaluate_trajectory(pd.DataFrame(records), scenario)
    metrics["clipped_command_count"] = sum(bool(d["clipped"]) for d in decisions)
    metrics["action_change_count"] = sum(a["action"] != b["action"] for a, b in zip(decisions, decisions[1:]))
    return {"strategy": strategy, "scenario_version": scenario.version, "seed": seed,
            "trajectory": records, "decisions": decisions, "metrics": metrics}


def compare_strategies(scenario: Scenario | None = None, seed: int = 123) -> dict:
    scenario = scenario or default_scenario(seed)
    return {"scenario_version": scenario.version, "seed": seed,
            "runs": {name: run_strategy(name, scenario, seed) for name in ("hold", "guided")}}
