"""Fixed calibration sensitivity preserves the original conditional v1 engine."""

from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np
import pytest

from app.uncertainty.ensemble import (
    forecast_ensemble,
    initialize_ensemble,
    summarize_ensemble,
    target_probability,
    target_probability_range,
    update_ensemble,
    weighted_quantile,
)
from app.uncertainty.models import CalibrationSettings, CalibrationState, EnsembleSettings

TOP = [{"x_ft": 0, "tvd_ft": 988}, {"x_ft": 10000, "tvd_ft": 1038}]
BASE = [{"x_ft": 0, "tvd_ft": 1012}, {"x_ft": 10000, "tvd_ft": 1062}]


def initial(**settings):
    return initialize_ensemble(TOP, BASE, 0, CalibrationSettings(member_count=32, **settings), seed=123)


def advance(state, x=0, tvd=1000, gr=92, md=2000, step=0):
    return update_ensemble(state, x, tvd, gr, md, step)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def test_original_v1_serialized_outputs_are_byte_equivalent_to_pre_v2_reference():
    state = initialize_ensemble(TOP, BASE, 0, {"member_count": 32}, seed=123)
    updated = advance(state, gr=80)
    outputs = [state, updated, summarize_ensemble(updated, bit_tvd_ft=1000),
               forecast_ensemble(updated, [0, 37, 250, 500], seed_key=9)]
    assert [digest(value) for value in outputs] == [
        "9874fb6fe5bba2e1cb84e5716040bc4da1c1b556e6d9c94bdda487dda81bc27b",
        "9f8ec6f3ef907676a68579c68f2c8b5bc12da982cf39422ba7db6ad481367522",
        "36b0cb570c6d339c506215d76536e7807b7ffd80edc630027bba0bf253227b90",
        "73620017ee2b6889ae68b7cccbde126a30bfa3529e5b0606d85f7b0e54d03b70",
    ]


def test_single_zero_hypothesis_reduces_exactly_to_v1_states_and_payloads():
    wrapped = initial(calibration_biases_api=(0,))
    original = initialize_ensemble(TOP, BASE, 0, {"member_count": 32}, seed=123)
    assert wrapped["components"][0]["ensemble"] == original
    for x, reading, step in [(0, 80, 0), (50, None, 1), (100, 88, 2), (150, 160, 3)]:
        wrapped = advance(wrapped, x=x, tvd=1000 + 0.005 * x, gr=reading, md=2000 + x, step=step)
        original = advance(original, x=x, tvd=1000 + 0.005 * x, gr=reading, md=2000 + x, step=step)
        assert wrapped["components"][0]["ensemble"] == original
        assert wrapped["ess"] == original["ess"]
        assert wrapped["last_update"] == original["last_update"]
    for actual, expected in (
        (summarize_ensemble(wrapped, bit_tvd_ft=1000), summarize_ensemble(original, bit_tvd_ft=1000)),
        (forecast_ensemble(wrapped, [150, 187, 400, 650], seed_key=7),
         forecast_ensemble(original, [150, 187, 400, 650], seed_key=7)),
    ):
        assert {key: actual[key] for key in expected} == expected
        probability = target_probability(expected, 0, 1000)
        assert target_probability_range(actual, 0, 1000) == (probability, probability)


@pytest.mark.parametrize("biases", [(), (-8, 8), (0, 0), (8, 0), (-41, 0, 8),
                                    (0, math.inf), (False,), ("0",), tuple(range(-4, 6))])
def test_calibration_hypotheses_are_strict_finite_sorted_unique_and_bounded(biases):
    with pytest.raises(ValueError):
        CalibrationSettings(calibration_biases_api=biases)


def test_json_settings_and_component_state_validation_retain_fixed_weights():
    state = initial()
    assert state["version"] == "spatial-calibration-state-v2"
    assert state["settings"]["version"] == "spatial-calibration-v2"
    assert CalibrationState.model_validate_json(json.dumps(state, allow_nan=False)).model_dump(mode="json") == state
    assert [component["weight"] for component in state["components"]] == [0.2] * 5
    assert [component["ensemble"]["settings"]["sensor_center_api"] for component in state["components"]] == [64, 72, 80, 88, 96]
    assert all(component["ensemble"]["seed"] == 123 for component in state["components"])
    with pytest.raises(ValueError, match="nominal 80 API"):
        CalibrationSettings(sensor_center_api=90)


def test_bias_is_applied_inside_clipping_without_subtracting_from_observations():
    wrapped = initial(prior_center_std_ft=40)
    actual = advance(wrapped, gr=160)
    conditional = actual["components"][-1]["ensemble"]
    matched = initialize_ensemble(TOP, BASE, 0, EnsembleSettings(member_count=32, prior_center_std_ft=40, sensor_center_api=96), seed=123)
    matched = advance(matched, gr=160)
    assert conditional == matched
    wrong = initialize_ensemble(TOP, BASE, 0, EnsembleSettings(member_count=32, prior_center_std_ft=40), seed=123)
    wrong = advance(wrong, gr=160 - 16)
    assert not np.allclose(conditional["weights"], wrong["weights"])
    assert conditional["last_update"]["saturation_status"] == "high"
    assert wrong["last_update"]["saturation_status"] == "none"


