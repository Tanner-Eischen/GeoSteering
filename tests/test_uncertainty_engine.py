"""Pure sequential ensemble checks independent of geological truth or UI."""

from __future__ import annotations

import copy
import json
import math

import numpy as np
import pytest

from app.uncertainty.ensemble import (
    forecast_ensemble,
    initialize_ensemble,
    summarize_ensemble,
    target_probability,
    update_ensemble,
    weighted_quantile,
)
from app.uncertainty.models import EnsembleSettings, EnsembleState

TOP = [{"x_ft": 0, "tvd_ft": 988}, {"x_ft": 10000, "tvd_ft": 1038}]
BASE = [{"x_ft": 0, "tvd_ft": 1012}, {"x_ft": 10000, "tvd_ft": 1062}]


def initial(seed=123, **settings):
    return initialize_ensemble(TOP, BASE, 0, EnsembleSettings(member_count=128, **settings), seed)


def update(state, *, x=0, tvd=1000, gr=80, md=2000, step=0):
    return update_ensemble(state, x, tvd, gr, md, step)


def width(summary, boundary="center"):
    return summary[boundary]["q95"][0] - summary[boundary]["q05"][0]


def test_weighted_quantiles_have_explicit_empirical_cdf_definition():
    actual = weighted_quantile([20, 0, 10, -999], [0.1, 0.1, 0.8, 0], [0, 0.05, 0.1, 0.5, 0.9, 0.95, 1])
    assert actual.tolist() == [0, 0, 0, 10, 10, 20, 20]
    for values, weights, probabilities in [([1], [-1], [.5]), ([math.nan], [1], [.5]),
                                           ([1, 2], [1], [.5]), ([1], [1], [1.1])]:
        with pytest.raises(ValueError):
            weighted_quantile(values, weights, probabilities)


def test_settings_and_state_are_strict_finite_json_serializable():
    for settings in ({"member_count": 16}, {"member_count": 1025}, {"member_count": True},
                     {"center_process_std_ft": math.inf}, {"unknown_setting": 1},
                     {"sensor_clip_min_api": 160, "sensor_clip_max_api": 20}):
        with pytest.raises(ValueError):
            EnsembleSettings(**settings)
    state = initial()
    encoded = json.dumps(state, allow_nan=False)
    assert EnsembleState.model_validate_json(encoded).model_dump(mode="json") == state
    assert len(state["thickness_prior_ft"]) == 64
    for weights in ([0] * 128, [1] * 128):
        altered = {**state, "weights": weights}
        with pytest.raises(ValueError):
            EnsembleState.model_validate(altered)


def test_initialization_uses_only_supplied_model_and_deterministic_namespaced_seed():
    a = initial()
    assert a == initial()
    assert a != initial(seed=124)
    assert np.mean([member["center_tvd_ft"] for member in a["members"]]) == pytest.approx(1000, abs=3)
    assert a["prior_thickness_mean_ft"] == 24
    assert a["last_observation_md_ft"] is None
    shifted = initialize_ensemble([{**p, "tvd_ft": p["tvd_ft"] + 100} for p in TOP],
                                  [{**p, "tvd_ft": p["tvd_ft"] + 100} for p in BASE], 0,
                                  EnsembleSettings(member_count=128))
    np.testing.assert_allclose([member["center_tvd_ft"] + 100 for member in a["members"]],
                               [member["center_tvd_ft"] for member in shifted["members"]])
    # Synthetic sensor uses a different namespace; this engine never consumes
    # or mutates NumPy's global random stream.
    np.random.seed(19)
    expected = np.random.normal(size=3)
    np.random.seed(19)
    initial()
    np.testing.assert_array_equal(np.random.normal(size=3), expected)
    with pytest.raises(ValueError):
        initialize_ensemble(TOP, TOP, 0)


