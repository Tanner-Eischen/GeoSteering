"""Sequential spatial particle filter using acquired observations only.

Intervals and probabilities are conditional on the declared process, prior and
nominal clipped sensor model. They are not calibrated field confidence bounds.
Thickness is an independent fixed prior: GR constrains center/dip, not thickness.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from app.uncertainty.models import CalibrationSettings, EnsembleSettings, EnsembleState

_NAMESPACE = 0x47535046  # Separate from every synthetic-instrument random stream.
_QUANTILES = (0.05, 0.50, 0.95)
_THICKNESS_COUNT = 64


def _rng(seed, stream, *keys):
    return np.random.default_rng(np.random.SeedSequence([seed, _NAMESPACE, stream, *keys]))


def _finite(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _counter(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def weighted_quantile(values, weights, quantiles=_QUANTILES):
    """Inverse weighted empirical CDF (leftmost value reaching each probability)."""
    values = np.asarray(values, dtype=float).reshape(-1)
    weights = np.asarray(weights, dtype=float).reshape(-1)
    probabilities = np.atleast_1d(np.asarray(quantiles, dtype=float))
    if not len(values) or values.shape != weights.shape or not np.isfinite(values).all():
        raise ValueError("Weighted quantiles require matching finite values and weights")
    if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
        raise ValueError("Weighted quantile weights must be nonnegative and have positive sum")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Quantile probabilities must lie in [0, 1]")
    positive = weights > 0
    values, weights = values[positive], weights[positive]
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    cumulative /= cumulative[-1]
    indices = np.minimum(np.searchsorted(cumulative, probabilities, side="left"), len(order) - 1)
    return values[order][indices]


def _line(points, x):
    if len(points) < 2:
        raise ValueError("An offset-derived horizon requires at least two spatial points")
    coordinates, values = [], []
    for point in points:
        coordinate = point.get("x_ft") if isinstance(point, dict) else point.x_ft
        depth = point.get("tvd_ft") if isinstance(point, dict) else point.tvd_ft
        coordinates.append(_finite(coordinate, "Horizon x"))
        values.append(_finite(depth, "Horizon TVD"))
    order = np.argsort(coordinates)
    coordinates, values = np.asarray(coordinates)[order], np.asarray(values)[order]
    if (np.diff(coordinates) <= 0).any():
        raise ValueError("Horizon coordinates must be distinct")
    segment = min(max(int(np.searchsorted(coordinates, x, side="right")) - 1, 0), len(values) - 2)
    slope = (values[segment + 1] - values[segment]) / (coordinates[segment + 1] - coordinates[segment])
    return float(values[segment] + slope * (x - coordinates[segment])), float(slope)


def _thickness_prior(mean, relative_std):
    sigma = math.sqrt(math.log1p(relative_std * relative_std))
    mu = math.log(mean) - 0.5 * sigma * sigma
    normal = NormalDist()
    return np.array([math.exp(mu + sigma * normal.inv_cdf((index + 0.5) / _THICKNESS_COUNT))
                     for index in range(_THICKNESS_COUNT)])


def initialize_ensemble(top_points, base_points, x_ft, settings=None, seed=123):
    if isinstance(settings, CalibrationSettings) or isinstance(settings, dict) and settings.get("version") == "spatial-calibration-v2":
        from app.uncertainty.calibration import initialize_calibration
        return initialize_calibration(top_points, base_points, x_ft, settings, seed)
    settings = EnsembleSettings.model_validate(settings.model_dump() if isinstance(settings, EnsembleSettings) else settings or {})
    seed = _counter(seed, "Seed")
    x = _finite(x_ft, "Initial x")
    if x < 0:
        raise ValueError("Initial x must be nonnegative")
    top, top_dip = _line(top_points, x)
    base, base_dip = _line(base_points, x)
    if base <= top:
        raise ValueError("Offset-derived target thickness must be positive at initialization")
    center, dip = (top + base) / 2, (top_dip + base_dip) / 2
    if abs(dip) > settings.dip_bound:
        raise ValueError("Offset-derived dip exceeds the declared prior bound")
    count = settings.member_count
    random = _rng(seed, 0)
    centers = center + random.normal(0, settings.prior_center_std_ft, count)
    dips = np.clip(dip + random.normal(0, settings.prior_dip_std, count), -settings.dip_bound, settings.dip_bound)
    prior = _thickness_prior(base - top, settings.prior_thickness_relative_std)
    thickness = _rng(seed, 1).choice(prior, count)
    return EnsembleState(
        settings=settings, seed=seed, x_ft=x,
        members=[{"center_tvd_ft": float(a), "dip": float(b), "thickness_ft": float(c)} for a, b, c in zip(centers, dips, thickness)],
        weights=[1 / count] * count, thickness_prior_ft=prior.tolist(), prior_thickness_mean_ft=base - top,
        ess=float(count), last_update={"measurement_used": False, "skip_reason": "No measurements assimilated"},
    ).model_dump(mode="json")


def _systematic_resample(weights, random):
    positions = (random.uniform() + np.arange(len(weights))) / len(weights)
    cumulative = np.cumsum(weights)
    cumulative[-1] = 1.0
    return np.searchsorted(cumulative, positions, side="right")


def _propagate(centers, dips, dx, settings, random):
    updated_centers, updated_dips = centers.copy(), dips.copy()
    # Use the same bounded spatial kernel for assimilation gaps and forecasts,
    # so a long measurement interval still accumulates evolving dip uncertainty.
    spacing = min(settings.process_reference_step_ft, settings.forecast_grid_step_ft)
    if math.ceil(dx / spacing) > 10000:
        raise ValueError("Observation gap requires more than 10,000 process substeps")
    remaining = dx
    while remaining > 0:
        length = min(remaining, spacing)
        scale = math.sqrt(length / settings.process_reference_step_ft)
        draws = random.normal(size=(len(centers), 2))
        updated_centers += updated_dips * length + settings.center_process_std_ft * scale * draws[:, 0]
        updated_dips = np.clip(updated_dips + settings.dip_process_std * scale * draws[:, 1],
                               -settings.dip_bound, settings.dip_bound)
        remaining -= length
    return updated_centers, updated_dips


def _predictive_quantiles(means, weights, sigma, random):
    # Eight independent assumed-error draws per particle describe the forward
    # predictive mixture. These draws never enter the likelihood or state.
    predictive = means[:, None] + sigma * random.normal(size=(len(means), 8))
    return weighted_quantile(predictive.ravel(), np.repeat(weights, 8) / 8)


def update_ensemble(state, x_ft, tvd_ft, gr_api, observation_md_ft, step_index):
    """Return a new state; never mutate the supplied history snapshot.

    Resample an exhausted previous posterior before propagation. Missing GR
    still advances the spatial state and consumes its observation identity.
    First observation may share the initialization x; subsequent x and MD must
    advance strictly, preventing duplicate measurements from adding likelihood.
    """
    if isinstance(state, dict) and state.get("version") == "spatial-calibration-state-v2":
        from app.uncertainty.calibration import update_calibration
        return update_calibration(state, x_ft, tvd_ft, gr_api, observation_md_ft, step_index)
    current = EnsembleState.model_validate(state)
    settings, count = current.settings, current.settings.member_count
    x, tvd, md = _finite(x_ft, "Observation x"), _finite(tvd_ft, "Observation TVD"), _finite(observation_md_ft, "Observation MD")
    step = _counter(step_index, "Step index")
    if x < current.x_ft or (current.update_count and x <= current.x_ft):
        raise ValueError("Observation x must advance monotonically; duplicate or backwards measurements are rejected")
    if md < 0 or (current.last_observation_md_ft is not None and md <= current.last_observation_md_ft):
        raise ValueError("Observation MD must advance; duplicate or backwards measurements are rejected")
    if current.step_index is not None and step <= current.step_index:
        raise ValueError("Observation step must advance; duplicate steps are rejected")
    centers = np.array([member.center_tvd_ft for member in current.members])
    dips = np.array([member.dip for member in current.members])
    thickness = np.array([member.thickness_ft for member in current.members])
    weights = np.array(current.weights)
    resampled = current.ess < settings.resample_ess_fraction * count
    if resampled:
        random = _rng(current.seed, 2, current.update_count)
        selected = _systematic_resample(weights, random)
        centers, dips = centers[selected], dips[selected]
        # The clipped GR likelihood cannot identify thickness. Rejuvenate from
        # its original independent prior rather than inheriting weight artifacts.
        thickness = random.choice(current.thickness_prior_ft, count)
        weights = np.full(count, 1 / count)
    centers, dips = _propagate(centers, dips, x - current.x_ft, settings, _rng(current.seed, 3, current.update_count))
    means = np.clip(settings.sensor_center_api + settings.sensor_gradient_api_per_ft * (tvd - centers),
                    settings.sensor_clip_min_api, settings.sensor_clip_max_api)
    sigma = math.hypot(settings.sensor_noise_std_api, settings.model_discrepancy_std_api)
    predictive = _predictive_quantiles(means, weights, sigma, _rng(current.seed, 4, current.update_count))
    try:
        observation = float(gr_api) if gr_api is not None and not isinstance(gr_api, bool) else float("nan")
    except (TypeError, ValueError):
        observation = float("nan")
    used = math.isfinite(observation)
    prior_ess = float(1 / np.dot(weights, weights))
    if used:
        # Cancel the common squared-observation term algebraically. This avoids
        # squaring a huge finite reading, which can overflow even long double
        # on Windows. The closest supported mean has relative likelihood zero.
        supported = np.flatnonzero(weights > 0)
        supported_means = means[supported]
        reference = float(np.clip(observation, supported_means.min(), supported_means.max()))
        if supported_means.min() < observation < supported_means.max():
            reference = supported_means[np.argmin(np.abs(observation - supported_means))]
        delta = (supported_means - reference) / sigma
        with np.errstate(over="ignore", invalid="ignore"):
            relative = delta * ((observation - reference) / sigma) - 0.5 * delta * delta
        log_weights = np.full(count, -np.inf)
        log_weights[supported] = np.log(weights[supported]) + np.minimum(relative, 0)
        with np.errstate(over="ignore"):
            log_weights -= np.max(log_weights)
        with np.errstate(under="ignore"):
            weights = np.asarray(np.exp(log_weights), dtype=float)
        weights /= weights.sum()
    ess = float(1 / np.dot(weights, weights))
    status = "missing" if not used else ("low" if observation <= settings.sensor_clip_min_api else (
        "high" if observation >= settings.sensor_clip_max_api else "none"))
    diagnostics = {
        "measurement_used": used, "skip_reason": None if used else "Missing or nonfinite GR",
        "prior_predictive_gr": dict(zip(("q05", "q50", "q95"), map(float, predictive))),
        "predictive_conflict": bool(used and (observation < predictive[0] or observation > predictive[2])),
        "saturation_status": status, "ess_before_update": prior_ess, "ess_after_update": ess,
        "previous_posterior_ess": current.ess, "resampled": resampled,
        "observation_md_ft": md, "observation_x_ft": x,
        "predictive_interval_probability": 0.90,
        "max_posterior_weight": float(weights.max()),
        "resample_before_next_update": bool(ess < settings.resample_ess_fraction * count),
    }
    return EnsembleState(
        settings=settings, seed=current.seed, x_ft=x,
        members=[{"center_tvd_ft": float(a), "dip": float(b), "thickness_ft": float(c)} for a, b, c in zip(centers, dips, thickness)],
        weights=weights.tolist(), thickness_prior_ft=current.thickness_prior_ft,
        prior_thickness_mean_ft=current.prior_thickness_mean_ft,
        last_observation_md_ft=md, step_index=step, update_count=current.update_count + 1,
        ess=ess, resampled=resampled, last_update=diagnostics,
    ).model_dump(mode="json")


def _summaries(centers, weights, prior):
    result = {name: {key: [] for key in ("q05", "q50", "q95")} for name in ("center", "top", "base")}
    product_weights = np.repeat(weights, len(prior)) / len(prior)
    for column in centers.T:
        values = {"center": weighted_quantile(column, weights)}
        for name, direction in (("top", -1), ("base", 1)):
            values[name] = weighted_quantile((column[:, None] + direction * prior[None, :] / 2).ravel(), product_weights)
        for name, quantiles in values.items():
            for key, value in zip(("q05", "q50", "q95"), quantiles):
                result[name][key].append(float(value))
    return result


def _forecast_payload(current, queries, centers, weights, thickness, resampled):
    prior = np.array(current.thickness_prior_ft)
    thickness = np.asarray(thickness)[:, None]
    return {
        "x_ft": queries.tolist(), **_summaries(centers, weights, prior),
        "members": {"center_tvd_ft": centers.tolist(), "top_tvd_ft": (centers - thickness / 2).tolist(),
                    "base_tvd_ft": (centers + thickness / 2).tolist()},
        "weights": weights.tolist(), "thickness_prior_ft": current.thickness_prior_ft,
        "ess": current.ess, "forecast_resampled": resampled, "interval_probability": 0.90,
        "note": "Conditional assumed-model intervals; independent thickness prior; not field-calibrated confidence",
    }


def forecast_ensemble(state, x_grid, seed_key=0):
    """Forecast on one fixed spatial lattice, independent of requested positions.

    Non-lattice queries linearly interpolate the same member paths. Queries must
    be nondecreasing and lie between current x and current x + 500 ft. No sensor
    measurements are generated and no observation likelihood is added.
    """
    if isinstance(state, dict) and state.get("version") == "spatial-calibration-state-v2":
        from app.uncertainty.calibration import forecast_calibration
        return forecast_calibration(state, x_grid, seed_key)
    current = EnsembleState.model_validate(state)
    key = _counter(seed_key, "Forecast seed key")
    queries = np.atleast_1d(np.asarray(x_grid, dtype=float))
    if queries.ndim != 1 or not len(queries) or not np.isfinite(queries).all():
        raise ValueError("Forecast x grid must be a nonempty finite one-dimensional sequence")
    if (np.diff(queries) < 0).any() or (queries < current.x_ft).any() or (queries > current.x_ft + 500 + 1e-9).any():
        raise ValueError("Forecast x grid must be ordered within current x through +500 ft")
    spacing = current.settings.forecast_grid_step_ft
    nodes = max(1, int(math.ceil((queries[-1] - current.x_ft) / spacing)))
    lattice = current.x_ft + np.arange(nodes + 1) * spacing
    centers = np.array([member.center_tvd_ft for member in current.members])
    dips = np.array([member.dip for member in current.members])
    thickness = np.array([member.thickness_ft for member in current.members])
    weights = np.array(current.weights)
    random = _rng(current.seed, 5, current.update_count, key)
    forecast_resampled = current.ess < current.settings.resample_ess_fraction * len(weights)
    if forecast_resampled:
        # Replicate a concentrated posterior before drawing future process
        # paths. Otherwise ESS=1 would imply one future draw and zero apparent
        # process uncertainty. This never alters the saved posterior or its ESS.
        selected = _systematic_resample(weights, random)
        centers, dips = centers[selected], dips[selected]
        thickness = random.choice(current.thickness_prior_ft, len(weights))
        weights = np.full(len(weights), 1 / len(weights))
    paths = [centers.copy()]
    for _ in range(nodes):
        centers, dips = _propagate(centers, dips, spacing, current.settings, random)
        paths.append(centers.copy())
    interpolated = np.array([np.interp(queries, lattice, path) for path in np.array(paths).T])
    return _forecast_payload(current, queries, interpolated, weights, thickness, forecast_resampled)


def target_probability(forecast, x_index, tvd_ft):
    """Marginalize center posterior × independent uniform thickness prior."""
    tvd = _finite(tvd_ft, "Bit TVD")
    if type(x_index) is not int or not 0 <= x_index < len(forecast["x_ft"]):
        raise ValueError("Select a valid forecast x index")
    centers = np.asarray(forecast["members"]["center_tvd_ft"], dtype=float)[:, x_index]
    prior = np.asarray(forecast["thickness_prior_ft"], dtype=float)
    conditional = np.mean(np.abs(centers[:, None] - tvd) <= prior[None, :] / 2, axis=1)
    return float(np.clip(np.dot(np.asarray(forecast["weights"]), conditional), 0, 1))


def summarize_ensemble(state, x_grid=None, bit_tvd_ft=None):
    """Weighted nominal 90% model intervals, with optional target probability."""
    if isinstance(state, dict) and state.get("version") == "spatial-calibration-state-v2":
        from app.uncertainty.calibration import summarize_calibration
        return summarize_calibration(state, x_grid, bit_tvd_ft)
    current = EnsembleState.model_validate(state)
    if x_grid is None:
        # Current summaries use the exact saved posterior weights, without
        # forecast-only Monte Carlo replication.
        centers = np.array([member.center_tvd_ft for member in current.members])[:, None]
        summary = _forecast_payload(current, np.array([current.x_ft]), centers, np.array(current.weights),
                                    [member.thickness_ft for member in current.members], False)
    else:
        summary = forecast_ensemble(state, x_grid)
    if bit_tvd_ft is not None:
        depths = np.atleast_1d(np.asarray(bit_tvd_ft, dtype=float))
        if len(depths) == 1:
            depths = np.repeat(depths, len(summary["x_ft"]))
        if len(depths) != len(summary["x_ft"]):
            raise ValueError("Bit TVD must be scalar or match the x grid")
        summary["in_zone_probability"] = [target_probability(summary, index, depth) for index, depth in enumerate(depths)]
    return summary


def target_probability_range(forecast, x_index, tvd_ft):
    """Conditional probability sensitivity across fixed calibration hypotheses."""
    components = forecast.get("calibration_components")
    if not components:
        value = target_probability(forecast, x_index, tvd_ft)
        return value, value
    values = [target_probability(component["forecast"], x_index, tvd_ft) for component in components]
    return min(values), max(values)