def test_hypothesis_weights_and_zero_branch_persist_despite_different_likelihoods():
    state = initial()
    reference = initialize_ensemble(TOP, BASE, 0, {"member_count": 32}, seed=123)
    for step in range(12):
        x = step * 50
        state = advance(state, x=x, tvd=1000 + x * .005, gr=112, md=2000 + x, step=step)
        reference = advance(reference, x=x, tvd=1000 + x * .005, gr=112, md=2000 + x, step=step)
        assert [component["weight"] for component in state["components"]] == [0.2] * 5
        assert state["components"][2]["ensemble"] == reference
        assert state["ess"] == min(component["ensemble"]["ess"] for component in state["components"])
    assert state["components"][0]["ensemble"]["weights"] != state["components"][-1]["ensemble"]["weights"]


def test_pooled_quantiles_are_inverse_cdf_and_probability_is_weighted_marginal():
    state = initial(calibration_biases_api=(-8, 0, 8))
    for component, center in zip(state["components"], (0, 10, 100)):
        for member in component["ensemble"]["members"]:
            member["center_tvd_ft"] = center
    summary = summarize_ensemble(state, bit_tvd_ft=10)
    assert summary["center"] == {"q05": [0], "q50": [10], "q95": [100]}
    conditional_medians = [component["forecast"]["center"]["q50"][0] for component in summary["calibration_components"]]
    assert summary["center"]["q50"][0] != sum(conditional_medians) / 3
    centers = np.asarray(summary["members"]["center_tvd_ft"])[:, 0]
    prior = np.asarray(summary["thickness_prior_ft"])
    weights = np.asarray(summary["weights"])
    expected_top = weighted_quantile((centers[:, None] - prior[None, :] / 2).ravel(), np.repeat(weights, len(prior)) / len(prior))
    assert [summary["top"][key][0] for key in ("q05", "q50", "q95")] == expected_top.tolist()
    probabilities = [target_probability(component["forecast"], 0, 10) for component in summary["calibration_components"]]
    assert target_probability(summary, 0, 10) == pytest.approx(sum(probabilities) / 3)
    assert target_probability_range(summary, 0, 10) == (min(probabilities), max(probabilities))
    assert summary["in_zone_probability_range"] == {"min": [min(probabilities)], "max": [max(probabilities)]}
    for boundary in ("center", "top", "base"):
        envelope = summary["calibration_envelope"][boundary]
        assert envelope["q05"][0] == min(component["forecast"][boundary]["q05"][0] for component in summary["calibration_components"])
        assert envelope["q95"][0] == max(component["forecast"][boundary]["q95"][0] for component in summary["calibration_components"])
        assert envelope["q50"] == summary[boundary]["q50"]


def test_conditional_branches_share_initial_process_draws_and_query_grid_is_reusable():
    prior = initial()
    forecasts = forecast_ensemble(prior, [0, 37, 250, 500], seed_key=9)
    baseline_paths = forecasts["calibration_components"][0]["forecast"]["members"]
    assert all(component["forecast"]["members"] == baseline_paths for component in forecasts["calibration_components"])
    updated = advance(prior)
    before = copy.deepcopy(updated)
    sparse = forecast_ensemble(updated, [0, 37, 250, 500], seed_key=9)
    dense = forecast_ensemble(updated, [0, 25, 37, 50, 100, 250, 400, 500], seed_key=9)
    for index, x in enumerate(sparse["x_ft"]):
        other = dense["x_ft"].index(x)
        for name in ("center_tvd_ft", "top_tvd_ft", "base_tvd_ft"):
            np.testing.assert_array_equal(np.asarray(sparse["members"][name])[:, index], np.asarray(dense["members"][name])[:, other])
    assert updated == before
    assert sparse["ess"] == updated["ess"]
    assert sparse["conditional_ess"] == [component["ensemble"]["ess"] for component in updated["components"]]


def test_missing_and_duplicate_updates_preserve_snapshot_and_support_floor():
    state = initial()
    before = digest(state)
    predicted = advance(state, gr=None)
    assert not predicted["last_update"]["measurement_used"]
    assert digest(state) == before
    assert [component["weight"] for component in predicted["components"]] == [.2] * 5
    for changes in ({}, {"x": -1}, {"x": 50, "md": 1999, "step": 1}):
        with pytest.raises(ValueError):
            advance(predicted, **changes)
    first = advance(predicted, x=50, md=2050, step=1)
    second = advance(json.loads(json.dumps(predicted)), x=50, md=2050, step=1)
    assert first == second


@pytest.mark.parametrize("corruption", ["weight", "seed", "bias", "settings", "timing", "ess", "thickness", "resampled"])
def test_corrupt_component_contracts_are_rejected(corruption):
    state = initial()
    component = state["components"][0]
    if corruption == "weight":
        component["weight"] = .3
    elif corruption == "seed":
        component["ensemble"]["seed"] = 124
    elif corruption == "bias":
        component["bias_api"] = -15
    elif corruption == "settings":
        component["ensemble"]["settings"]["sensor_center_api"] += 1
    elif corruption == "timing":
        component["ensemble"]["x_ft"] = 1
    elif corruption == "ess":
        state["ess"] = 31
    elif corruption == "thickness":
        component["ensemble"]["thickness_prior_ft"][0] += .01
    else:
        state["resampled"] = True
    with pytest.raises(ValueError):
        summarize_ensemble(state)


def test_probability_range_v1_and_mixture_summaries_validate_position_inputs():
    v1 = initialize_ensemble(TOP, BASE, 0, {"member_count": 32}, seed=123)
    forecast = forecast_ensemble(v1, [0])
    value = target_probability(forecast, 0, 1000)
    assert target_probability_range(forecast, 0, 1000) == (value, value)
    with pytest.raises(ValueError):
        summarize_ensemble(initial(), [0, 50], bit_tvd_ft=[1, 2, 3])