def test_signed_forward_likelihood_updates_center_and_normalizes_weights():
    state = initial()
    deep_bit = update(state, gr=100)
    shallow_bit = update(state, gr=60)
    assert summarize_ensemble(deep_bit)["center"]["q50"][0] < 1000
    assert summarize_ensemble(shallow_bit)["center"]["q50"][0] > 1000
    assert sum(deep_bit["weights"]) == pytest.approx(1)
    assert deep_bit["ess"] == pytest.approx(1 / sum(weight ** 2 for weight in deep_bit["weights"]))
    assert width(summarize_ensemble(update(state))) < width(summarize_ensemble(state))


@pytest.mark.parametrize("reading", [1e6, -1e6, 1e308, -1e308])
def test_extreme_finite_readings_keep_finite_normalized_weights_without_warnings(reading):
    with np.errstate(all="raise"):
        updated = update(initial(), gr=reading)
    assert np.isfinite(updated["weights"]).all()
    assert sum(updated["weights"]) == pytest.approx(1)
    assert 1 <= updated["ess"] <= 128 + 1e-8
    assert updated["last_update"]["predictive_conflict"]
    json.dumps(updated, allow_nan=False)


def test_saturation_forward_likelihood_retains_directional_spread_instead_of_exact_inversion():
    state = initial(prior_center_std_ft=40)
    saturated = update(state, gr=160)
    summary = summarize_ensemble(saturated)
    assert saturated["last_update"]["saturation_status"] == "high"
    assert summary["center"]["q50"][0] < 970
    assert width(summary) > 10
    # A saturated measurement has support well beyond the nominal invertible
    # edge (center=960), rather than collapsing all members onto that edge.
    assert summary["center"]["q05"][0] < 950


def test_previous_low_ess_resamples_before_next_update_but_postweight_ess_is_retained():
    state = initial()
    observed = update(state)
    assert observed["ess"] < 64
    assert not observed["resampled"]
    following = update(observed, x=50, tvd=1000.25, gr=80, md=2050, step=1)
    assert following["resampled"]
    diagnostics = following["last_update"]
    assert diagnostics["previous_posterior_ess"] == observed["ess"]
    assert diagnostics["ess_before_update"] == pytest.approx(128)
    assert following["ess"] == diagnostics["ess_after_update"]
    assert following["ess"] < 128


@pytest.mark.parametrize("reading", [None, math.nan, math.inf, -math.inf])
def test_missing_readings_skip_likelihood_but_propagate_and_consume_identity(reading):
    state = initial()
    updated = update(state, x=50, gr=reading, md=2050, step=1)
    assert not updated["last_update"]["measurement_used"]
    assert updated["last_update"]["saturation_status"] == "missing"
    assert updated["x_ft"] == 50 and updated["last_observation_md_ft"] == 2050
    assert updated["weights"] == state["weights"]
    assert updated["members"] != state["members"]
    with pytest.raises(ValueError, match="duplicate"):
        update(updated, x=50, gr=80, md=2050, step=1)


def test_duplicate_backward_and_invalid_positions_reject_without_mutation():
    observed = update(initial())
    before = copy.deepcopy(observed)
    for changes in ({"x": 0, "md": 2050, "step": 1}, {"x": -1, "md": 2050, "step": 1},
                     {"x": 50, "md": 2000, "step": 1}, {"x": 50, "md": 2050, "step": 0},
                     {"x": math.nan, "md": 2050, "step": 1}):
        with pytest.raises(ValueError):
            update(observed, **changes)
    assert observed == before


def test_prior_and_posterior_calls_from_same_state_share_spatial_random_draws():
    state = update(initial())
    prior = update(state, x=50, tvd=1000.25, gr=None, md=2050, step=1)
    posterior = update(state, x=50, tvd=1000.25, gr=80, md=2050, step=1)
    assert prior["members"] == posterior["members"]
    assert prior["last_update"]["prior_predictive_gr"] == posterior["last_update"]["prior_predictive_gr"]
    assert prior["weights"] != posterior["weights"]


