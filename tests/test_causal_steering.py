from __future__ import annotations

import pandas as pd
import pytest

from app.geo.formation import default_scenario
from app.sim.causal import compare_strategies, guided_command, landing_trajectory
from app.sim.environment import (
    commit_environment_step,
    initialize_environment,
    load_environment_frames,
    load_private_scenario,
    preview_environment_step,
)
from app.sim.observation_sampler import sample_station
from app.sim.sim_models import SimulationConfig
from app.sim.trajectory_response import advance_station


def test_opposite_commands_change_future_path_and_logs_under_bounds() -> None:
    scenario = default_scenario()
    previous = landing_trajectory(scenario).iloc[-1].to_dict()
    build, _ = advance_station(previous, "BUILD", max_dls_deg_per_100ft=3.0)
    drop, _ = advance_station(previous, "DROP", max_dls_deg_per_100ft=3.0)
    assert build["tvd_ft"] < drop["tvd_ft"]
    assert build["md_ft"] == drop["md_ft"]
    for station in [build, drop]:
        assert 85.0 <= station["inc_deg"] <= 95.0
        assert station["dls_deg_per_100ft"] <= 3.0 + 1e-8
    # Same random stream isolates the effect of the changed path on observations.
    assert sample_station(build, scenario, 123, 1)["GR"] < sample_station(drop, scenario, 123, 1)["GR"]


def test_command_clipping_and_action_semantics() -> None:
    previous = landing_trajectory(default_scenario()).iloc[-1].to_dict()
    result, response = advance_station(previous, "BUILD", target_inc_deg=110.0)
    assert result["inc_deg"] == 91.5
    assert response["clipped"]
    with pytest.raises(ValueError, match="contradicts"):
        advance_station(previous, "DROP", target_inc_deg=91.0)


def test_policy_uses_observed_center_only() -> None:
    station = {"md_ft": 2000.0, "tvd_ft": 1450.0, "x_ft": 1000.0, "inc_deg": 90.0}
    # GR above calibration center means the well is too deep and should BUILD.
    action, target = guided_command(station, [{**station, "GR": 90.0}])
    assert action == "BUILD"
    assert target > 90
    action, target = guided_command(station, [{**station, "GR": 70.0}])
    assert action == "DROP"
    assert target < 90


def test_completed_controlled_comparison_is_reproducible_and_feasible() -> None:
    first = compare_strategies(seed=123)
    assert first == compare_strategies(seed=123)
    hold, guided = (first["runs"][name] for name in ["hold", "guided"])
    assert hold["trajectory"][:41] == guided["trajectory"][:41]
    assert hold["metrics"]["evaluated_length_ft"] == guided["metrics"]["evaluated_length_ft"] == 5000.0
    assert hold["metrics"]["percent_in_zone"] == pytest.approx(38.0716207966, abs=1e-7)
    assert guided["metrics"]["percent_in_zone"] == pytest.approx(97.1742656784, abs=1e-7)
    for run in [hold, guided]:
        assert run["metrics"]["dls_violation_count"] == 0
        assert len(run["decisions"]) == 100
        assert run["trajectory"][-1]["md_ft"] == 7000.0
        assert all(d["observation"]["md_ft"] == d["md_from_ft"] for d in run["decisions"])


def test_persistent_environment_preview_and_commit_respect_reveal_boundary(tmp_path) -> None:
    scenario = default_scenario()
    prefix = landing_trajectory(scenario)
    future = prefix.iloc[[-1]].copy()
    future["md_ft"] = 7000.0
    future["tvd_ft"] = -999999.0
    source = pd.concat([prefix, future], ignore_index=True)
    frames = {"trajectory": source,
              "logs": pd.DataFrame({"md_ft": [0.0, 2000.0, 7000.0], "GR": [80.0, 80.0, -999999.0], "RES": [40.0] * 3})}
    config = SimulationConfig(active_well_id="active", mode="causal", start_md_ft=2000, end_md_ft=2100,
                              scenario_version=scenario.version)
    initialize_environment(tmp_path, config, frames)
    before = (tmp_path / "environment" / "state.json").read_bytes()
    preview, response = preview_environment_step(tmp_path, config, 2050, 1, "BUILD")
    assert (tmp_path / "environment" / "state.json").read_bytes() == before
    assert load_environment_frames(tmp_path)["trajectory"].md_ft.max() == 2000
    assert preview["trajectory"].md_ft.max() == 2050
    assert preview["trajectory"].tvd_ft.iloc[-1] > 1400
    commit_environment_step(tmp_path, preview, response)
    acquired = load_environment_frames(tmp_path)
    pd.testing.assert_frame_equal(acquired["trajectory"], preview["trajectory"], check_dtype=False)
    assert acquired["logs"].md_ft.max() == 2050
    with pytest.raises(ValueError, match="preserve"):
        commit_environment_step(tmp_path, preview, response)


def test_private_environment_rejects_changed_field(tmp_path) -> None:
    scenario = default_scenario()
    trajectory = landing_trajectory(scenario)
    frames = {"trajectory": trajectory,
              "logs": pd.DataFrame({"md_ft": [2000.0], "GR": [80.0], "RES": [40.0]})}
    config = SimulationConfig(active_well_id="active", mode="causal", start_md_ft=2000, end_md_ft=2100,
                              scenario_version=scenario.version)
    initialize_environment(tmp_path, config, frames)
    assert load_private_scenario(tmp_path).version == scenario.version
    path = tmp_path / "environment" / "scenario.json"
    path.write_text(path.read_text().replace('"disturbance_height_ft": 25.0', '"disturbance_height_ft": 5.0'))
    with pytest.raises(ValueError, match="has changed"):
        load_private_scenario(tmp_path)
