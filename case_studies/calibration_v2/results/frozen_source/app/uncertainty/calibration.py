"""Fixed-weight calibration sensitivity around the unchanged v1 filter.

Each bias changes the latent sensor center before clipping. Hypothesis weights
are declared equal, retained over time, and never inferred from GR. This keeps
calibration/geology confounding visible instead of selecting a single bias.
"""

from __future__ import annotations

from copy import deepcopy

import numpy as np

from app.uncertainty import ensemble as engine
from app.uncertainty.models import CalibrationSettings, CalibrationState


def _aggregate_diagnostics(components):
    diagnostics = [component["ensemble"]["last_update"] for component in components]
    if len(diagnostics) == 1:
        return deepcopy(diagnostics[0])
    used = all(item.get("measurement_used", False) for item in diagnostics)
    result = {
        "measurement_used": used,
        "skip_reason": diagnostics[0].get("skip_reason"),
        "predictive_conflict": bool(used and all(item.get("predictive_conflict", False) for item in diagnostics)),
        "any_conditional_predictive_conflict": any(item.get("predictive_conflict", False) for item in diagnostics),
        "conditional_predictive_conflict": [bool(item.get("predictive_conflict", False)) for item in diagnostics],
        "predictive_conflict_basis": "Outside every conditional nominal 90% predictive interval; hypothesis weights are fixed",
    }
    for key in ("ess_before_update", "ess_after_update", "previous_posterior_ess"):
        if key in diagnostics[0]:
            result[key] = min(item[key] for item in diagnostics)
    for key in ("saturation_status", "observation_md_ft", "observation_x_ft"):
        if key in diagnostics[0]:
            result[key] = diagnostics[0][key]
    if "prior_predictive_gr" in diagnostics[0]:
        result["prior_predictive_gr"] = {
            "q05": min(item["prior_predictive_gr"]["q05"] for item in diagnostics),
            "q95": max(item["prior_predictive_gr"]["q95"] for item in diagnostics),
        }
        result["predictive_interval_basis"] = "Envelope of conditional nominal 90% intervals; no 90% envelope coverage guarantee"
    result["resampled"] = any(component["ensemble"]["resampled"] for component in components)
    result["resample_before_next_update"] = any(item.get("resample_before_next_update", False) for item in diagnostics)
    return result


def _state(settings, components):
    first = components[0]["ensemble"]
    return CalibrationState(
        settings=settings, seed=first["seed"], x_ft=first["x_ft"],
        step_index=first["step_index"], last_observation_md_ft=first["last_observation_md_ft"],
        update_count=first["update_count"], components=components,
        ess=min(component["ensemble"]["ess"] for component in components),
        resampled=any(component["ensemble"]["resampled"] for component in components),
        last_update=_aggregate_diagnostics(components),
    ).model_dump(mode="json")


def initialize_calibration(top_points, base_points, x_ft, settings, seed):
    settings = CalibrationSettings.model_validate(settings.model_dump() if isinstance(settings, CalibrationSettings) else settings)
    weight = 1.0 / len(settings.calibration_biases_api)
    components = [{
        "bias_api": bias, "weight": weight,
        "ensemble": engine.initialize_ensemble(top_points, base_points, x_ft, settings.conditional_settings(bias), seed),
    } for bias in settings.calibration_biases_api]
    return _state(settings, components)


def update_calibration(state, x_ft, tvd_ft, gr_api, observation_md_ft, step_index):
    current = CalibrationState.model_validate(state)
    components = [{
        "bias_api": component.bias_api, "weight": component.weight,
        "ensemble": engine.update_ensemble(component.ensemble.model_dump(mode="json"), x_ft, tvd_ft,
                                             gr_api, observation_md_ft, step_index),
    } for component in current.components]
    return _state(current.settings, components)


def _pool(component_forecasts):
    first = component_forecasts[0]["forecast"]
    queries = first["x_ft"]
    prior = first["thickness_prior_ft"]
    if any(component["forecast"]["x_ft"] != queries or component["forecast"]["thickness_prior_ft"] != prior
           for component in component_forecasts):
        raise ValueError("Conditional calibration forecasts must share query positions and independent thickness prior")
    if len(component_forecasts) == 1:
        # Exact one-hypothesis reduction, including original floating point
        # ordering, weighted quantiles, member arrays and note text.
        result = deepcopy(first)
    else:
        members = {name: [path for component in component_forecasts for path in component["forecast"]["members"][name]]
                   for name in ("center_tvd_ft", "top_tvd_ft", "base_tvd_ft")}
        weights = np.array([component["weight"] * weight for component in component_forecasts
                            for weight in component["forecast"]["weights"]])
        # Quantiles are of the pooled empirical distribution, not averages of
        # conditional quantiles. Thickness remains independently marginalized.
        result = {
            "x_ft": deepcopy(queries),
            **engine._summaries(np.asarray(members["center_tvd_ft"]), weights, np.asarray(prior)),
            "members": members, "weights": weights.tolist(), "thickness_prior_ft": deepcopy(prior),
            "ess": min(component["forecast"]["ess"] for component in component_forecasts),
            "forecast_resampled": any(component["forecast"]["forecast_resampled"] for component in component_forecasts),
            "interval_probability": 0.90,
            "note": "Equal fixed calibration hypotheses; pooled nominal 90% assumed-model intervals; sensitivity envelope has no 90% coverage guarantee",
        }
    result["calibration_components"] = component_forecasts
    result["calibration_biases_api"] = [component["bias_api"] for component in component_forecasts]
    result["conditional_ess"] = [component["forecast"]["ess"] for component in component_forecasts]
    result["calibration_envelope"] = {
        boundary: {
            "q05": [min(component["forecast"][boundary]["q05"][index] for component in component_forecasts)
                    for index in range(len(queries))],
            "q50": deepcopy(result[boundary]["q50"]),
            "q95": [max(component["forecast"][boundary]["q95"][index] for component in component_forecasts)
                    for index in range(len(queries))],
        } for boundary in ("center", "top", "base")
    }
    result["calibration_envelope_note"] = "Min/max of conditional nominal 90% bounds; not a calibrated or guaranteed 90% interval"
    return result


def forecast_calibration(state, x_grid, seed_key=0):
    current = CalibrationState.model_validate(state)
    components = [{
        "bias_api": component.bias_api, "weight": component.weight,
        "forecast": engine.forecast_ensemble(component.ensemble.model_dump(mode="json"), x_grid, seed_key),
    } for component in current.components]
    return _pool(components)


def summarize_calibration(state, x_grid=None, bit_tvd_ft=None):
    current = CalibrationState.model_validate(state)
    components = [{
        "bias_api": component.bias_api, "weight": component.weight,
        "forecast": engine.summarize_ensemble(component.ensemble.model_dump(mode="json"), x_grid),
    } for component in current.components]
    result = _pool(components)
    if bit_tvd_ft is not None:
        depths = np.atleast_1d(np.asarray(bit_tvd_ft, dtype=float))
        if len(depths) == 1:
            depths = np.repeat(depths, len(result["x_ft"]))
        if len(depths) != len(result["x_ft"]):
            raise ValueError("Bit TVD must be scalar or match the x grid")
        result["in_zone_probability"] = [engine.target_probability(result, index, depth) for index, depth in enumerate(depths)]
        ranges = [engine.target_probability_range(result, index, depth) for index, depth in enumerate(depths)]
        result["in_zone_probability_range"] = {"min": [value[0] for value in ranges], "max": [value[1] for value in ranges]}
    return result