def test_forecast_reuses_fixed_lattice_draws_independent_of_requested_grid():
    state = update(initial())
    before = copy.deepcopy(state)
    sparse = forecast_ensemble(state, [37, 125, 250, 500], seed_key=7)
    dense = forecast_ensemble(state, [0, 25, 37, 50, 100, 125, 200, 250, 300, 400, 500], seed_key=7)
    for index, x in enumerate(sparse["x_ft"]):
        matching = dense["x_ft"].index(x)
        for name in ("center_tvd_ft", "top_tvd_ft", "base_tvd_ft"):
            np.testing.assert_array_equal(np.asarray(sparse["members"][name])[:, index], np.asarray(dense["members"][name])[:, matching])
    single = forecast_ensemble(state, [37], seed_key=7)
    np.testing.assert_array_equal(np.asarray(single["members"]["center_tvd_ft"])[:, 0],
                                   np.asarray(sparse["members"]["center_tvd_ft"])[:, 0])
    origin = forecast_ensemble(state, [0], seed_key=7)
    np.testing.assert_array_equal(np.asarray(origin["members"]["center_tvd_ft"])[:, 0],
                                   np.asarray(dense["members"]["center_tvd_ft"])[:, 0])
    assert forecast_ensemble(state, [500], seed_key=8)["members"] != forecast_ensemble(state, [500], seed_key=7)["members"]
    assert state == before
    assert width(forecast_ensemble(state, [500])) > width(summarize_ensemble(state))
    for grid in ([501], [-1], [50, 25], [math.inf], []):
        with pytest.raises(ValueError):
            forecast_ensemble(state, grid)


def test_current_summary_uses_exact_saved_weights_even_when_forecast_replicates():
    state = update(initial())
    summary = summarize_ensemble(state)
    expected = weighted_quantile([member["center_tvd_ft"] for member in state["members"]], state["weights"])
    assert [summary["center"][key][0] for key in ("q05", "q50", "q95")] == expected.tolist()
    assert not summary["forecast_resampled"]
    assert summary["weights"] == state["weights"]
    assert forecast_ensemble(state, [0])["ess"] == state["ess"]


def test_independent_thickness_prior_does_not_collapse_under_center_weights():
    state = initial()
    selected = copy.deepcopy(state)
    center = selected["members"][0]["center_tvd_ft"]
    for member in selected["members"]:
        member["center_tvd_ft"] = center
    selected["weights"] = [1.0] + [0.0] * 127
    selected["ess"] = 1.0
    summary = summarize_ensemble(selected)
    assert width(summary) == 0
    assert width(summary, "top") > 2
    assert width(summary, "base") > 2
    assert summary["top"]["q50"][0] == pytest.approx(center - np.median(selected["thickness_prior_ft"]) / 2, abs=0.1)
    rejuvenated = update(selected, x=50, tvd=center, md=2050, step=1)
    assert rejuvenated["thickness_prior_ft"] == state["thickness_prior_ft"]
    assert len({member["thickness_ft"] for member in rejuvenated["members"]}) > 10
    future = forecast_ensemble(selected, [0, 500])
    assert future["forecast_resampled"]
    assert future["ess"] == 1
    assert future["center"]["q95"][1] > future["center"]["q05"][1]
    assert selected["ess"] == 1


def test_target_probability_marginalizes_independent_thickness_and_is_bounded():
    state = initial()
    forecast = forecast_ensemble(state, [0, 50])
    values = summarize_ensemble(state, [0, 50], bit_tvd_ft=[1000, 1000.25])["in_zone_probability"]
    assert values[0] == target_probability(forecast, 0, 1000)
    assert values[1] == target_probability(forecast, 1, 1000.25)
    assert 0 < values[0] < 1
    assert target_probability(forecast, 0, 5000) == 0
    with pytest.raises(ValueError):
        target_probability(forecast, 2, 1000)


def test_fork_copy_reproduces_updates_and_serialized_snapshot_is_immutable():
    source = update(initial())
    before = json.dumps(source, sort_keys=True, allow_nan=False)
    first = update(source, x=50, tvd=1000.25, gr=83, md=2050, step=1)
    second = update(json.loads(before), x=50, tvd=1000.25, gr=83, md=2050, step=1)
    assert first == second
    assert json.dumps(source, sort_keys=True, allow_nan=False) == before
