"""Predeclared uncertainty-quality study on fixed synthetic HOLD observations.

Only the instrument and post-trial scorer receive a private geological Scenario.
The ensemble receives observed offset control points and acquired pose/GR only.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from app.geo.formation import Scenario, formation_top_base
from app.model.schemas import ControlPoint
from app.sim.causal import landing_trajectory
from app.sim.trajectory_response import advance_station
from app.study.robustness import (
    StrictModel,
    StudyCase,
    _check_relative_path,
    freeze_sources,
    offset_evidence,
    sample_instrument,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "case_studies" / "uncertainty_v1" / "manifest.json"
if not DEFAULT_MANIFEST.is_file():
    DEFAULT_MANIFEST = Path(sys.prefix) / "share" / "geosteering" / "case_studies" / "uncertainty_v1" / "manifest.json"
DEFAULT_RESULTS = DEFAULT_MANIFEST.parent / "results"
PHASES = {
    "prior_current": "Current pre-observation prior",
    "posterior_current": "Current posterior",
    "forecast_250": "250-ft forecast",
    "forecast_500": "500-ft forecast",
}
NOTES = [
    "This fixed-HOLD study assesses center-interval quality, not steering-policy performance or operational safety.",
    "Nominal 90% intervals are conditional on the fixed particle model and signed-GR calibration; empirical coverage can differ substantially.",
    "Cases are handpicked, with development and evaluation geology and seeds kept distinct. Equal-case summaries are descriptive, not population confidence statements.",
    "Current prior and posterior intervals use the same truth locations. Each forecast horizon excludes targets beyond the evaluated x domain; paired-origin results use only origins valid for both horizons.",
    "Coverage and width are computed within each trial before equal-trial and equal-case averaging. Correlated MD points are not independent inferential samples.",
    "Missing GR propagates without weighting. Available clipped GR uses the model's clipped forward likelihood, rather than exact center inversion.",
    "Exact synthetic offset picks and known sensor assumptions remain strong simplifications. Center coverage does not validate thickness or top/base uncertainty.",
    "The evaluated cases are now observed; future changes need new held-out cases. Repeating this protocol checks reproducibility, not independent confirmation.",
]


class CalibrationManifest(StrictModel):
    schema_version: Literal[1]
    study_id: str
    engine_version: Literal["signed-gr-particle-ensemble-v1"]
    nominal_level: Literal[0.9]
    forecast_horizons_ft: list[float]
    ensemble_seed_offset: int = Field(ge=0)
    development_seeds: list[int] = Field(min_length=1)
    evaluation_seeds: list[int] = Field(min_length=1)
    settings: dict
    cases: list[StudyCase] = Field(min_length=2)

    @model_validator(mode="after")
    def predeclared_design(self):
        if self.forecast_horizons_ft != [250.0, 500.0]:
            raise ValueError("This study declares exactly 250-ft and 500-ft forecast horizons")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique")
        for seeds in (self.development_seeds, self.evaluation_seeds):
            if len(set(seeds)) != len(seeds) or any(type(seed) is not int or seed < 0 for seed in seeds):
                raise ValueError("Seeds must be unique nonnegative integers")
        if set(self.development_seeds) & set(self.evaluation_seeds):
            raise ValueError("Development and evaluation noise seeds must be disjoint")
        signatures = {split: set() for split in ("development", "evaluation")}
        for case in self.cases:
            if case.sensor.delay_steps:
                raise ValueError("Delayed measurements are not part of uncertainty study v1")
            scenario = Scenario(**case.geology)
            signatures[case.split].add(tuple(getattr(scenario, key) for key in (
                "regional_dip", "thickness_ft", "disturbance_height_ft", "disturbance_width_ft", "disturbance_x_ft",
            )))
        if not all(signatures.values()) or signatures["development"] & signatures["evaluation"]:
            raise ValueError("Development and evaluation geological configurations must be present and disjoint")
        return self


def load_manifest(path: str | Path | None = None) -> CalibrationManifest:
    return CalibrationManifest.model_validate_json(Path(path or DEFAULT_MANIFEST).read_text(encoding="utf-8"))


def _engine():
    from app.uncertainty.ensemble import forecast_ensemble, initialize_ensemble, summarize_ensemble, update_ensemble
    from app.uncertainty.models import EnsembleSettings
    return EnsembleSettings, initialize_ensemble, update_ensemble, summarize_ensemble, forecast_ensemble


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _current_interval(summary, index=0):
    return {key: float(summary["center"][key][index]) for key in ("q05", "q50", "q95")}


def _fixed_hold_path(scenario):
    station = landing_trajectory(scenario).iloc[-1].to_dict()
    points = [station]
    while station["md_ft"] < scenario.max_md_ft - 1e-9:
        station, _ = advance_station(station, "HOLD", min(scenario.step_ft, scenario.max_md_ft - station["md_ft"]), scenario.max_dls_deg_per_100ft)
        points.append(station)
    return points


def _offset_model(scenario):
    evidence = offset_evidence(scenario)
    markers = evidence["markers"]
    x = np.array([row["x_ft"] for row in markers])
    controls = []
    for boundary in ("top_tvd_ft", "base_tvd_ft"):
        slope, intercept = np.polyfit(x, [row[boundary] for row in markers], 1)
        controls.append([ControlPoint(md_ft=float(at), x_ft=float(at), tvd_ft=float(slope * at + intercept)) for at in (x[0], x[-1])])
    return controls[0], controls[1], evidence


def run_trial(case: StudyCase, seed: int, manifest: CalibrationManifest) -> dict:
    Settings, initialize, update, summarize, forecast = _engine()
    settings = Settings.model_validate(manifest.settings)
    scenario = Scenario(**case.geology, seed=seed)
    path = _fixed_hold_path(scenario)
    top, base, evidence = _offset_model(scenario)
    state = initialize(top, base, path[0]["x_ft"], settings=settings, seed=seed + manifest.ensemble_seed_offset)
    initial_state = state
    events = []
    field_end = float(path[-1]["x_ft"])
    for step, station in enumerate(path):
        measurement = sample_instrument(station, scenario, case.sensor, seed, step)
        kwargs = {"x_ft": station["x_ft"], "tvd_ft": station["tvd_ft"], "observation_md_ft": station["md_ft"], "step_index": step}
        # Both calls start from oldstate, using the same process/resampling draws.
        # The missing-measurement branch is a prior query, never a consumed state.
        prior = update(state, gr_api=None, **kwargs)
        prior_interval = _current_interval(summarize(prior))
        state = update(state, gr_api=measurement["GR"], **kwargs)
        posterior_interval = _current_interval(summarize(state))
        valid, excluded = [], []
        for horizon in manifest.forecast_horizons_ft:
            target = float(station["x_ft"] + horizon)
            if target > field_end + 1e-8:
                excluded.append({"horizon_ft": horizon, "reason": "outside_evaluated_x_domain"})
            else:
                valid.append((horizon, min(target, field_end)))
        predictions = forecast(state, [target for _, target in valid], seed_key=step) if valid else None
        future = [{"horizon_ft": horizon, "target_x_ft": target, "interval": _current_interval(predictions, index)} for index, (horizon, target) in enumerate(valid)]
        events.append({
            "step_index": step, "md_ft": station["md_ft"], "x_ft": station["x_ft"], "tvd_ft": station["tvd_ft"],
            "measurement": measurement, "prior_current": prior_interval, "posterior_current": posterior_interval,
            "forecasts": future, "forecast_exclusions": excluded, "paired_forecast_origin": len(valid) == len(manifest.forecast_horizons_ft),
            "prior_state_sha256": _digest(prior), "posterior_state_sha256": _digest(state),
            "forecast_sha256": _digest(predictions) if predictions is not None else None,
            "posterior_ess": float(state["ess"]), "diagnostics": state["last_update"],
        })
    # The withheld center is consulted only after all 101 observations are processed.
    points = score_predictions(events, scenario)
    metrics = {phase: _point_metrics([row for row in points if row["phase"] == phase]) for phase in PHASES}
    paired = {phase: _point_metrics([row for row in points if row["phase"] == phase and row["paired_forecast_origin"]]) for phase in ("forecast_250", "forecast_500")}
    collapsed = [event["posterior_ess"] < max(2.0, 0.02 * len(state["weights"])) for event in events]
    reasons = {}
    for event in events:
        diagnostic = event["diagnostics"]
        if not diagnostic.get("measurement_used"):
            reason = diagnostic.get("skip_reason") or "unavailable"
            reasons[reason] = reasons.get(reason, 0) + 1
    diagnostics = {
        "event_count": len(events), "mean_ess": float(np.mean([event["posterior_ess"] for event in events])),
        "minimum_ess": min(event["posterior_ess"] for event in events),
        "predictive_conflict_count": sum(bool(event["diagnostics"].get("predictive_conflict")) for event in events),
        "missing_measurement_count": sum(bool(event["measurement"]["missing"]) for event in events),
        "saturated_measurement_count": sum(bool(event["measurement"]["saturated"]) for event in events),
        "filter_saturation_low_count": sum(event["diagnostics"].get("saturation_status") == "low" for event in events),
        "filter_saturation_high_count": sum(event["diagnostics"].get("saturation_status") == "high" for event in events),
        "measurement_used_count": sum(bool(event["diagnostics"].get("measurement_used")) for event in events),
        "dropped_measurement_count": sum(reasons.values()), "skip_reasons": reasons,
        "resampling_count": sum(bool(event["diagnostics"].get("resampled")) for event in events),
        "collapse_step_count": sum(collapsed),
        "collapse_episode_count": sum(value and (index == 0 or not collapsed[index - 1]) for index, value in enumerate(collapsed)),
        "forecast_exclusion_count": sum(len(event["forecast_exclusions"]) for event in events),
    }
    return {
        "case_id": case.case_id, "split": case.split, "seed": seed,
        "ensemble_seed": seed + manifest.ensemble_seed_offset, "initial_state": initial_state,
        "offset_evidence": evidence, "evaluated_x_domain": [float(path[0]["x_ft"]), field_end],
        "events": events, "metrics": metrics, "paired_forecasts": paired, "diagnostics": diagnostics,
        "point_metrics": points,
    }


def score_predictions(events, scenario):
    rows = []
    for event in events:
        predictions = [(phase, event["x_ft"], event[phase]) for phase in ("prior_current", "posterior_current")]
        predictions.extend((f"forecast_{int(item['horizon_ft'])}", item["target_x_ft"], item["interval"]) for item in event["forecasts"])
        for phase, target, interval in predictions:
            top, base = formation_top_base(target, scenario)
            center = float((top + base) / 2)
            rows.append({
                "step_index": event["step_index"], "phase": phase, "origin_x_ft": event["x_ft"], "target_x_ft": target,
                "q05": interval["q05"], "q50": interval["q50"], "q95": interval["q95"], "true_center_tvd_ft": center,
                "covered": interval["q05"] <= center <= interval["q95"],
                "width_ft": interval["q95"] - interval["q05"], "absolute_center_error_ft": abs(interval["q50"] - center),
                "paired_forecast_origin": event["paired_forecast_origin"],
            })
    return rows


def _point_metrics(rows):
    if not rows:
        return {"point_count": 0, "covered_count": 0, "coverage_pct": None, "mean_width_ft": None, "mean_abs_center_error_ft": None}
    return {
        "point_count": len(rows), "covered_count": sum(bool(row["covered"]) for row in rows),
        "coverage_pct": 100.0 * float(np.mean([row["covered"] for row in rows])),
        "mean_width_ft": float(np.mean([row["width_ft"] for row in rows])),
        "mean_abs_center_error_ft": float(np.mean([row["absolute_center_error_ft"] for row in rows])),
    }


def _aggregate_metrics(metrics):
    valid = [row for row in metrics if row["point_count"]]
    return {
        "mean_coverage_pct": float(np.mean([row["coverage_pct"] for row in valid])) if valid else None,
        "min_coverage_pct": min(row["coverage_pct"] for row in valid) if valid else None,
        "max_coverage_pct": max(row["coverage_pct"] for row in valid) if valid else None,
        "mean_width_ft": float(np.mean([row["mean_width_ft"] for row in valid])) if valid else None,
        "mean_abs_center_error_ft": float(np.mean([row["mean_abs_center_error_ft"] for row in valid])) if valid else None,
        "total_point_count": sum(row["point_count"] for row in metrics),
        "trial_count": len(metrics),
    }


def _aggregate_diagnostics(trials):
    fields = [key for key, value in trials[0]["diagnostics"].items() if isinstance(value, (int, float))]
    return {f"mean_{key}": float(np.mean([trial["diagnostics"][key] for trial in trials])) for key in fields}


def summarize_trials(manifest, trials):
    expected = {(case.case_id, seed) for case in manifest.cases for seed in (manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds)}
    keys = [(trial["case_id"], trial["seed"]) for trial in trials]
    if len(set(keys)) != len(keys) or set(keys) != expected:
        raise ValueError("Study requires one completed trial for every declared case and noise seed")
    cases = []
    for case in manifest.cases:
        selected = [trial for trial in trials if trial["case_id"] == case.case_id]
        cases.append({
            "case_id": case.case_id, "label": case.label, "split": case.split, "description": case.description,
            "geology": case.geology, "sensor": case.sensor.model_dump(), "seed_count": len(selected),
            "phases": {phase: _aggregate_metrics([trial["metrics"][phase] for trial in selected]) for phase in PHASES},
            "paired_forecasts": {phase: _aggregate_metrics([trial["paired_forecasts"][phase] for trial in selected]) for phase in ("forecast_250", "forecast_500")},
            "diagnostics": _aggregate_diagnostics(selected),
        })
    splits = {}
    for split in ("development", "evaluation"):
        selected = [case for case in cases if case["split"] == split]
        phases = {}
        for phase in PHASES:
            phases[phase] = {
                "mean_coverage_pct": float(np.mean([case["phases"][phase]["mean_coverage_pct"] for case in selected])),
                "min_coverage_pct": min(case["phases"][phase]["min_coverage_pct"] for case in selected),
                "max_coverage_pct": max(case["phases"][phase]["max_coverage_pct"] for case in selected),
                "mean_width_ft": float(np.mean([case["phases"][phase]["mean_width_ft"] for case in selected])),
                "mean_abs_center_error_ft": float(np.mean([case["phases"][phase]["mean_abs_center_error_ft"] for case in selected])),
                "total_point_count": sum(case["phases"][phase]["total_point_count"] for case in selected),
            }
        splits[split] = {"phases": phases, "diagnostics": {key: float(np.mean([case["diagnostics"][key] for case in selected])) for key in selected[0]["diagnostics"]}}
    worst = min((trial for trial in trials if trial["split"] == "evaluation"), key=lambda trial: trial["metrics"]["posterior_current"]["coverage_pct"])
    return {
        "schema_version": 1, "study_id": manifest.study_id, "engine_version": manifest.engine_version,
        "nominal_level": manifest.nominal_level, "phases": PHASES, "settings": manifest.settings,
        "counts": {"development_cases": sum(case.split == "development" for case in manifest.cases), "evaluation_cases": sum(case.split == "evaluation" for case in manifest.cases), "trial_count": len(trials)},
        "case_results": cases, **splits,
        "worst_trial": {"case_id": worst["case_id"], "seed": worst["seed"], "phase": "posterior_current", **worst["metrics"]["posterior_current"], "diagnostics": worst["diagnostics"]},
        "interpretation_notes": NOTES,
    }


def replay_trial_history(trial):
    """Verify every state/forecast digest using only saved acquired observations."""
    _, _, update, _, forecast = _engine()
    state = trial["initial_state"]
    for event in trial["events"]:
        kwargs = {"x_ft": event["x_ft"], "tvd_ft": event["tvd_ft"], "observation_md_ft": event["md_ft"], "step_index": event["step_index"]}
        prior = update(state, gr_api=None, **kwargs)
        if _digest(prior) != event["prior_state_sha256"]:
            raise ValueError("Replayed prior state differs from frozen event")
        state = update(state, gr_api=event["measurement"]["GR"], **kwargs)
        if _digest(state) != event["posterior_state_sha256"]:
            raise ValueError("Replayed posterior state differs from frozen event")
        targets = [item["target_x_ft"] for item in event["forecasts"]]
        predicted = forecast(state, targets, seed_key=event["step_index"]) if targets else None
        if (_digest(predicted) if predicted is not None else None) != event["forecast_sha256"]:
            raise ValueError("Replayed forecast differs from frozen event")
    return len(trial["events"])


def render_figures(summary, trials, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cases = [case for case in summary["case_results"] if case["split"] == "evaluation"]
    colors = {"prior_current": "#6b8190", "posterior_current": "#0f766e", "forecast_250": "#b45309", "forecast_500": "#7c3f7a"}
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), layout="constrained", sharex=True)
    x = np.arange(len(cases))
    for index, (phase, label) in enumerate(PHASES.items()):
        position = x + (index - 1.5) * 0.19
        axes[0].bar(position, [case["phases"][phase]["mean_coverage_pct"] for case in cases], width=0.18, label=label, color=colors[phase])
        axes[1].bar(position, [case["phases"][phase]["mean_width_ft"] for case in cases], width=0.18, color=colors[phase])
    axes[0].axhline(90, color="#273a44", linestyle="--", linewidth=1, label="Nominal 90%")
    axes[0].set_ylim(0, 103)
    axes[0].set_ylabel("Empirical center coverage (%)")
    fig.suptitle("Uncertainty quality on held-out fixed-HOLD cases", x=0.01, ha="left", fontweight="bold")
    axes[0].legend(ncol=3, fontsize=9, loc="lower left", bbox_to_anchor=(0, 1.02), borderaxespad=0, frameon=False)
    axes[1].set_ylabel("Mean center interval width (ft)")
    axes[1].set_xticks(x, [case["label"] for case in cases], rotation=18, ha="right")
    axes[1].set_xlabel("Handpicked geology / sensor cases · means across declared trial seeds")
    for ax in axes:
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(out / "uncertainty_coverage.png", dpi=170)
    plt.close(fig)

    worst = summary["worst_trial"]
    trial = next(trial for trial in trials if trial["case_id"] == worst["case_id"] and trial["seed"] == worst["seed"])
    points = [row for row in trial["point_metrics"] if row["phase"] == "posterior_current"]
    current_x = [row["target_x_ft"] for row in points]
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained", sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    axes[0].fill_between(current_x, [row["q05"] for row in points], [row["q95"] for row in points], alpha=0.25, color="#0f766e", label="Posterior 90% center interval")
    axes[0].plot(current_x, [row["q50"] for row in points], color="#0f766e", label="Posterior median")
    axes[0].plot(current_x, [row["true_center_tvd_ft"] for row in points], color="#263d4a", linestyle="--", label="Withheld true center")
    axes[0].invert_yaxis()
    axes[0].set_ylabel("Center TVD (ft; positive down)")
    axes[0].set_title(f"Lowest posterior coverage · {worst['case_id']} · seed {worst['seed']} · {worst['coverage_pct']:.1f}%", loc="left", fontweight="bold")
    axes[1].plot(current_x, [event["posterior_ess"] for event in trial["events"]], color="#6b8190", label="Posterior ESS")
    conflicts = [event for event in trial["events"] if event["diagnostics"].get("predictive_conflict")]
    axes[1].scatter([event["x_ft"] for event in conflicts], [event["posterior_ess"] for event in conflicts], color="#b45309", marker="x", label="Predictive conflict", zorder=4)
    axes[1].set_ylabel("Effective sample size")
    axes[1].set_xlabel("Acquired along-track x (ft)")
    for ax in axes:
        ax.legend(frameon=False, fontsize=9)
        ax.grid(alpha=0.15)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(out / "uncertainty_failure.png", dpi=170)
    plt.close(fig)


def run_study(out: str | Path, manifest_path: str | Path | None = None):
    manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
    manifest_bytes = manifest_path.read_bytes()
    manifest = CalibrationManifest.model_validate_json(manifest_bytes)
    Settings, *_ = _engine()
    Settings.model_validate(manifest.settings)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose a new or empty uncertainty output directory; evidence is never replaced")
    out.mkdir(parents=True, exist_ok=True)
    frozen = freeze_sources(out, manifest_bytes)
    protocol_bytes = (manifest_path.parent / "PROTOCOL.md").read_bytes()
    (out / "PROTOCOL.md").write_bytes(protocol_bytes)
    frozen["protocol_sha256"] = hashlib.sha256(protocol_bytes).hexdigest()
    _write_json(out / "freeze.json", frozen)
    trials = []
    try:
        with (out / "histories.jsonl.gz").open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as history:
            for case in manifest.cases:
                for seed in (manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds):
                    trial = run_trial(case, seed, manifest)
                    trials.append(trial)
                    history.write((json.dumps(trial, sort_keys=True, allow_nan=False) + "\n").encode())
        summary = summarize_trials(manifest, trials)
        summary.update({"manifest_sha256": frozen["manifest_sha256"], "source_fingerprint": frozen["source_fingerprint"]})
        _write_json(out / "summary.json", summary)
        metric_rows, point_rows, diagnostic_rows = [], [], []
        for trial in trials:
            identity = {key: trial[key] for key in ("case_id", "split", "seed")}
            metric_rows.extend(identity | {"phase": phase, "origin_set": "all_valid"} | metrics for phase, metrics in trial["metrics"].items())
            metric_rows.extend(identity | {"phase": phase, "origin_set": "paired_forecast_origins"} | metrics for phase, metrics in trial["paired_forecasts"].items())
            point_rows.extend(identity | row for row in trial["point_metrics"])
            diagnostic_rows.append(identity | {key: value for key, value in trial["diagnostics"].items() if key != "skip_reasons"} | {"skip_reasons": json.dumps(trial["diagnostics"]["skip_reasons"], sort_keys=True)})
        pd.DataFrame(metric_rows).to_csv(out / "trial_metrics.csv", index=False)
        pd.DataFrame(diagnostic_rows).to_csv(out / "diagnostics.csv", index=False)
        with (out / "point_metrics.csv.gz").open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as points:
            points.write(pd.DataFrame(point_rows).to_csv(index=False, lineterminator="\n").encode())
        render_figures(summary, trials, out)
        artifacts = {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.rglob("*")) if path.is_file()}
        _write_json(out / "artifacts.json", {"status": "complete", "sha256": artifacts})
        return summary
    except Exception as exc:
        _write_json(out / "failure.json", {"status": "incomplete", "completed_trial_count": len(trials), "error_type": type(exc).__name__, "message": str(exc)})
        raise


def load_uncertainty_summary(path: str | Path | None = None):
    """Verify saved uncertainty evidence and source archive; never execute a trial."""
    path = Path(path or DEFAULT_RESULTS / "summary.json")
    if path.name != "summary.json":
        raise ValueError("Select the uncertainty study summary.json artifact")
    artifacts = json.loads((path.parent / "artifacts.json").read_text(encoding="utf-8"))
    index = artifacts.get("sha256", {})
    required = {"summary.json", "manifest.json", "PROTOCOL.md", "freeze.json", "frozen_source.zip", "histories.jsonl.gz", "trial_metrics.csv", "diagnostics.csv", "point_metrics.csv.gz", "uncertainty_coverage.png", "uncertainty_failure.png"}
    if artifacts.get("status") != "complete" or not required.issubset(index):
        raise ValueError("Uncertainty study evidence is incomplete")
    expanded = path.parent / "frozen_source"
    for name, expected in index.items():
        _check_relative_path(name)
        if name.startswith("frozen_source/") and not expanded.exists():
            continue
        if hashlib.sha256((path.parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Uncertainty artifact changed: {name}")
    summary = json.loads(path.read_text(encoding="utf-8"))
    freeze = json.loads((path.parent / "freeze.json").read_text(encoding="utf-8"))
    manifest_bytes = (path.parent / "manifest.json").read_bytes()
    manifest = CalibrationManifest.model_validate_json(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if summary["manifest_sha256"] != manifest_hash or freeze["manifest_sha256"] != manifest_hash:
        raise ValueError("Uncertainty manifest identity does not match saved records")
    if freeze["protocol_sha256"] != hashlib.sha256((path.parent / "PROTOCOL.md").read_bytes()).hexdigest():
        raise ValueError("Uncertainty protocol identity does not match frozen record")
    if summary["study_id"] != manifest.study_id or summary["engine_version"] != manifest.engine_version or summary["settings"] != manifest.settings:
        raise ValueError("Uncertainty summary does not match executed design")
    sources = freeze["source_sha256"]
    if not sources or summary["source_fingerprint"] != _digest(sources) or freeze["source_fingerprint"] != _digest(sources):
        raise ValueError("Uncertainty source fingerprint does not match saved records")
    for name, expected in sources.items():
        _check_relative_path(name)
        if index.get(f"frozen_source/{name}") != expected:
            raise ValueError("Uncertainty source and artifact indexes differ")
    expected_paths = {f"frozen_source/{name}" for name in sources}
    if {name for name in index if name.startswith("frozen_source/")} != expected_paths:
        raise ValueError("Unexpected uncertainty source index member")
    with zipfile.ZipFile(path.parent / "frozen_source.zip") as archive:
        names = archive.namelist()
        for name in names:
            _check_relative_path(name)
        if len(names) != len(set(names)) or set(names) != set(sources):
            raise ValueError("Uncertainty source archive differs from source index")
        for name, expected in sources.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Uncertainty archived source changed: {name}")
    if expanded.exists() and {item.relative_to(expanded).as_posix() for item in expanded.rglob("*") if item.is_file()} != set(sources):
        raise ValueError("Expanded uncertainty sources differ from source index")
    return summary
