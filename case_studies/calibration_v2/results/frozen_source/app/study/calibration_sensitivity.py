"""Frozen paired v1/v2 calibration-sensitivity experiment, distinct from v1 evidence."""

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

from app.geo.formation import Scenario
from app.study.robustness import StrictModel, StudyCase, _check_relative_path, freeze_sources, sample_instrument
from app.study.uncertainty_calibration import (
    PHASES,
    _aggregate_metrics,
    _digest,
    _fixed_hold_path,
    _offset_model,
    _point_metrics,
    _write_json,
    load_uncertainty_summary,
    score_predictions,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "case_studies/calibration_v2/manifest.json"
if not DEFAULT_MANIFEST.is_file():
    DEFAULT_MANIFEST = Path(sys.prefix) / "share/geosteering/case_studies/calibration_v2/manifest.json"
DEFAULT_RESULTS = DEFAULT_MANIFEST.parent / "results"
INTERVAL_TYPES = {
    "v1_nominal": "V1 nominal 90%",
    "v2_pooled": "V2 fixed-mixture nominal 90%",
    "v2_envelope": "Calibration sensitivity envelope",
}
NOTES = [
    "This is a paired uncertainty-quality study on fixed HOLD paths, not a new steering-policy ranking.",
    "The ±16 API support and five equal-weight hypotheses were empirically selected after observing the historical v1 +8 API failure.",
    "Fixed calibration weights are sensitivity assumptions, not data-identified posterior calibration probabilities.",
    "The sensitivity envelope is a hull of conditional intervals and has no nominal coverage guarantee.",
    "Each pair shares its observations, offset prior, path and namespaced particle random streams. Twenty pairs are not forty independent experiments.",
    "New evaluation geology and seeds are disjoint from both previous studies. The historical +8 API diagnostic is reused and is not fresh validation.",
    "Coverage and width are averaged within trials, then within cases, with equal case weights. Spatial points are correlated; no population confidence interval is claimed.",
    "Wider intervals trade precision for coverage. The +28 API outside-support case and worst fresh failure remain in the reported results.",
    "Current prior/posterior locations are paired. Forecast targets outside the evaluated domain are excluded with explicit denominators.",
]


class SensitivityCase(StudyCase):
    evidence_status: Literal["diagnostic_reused", "development_control", "fresh_evaluation"]
    historical_reference: str | None = None


class SensitivityManifest(StrictModel):
    schema_version: Literal[1]
    study_id: str
    nominal_level: Literal[0.9]
    forecast_horizons_ft: list[float]
    ensemble_seed_offset: int = Field(ge=0)
    development_seeds: list[int] = Field(min_length=1)
    evaluation_seeds: list[int] = Field(min_length=1)
    baseline_settings: dict
    sensitivity_settings: dict
    design_note: str
    historical_evidence: dict
    cases: list[SensitivityCase] = Field(min_length=2)

    @model_validator(mode="after")
    def paired_design(self):
        if self.forecast_horizons_ft != [250.0, 500.0]:
            raise ValueError("The fixed forecast horizons are 250 and 500 ft")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique")
        for seeds in (self.development_seeds, self.evaluation_seeds):
            if len(set(seeds)) != len(seeds) or any(type(seed) is not int or seed < 0 for seed in seeds):
                raise ValueError("Seeds must be unique nonnegative integers")
        if set(self.development_seeds) & set(self.evaluation_seeds):
            raise ValueError("Development and evaluation seeds must be disjoint")
        if self.sensitivity_settings.get("calibration_biases_api") != [-16.0, -8.0, 0.0, 8.0, 16.0]:
            raise ValueError("Calibration support is fixed before evaluation")
        conditional = {key: value for key, value in self.sensitivity_settings.items() if key not in {"version", "calibration_biases_api"}}
        baseline = {key: value for key, value in self.baseline_settings.items() if key != "version"}
        if conditional != baseline:
            raise ValueError("Paired baseline and conditional settings must match")
        signatures = {"development": set(), "evaluation": set()}
        for case in self.cases:
            if case.sensor.delay_steps:
                raise ValueError("Delayed observations are excluded from this fixed study")
            if case.split == "evaluation" and case.evidence_status != "fresh_evaluation":
                raise ValueError("Evaluation cases must be labeled fresh")
            if case.split == "development" and case.evidence_status == "fresh_evaluation":
                raise ValueError("Development cases cannot be labeled fresh evaluation")
            if case.evidence_status == "diagnostic_reused" and not case.historical_reference:
                raise ValueError("Reused diagnostics require an explicit historical reference")
            signatures[case.split].add(_geology_signature(case.geology))
        if not all(signatures.values()) or signatures["development"] & signatures["evaluation"]:
            raise ValueError("Development and evaluation geological configurations must be disjoint")
        return self


def _geology_signature(geology):
    scenario = Scenario(**geology)
    return tuple(getattr(scenario, key) for key in ("regional_dip", "thickness_ft", "disturbance_height_ft", "disturbance_width_ft", "disturbance_x_ft"))


def load_manifest(path=None):
    return SensitivityManifest.model_validate_json(Path(path or DEFAULT_MANIFEST).read_text(encoding="utf-8"))


def _previous_root():
    return DEFAULT_MANIFEST.parent.parent


def validate_freshness(manifest):
    """Compare only protocol inputs; never inspect new evaluation outcomes."""
    previous_signatures, previous_seeds, records = set(), set(), []
    for study in ("robustness_v1", "uncertainty_v1"):
        path = _previous_root() / study / "results/manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        previous_signatures.update(_geology_signature(case["geology"]) for case in data["cases"])
        previous_seeds.update(data["development_seeds"] + data["evaluation_seeds"])
        records.append({"study": study, "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if {_geology_signature(case.geology) for case in manifest.cases if case.split == "evaluation"} & previous_signatures:
        raise ValueError("Fresh evaluation geology overlaps an already observed protocol")
    if set(manifest.evaluation_seeds) & previous_seeds:
        raise ValueError("Fresh evaluation seeds overlap an already observed protocol")
    return {"previous_protocols": records, "evaluation_geology_disjoint": True, "evaluation_seeds_disjoint": True}


def _engine():
    from app.uncertainty.ensemble import forecast_ensemble, initialize_ensemble, summarize_ensemble, update_ensemble
    from app.uncertainty.models import CalibrationSettings, EnsembleSettings
    return EnsembleSettings, CalibrationSettings, initialize_ensemble, update_ensemble, summarize_ensemble, forecast_ensemble


def _interval(summary, kind, index=0):
    source = summary["calibration_envelope"] if kind == "v2_envelope" else summary
    return {key: float(source["center"][key][index]) for key in ("q05", "q50", "q95")}


def _zero_branch(state):
    return next(component["ensemble"] for component in state["components"] if component["bias_api"] == 0)


def _difference(value, baseline):
    return None if value is None or baseline is None else value - baseline


def _health(state):
    components = state.get("components")
    conditional = [component["ensemble"] for component in components] if components else [state]
    return {
        "minimum_conditional_ess": min(item["ess"] for item in conditional),
        "conditional_ess": [item["ess"] for item in conditional],
        "predictive_conflict_any": any(item["last_update"].get("predictive_conflict", False) for item in conditional),
        "predictive_conflict_all": all(item["last_update"].get("predictive_conflict", False) for item in conditional),
        "measurement_used": all(item["last_update"].get("measurement_used", False) for item in conditional),
        "fixed_component_weights": [item["weight"] for item in components] if components else [1.0],
    }


def run_pair(case, seed, manifest):
    V1, V2, initialize, update, summarize, forecast = _engine()
    settings = {"v1": V1.model_validate(manifest.baseline_settings), "v2": V2.model_validate(manifest.sensitivity_settings)}
    scenario = Scenario(**case.geology, seed=seed)
    path = _fixed_hold_path(scenario)
    top, base, evidence = _offset_model(scenario)
    ensemble_seed = seed + manifest.ensemble_seed_offset
    states = {model: initialize(top, base, path[0]["x_ft"], settings=value, seed=ensemble_seed) for model, value in settings.items()}
    initial_states = states.copy()
    if states["v1"] != _zero_branch(states["v2"]):
        raise ValueError("Paired zero-bias initial states differ")
    endpoint = float(path[-1]["x_ft"])
    events = []
    for step, station in enumerate(path):
        observation = sample_instrument(station, scenario, case.sensor, seed, step)
        kwargs = {"x_ft": station["x_ft"], "tvd_ft": station["tvd_ft"], "observation_md_ft": station["md_ft"], "step_index": step}
        prior = {model: update(state, gr_api=None, **kwargs) for model, state in states.items()}
        states = {model: update(state, gr_api=observation["GR"], **kwargs) for model, state in states.items()}
        if states["v1"] != _zero_branch(states["v2"]) or prior["v1"] != _zero_branch(prior["v2"]):
            raise ValueError("Paired zero-bias conditional state diverged from v1")
        if any(component["weight"] != 0.2 for component in states["v2"]["components"]):
            raise ValueError("Fixed sensitivity weights changed during evaluation")
        prior_summary = {model: summarize(state) for model, state in prior.items()}
        posterior_summary = {model: summarize(state) for model, state in states.items()}
        valid, excluded = [], []
        for horizon in manifest.forecast_horizons_ft:
            target = station["x_ft"] + horizon
            if target > endpoint + 1e-8:
                excluded.append({"horizon_ft": horizon, "reason": "outside_evaluated_x_domain"})
            else:
                valid.append((horizon, min(target, endpoint)))
        future = {model: forecast(state, [target for _, target in valid], seed_key=step) if valid else None for model, state in states.items()}
        variants = {}
        for kind in INTERVAL_TYPES:
            model = "v1" if kind == "v1_nominal" else "v2"
            variants[kind] = {
                "prior_current": _interval(prior_summary[model], kind),
                "posterior_current": _interval(posterior_summary[model], kind),
                "forecasts": [{"horizon_ft": horizon, "target_x_ft": target, "interval": _interval(future[model], kind, index)} for index, (horizon, target) in enumerate(valid)],
            }
        events.append({
            "step_index": step, "md_ft": station["md_ft"], "x_ft": station["x_ft"], "tvd_ft": station["tvd_ft"],
            "observation": observation, "intervals": variants, "forecast_exclusions": excluded,
            "paired_forecast_origin": len(valid) == 2,
            "prior_state_sha256": {model: _digest(state) for model, state in prior.items()},
            "posterior_state_sha256": {model: _digest(state) for model, state in states.items()},
            "forecast_sha256": {model: _digest(value) if value is not None else None for model, value in future.items()},
            "zero_bias_matches_v1": True, "health": {model: _health(state) for model, state in states.items()},
        })
    # Neither model receives truth. Score the shared points after both have finished.
    points, metrics, paired_origins = [], {}, {}
    for kind in INTERVAL_TYPES:
        projected = [{"step_index": event["step_index"], "x_ft": event["x_ft"], "paired_forecast_origin": event["paired_forecast_origin"], **event["intervals"][kind]} for event in events]
        scored = [row | {"interval_type": kind} for row in score_predictions(projected, scenario)]
        points.extend(scored)
        metrics[kind] = {phase: _point_metrics([row for row in scored if row["phase"] == phase]) for phase in PHASES}
        paired_origins[kind] = {phase: _point_metrics([row for row in scored if row["phase"] == phase and row["paired_forecast_origin"]]) for phase in ("forecast_250", "forecast_500")}
    deltas = {kind: {phase: {
        "coverage_delta_pp": _difference(metrics[kind][phase]["coverage_pct"], metrics["v1_nominal"][phase]["coverage_pct"]),
        "width_delta_ft": _difference(metrics[kind][phase]["mean_width_ft"], metrics["v1_nominal"][phase]["mean_width_ft"]),
    } for phase in PHASES} for kind in ("v2_pooled", "v2_envelope")}
    diagnostics = {model: {
        "mean_minimum_conditional_ess": float(np.mean([event["health"][model]["minimum_conditional_ess"] for event in events])),
        "minimum_conditional_ess": min(event["health"][model]["minimum_conditional_ess"] for event in events),
        "predictive_conflict_any_count": sum(event["health"][model]["predictive_conflict_any"] for event in events),
        "predictive_conflict_all_count": sum(event["health"][model]["predictive_conflict_all"] for event in events),
        "measurement_used_count": sum(event["health"][model]["measurement_used"] for event in events),
        "missing_count": sum(event["observation"]["missing"] for event in events),
        "saturated_count": sum(event["observation"]["saturated"] for event in events),
    } for model in states}
    return {
        "case_id": case.case_id, "split": case.split, "evidence_status": case.evidence_status, "seed": seed,
        "ensemble_seed": ensemble_seed, "initial_states": initial_states, "offset_evidence": evidence,
        "evaluated_x_domain": [path[0]["x_ft"], endpoint], "events": events,
        "metrics": metrics, "paired_forecasts": paired_origins, "paired_deltas": deltas,
        "diagnostics": diagnostics, "point_metrics": points,
    }


def replay_pair(pair):
    _, _, _, update, _, forecast = _engine()
    states = pair["initial_states"]
    for event in pair["events"]:
        kwargs = {"x_ft": event["x_ft"], "tvd_ft": event["tvd_ft"], "observation_md_ft": event["md_ft"], "step_index": event["step_index"]}
        prior = {model: update(state, gr_api=None, **kwargs) for model, state in states.items()}
        if any(_digest(state) != event["prior_state_sha256"][model] for model, state in prior.items()):
            raise ValueError("Replayed prior state differs from paired evidence")
        states = {model: update(state, gr_api=event["observation"]["GR"], **kwargs) for model, state in states.items()}
        if any(_digest(state) != event["posterior_state_sha256"][model] for model, state in states.items()):
            raise ValueError("Replayed posterior state differs from paired evidence")
        if states["v1"] != _zero_branch(states["v2"]):
            raise ValueError("Replayed paired zero branch differs from v1")
        targets = [item["target_x_ft"] for item in event["intervals"]["v1_nominal"]["forecasts"]]
        future = {model: forecast(state, targets, seed_key=event["step_index"]) if targets else None for model, state in states.items()}
        if any((_digest(value) if value is not None else None) != event["forecast_sha256"][model] for model, value in future.items()):
            raise ValueError("Replayed forecast differs from paired evidence")
    return len(pair["events"])


def _paired_summary(rows):
    valid = [row for row in rows if row["coverage_delta_pp"] is not None and row["width_delta_ft"] is not None]
    return {
        "mean_coverage_delta_pp": float(np.mean([row["coverage_delta_pp"] for row in valid])) if valid else None,
        "min_coverage_delta_pp": min(row["coverage_delta_pp"] for row in valid) if valid else None,
        "max_coverage_delta_pp": max(row["coverage_delta_pp"] for row in valid) if valid else None,
        "mean_width_delta_ft": float(np.mean([row["width_delta_ft"] for row in valid])) if valid else None,
        "paired_trial_count": len(rows),
        "valid_paired_trial_count": len(valid),
    }


def summarize_pairs(manifest, pairs):
    expected = {(case.case_id, seed) for case in manifest.cases for seed in (manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds)}
    keys = [(pair["case_id"], pair["seed"]) for pair in pairs]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("One completed pair is required for each declared case and seed")
    cases = []
    for case in manifest.cases:
        selected = [pair for pair in pairs if pair["case_id"] == case.case_id]
        cases.append({
            "case_id": case.case_id, "label": case.label, "split": case.split, "evidence_status": case.evidence_status,
            "description": case.description, "historical_reference": case.historical_reference,
            "geology": case.geology, "sensor": case.sensor.model_dump(), "seed_count": len(selected),
            "intervals": {kind: {"phases": {phase: _aggregate_metrics([pair["metrics"][kind][phase] for pair in selected]) for phase in PHASES}} for kind in INTERVAL_TYPES},
            "paired": {kind: {phase: _paired_summary([pair["paired_deltas"][kind][phase] for pair in selected]) for phase in PHASES} for kind in ("v2_pooled", "v2_envelope")},
        })
    splits = {}
    for split in ("development", "evaluation"):
        selected = [case for case in cases if case["split"] == split]
        splits[split] = {
            "intervals": {kind: {"phases": {phase: {
                "mean_coverage_pct": float(np.mean([case["intervals"][kind]["phases"][phase]["mean_coverage_pct"] for case in selected])),
                "min_coverage_pct": min(case["intervals"][kind]["phases"][phase]["min_coverage_pct"] for case in selected),
                "max_coverage_pct": max(case["intervals"][kind]["phases"][phase]["max_coverage_pct"] for case in selected),
                "mean_width_ft": float(np.mean([case["intervals"][kind]["phases"][phase]["mean_width_ft"] for case in selected])),
                "mean_abs_center_error_ft": float(np.mean([case["intervals"][kind]["phases"][phase]["mean_abs_center_error_ft"] for case in selected])),
                "total_point_count": sum(case["intervals"][kind]["phases"][phase]["total_point_count"] for case in selected),
            } for phase in PHASES}} for kind in INTERVAL_TYPES},
            "paired": {kind: {phase: {
                "mean_coverage_delta_pp": float(np.mean([case["paired"][kind][phase]["mean_coverage_delta_pp"] for case in selected])),
                "mean_width_delta_ft": float(np.mean([case["paired"][kind][phase]["mean_width_delta_ft"] for case in selected])),
                "paired_trial_count": sum(case["paired"][kind][phase]["paired_trial_count"] for case in selected),
            } for phase in PHASES} for kind in ("v2_pooled", "v2_envelope")},
        }
    worst = min((pair for pair in pairs if pair["split"] == "evaluation"), key=lambda pair: pair["metrics"]["v2_envelope"]["posterior_current"]["coverage_pct"])
    historical = next((pair for pair in pairs if pair["evidence_status"] == "diagnostic_reused"), None)
    def diagnostic(pair):
        return {"case_id": pair["case_id"], "seed": pair["seed"], "evidence_status": pair["evidence_status"], "intervals": pair["metrics"], "paired": pair["paired_deltas"], "diagnostics": pair["diagnostics"]} if pair else None
    return {
        "schema_version": 1, "study_id": manifest.study_id, "nominal_level": manifest.nominal_level,
        "interval_types": INTERVAL_TYPES, "phases": PHASES,
        "baseline_settings": manifest.baseline_settings, "sensitivity_settings": manifest.sensitivity_settings,
        "design_note": manifest.design_note,
        "counts": {"development_cases": sum(case.split == "development" for case in manifest.cases), "evaluation_cases": sum(case.split == "evaluation" for case in manifest.cases), "paired_trial_count": len(pairs), "model_run_count": 2 * len(pairs)},
        "case_results": cases, **splits, "historical_diagnostic": diagnostic(historical),
        "worst_fresh_trial": diagnostic(worst), "interpretation_notes": NOTES,
    }


def _historical_reference(manifest):
    root = _previous_root() / "uncertainty_v1/results"
    load_uncertainty_summary(root / "summary.json")
    expected = manifest.historical_evidence
    for name, key in (("manifest.json", "manifest_sha256"), ("summary.json", "summary_sha256")):
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected[key]:
            raise ValueError("Historical reference evidence identity changed")
    with gzip.open(root / "histories.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            trial = json.loads(line)
            if trial["case_id"] == expected["case_id"] and trial["seed"] == expected["seed"]:
                return {**expected, "evidence_status": "diagnostic_reused", "metrics": trial["metrics"], "ensemble_seed": trial["ensemble_seed"]}
    raise ValueError("Historical diagnostic trial was not found")


def render_figures(summary, pairs, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"v1_nominal": "#6b8190", "v2_pooled": "#0f766e", "v2_envelope": "#b45309"}
    cases = [case for case in summary["case_results"] if case["split"] == "evaluation"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), layout="constrained", sharex=True)
    x = np.arange(len(cases))
    for index, (kind, label) in enumerate(INTERVAL_TYPES.items()):
        position = x + (index - 1) * 0.24
        axes[0].bar(position, [case["intervals"][kind]["phases"]["posterior_current"]["mean_coverage_pct"] for case in cases], width=0.22, label=label, color=colors[kind])
        axes[1].bar(position, [case["intervals"][kind]["phases"]["posterior_current"]["mean_width_ft"] for case in cases], width=0.22, color=colors[kind])
    axes[0].axhline(90, linestyle="--", color="#283f4b", linewidth=1)
    axes[0].set_ylim(0, 104)
    axes[0].set_ylabel("Current posterior center coverage (%)")
    axes[1].set_ylabel("Mean current interval width (ft)")
    axes[1].set_xticks(x, [case["label"] for case in cases], rotation=18, ha="right")
    axes[1].set_xlabel("Fresh handpicked cases · paired trial means · envelope has no nominal coverage guarantee")
    fig.suptitle("Calibration sensitivity: coverage and precision together", x=0.01, ha="left", fontweight="bold")
    axes[0].legend(ncol=2, fontsize=9, loc="lower left", bbox_to_anchor=(0, 1.02), frameon=False, borderaxespad=0)
    for ax in axes:
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(out / "calibration_coverage.png", dpi=170)
    plt.close(fig)
    diagnostics = [(summary["historical_diagnostic"], "Reused historical diagnostic"), (summary["worst_fresh_trial"], "Lowest fresh envelope coverage")]
    diagnostics = [(value, label) for value, label in diagnostics if value is not None]
    fig, axes = plt.subplots(len(diagnostics), 1, figsize=(12, 4 * len(diagnostics)), layout="constrained", squeeze=False)
    for ax, (reference, title) in zip(axes[:, 0], diagnostics):
        pair = next(pair for pair in pairs if pair["case_id"] == reference["case_id"] and pair["seed"] == reference["seed"])
        for kind in ("v2_envelope", "v2_pooled", "v1_nominal"):
            rows = [row for row in pair["point_metrics"] if row["interval_type"] == kind and row["phase"] == "posterior_current"]
            coverage = pair["metrics"][kind]["posterior_current"]["coverage_pct"]
            ax.fill_between([row["target_x_ft"] for row in rows], [row["q05"] for row in rows], [row["q95"] for row in rows], alpha=0.20, color=colors[kind], label=f"{INTERVAL_TYPES[kind]} · {coverage:.1f}%")
        truth = [row for row in pair["point_metrics"] if row["interval_type"] == "v1_nominal" and row["phase"] == "posterior_current"]
        ax.plot([row["target_x_ft"] for row in truth], [row["true_center_tvd_ft"] for row in truth], color="#213a48", linestyle="--", label="Withheld true center")
        ax.invert_yaxis()
        ax.set_title(f"{title} · {reference['case_id']} · seed {reference['seed']}", loc="left", fontweight="bold")
        ax.set_ylabel("Center TVD (ft; positive down)")
        ax.set_xlabel("Acquired along-track x (ft)")
        ax.legend(fontsize=8, frameon=False, loc="best")
        ax.grid(alpha=0.12)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(out / "calibration_failure.png", dpi=170)
    plt.close(fig)


def run_study(out, manifest_path=None):
    manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
    manifest_bytes = manifest_path.read_bytes()
    manifest = SensitivityManifest.model_validate_json(manifest_bytes)
    V1, V2, *_ = _engine()
    V1.model_validate(manifest.baseline_settings)
    V2.model_validate(manifest.sensitivity_settings)
    freshness = validate_freshness(manifest)
    historical = _historical_reference(manifest)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose a new or empty calibration output directory; evidence is never replaced")
    out.mkdir(parents=True, exist_ok=True)
    frozen = freeze_sources(out, manifest_bytes)
    protocol = (manifest_path.parent / "PROTOCOL.md").read_bytes()
    (out / "PROTOCOL.md").write_bytes(protocol)
    frozen["protocol_sha256"] = hashlib.sha256(protocol).hexdigest()
    _write_json(out / "freeze.json", frozen)
    _write_json(out / "freshness_audit.json", freshness)
    _write_json(out / "historical_reference.json", historical)
    pairs = []
    try:
        with (out / "histories.jsonl.gz").open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as history:
            for case in manifest.cases:
                for seed in (manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds):
                    pair = run_pair(case, seed, manifest)
                    if pair["evidence_status"] == "diagnostic_reused" and pair["metrics"]["v1_nominal"] != historical["metrics"]:
                        raise ValueError("Reused diagnostic v1 metrics differ from original frozen evidence")
                    pairs.append(pair)
                    history.write((json.dumps(pair, sort_keys=True, allow_nan=False) + "\n").encode())
        summary = summarize_pairs(manifest, pairs)
        summary.update({"manifest_sha256": frozen["manifest_sha256"], "source_fingerprint": frozen["source_fingerprint"]})
        _write_json(out / "summary.json", summary)
        metrics, paired, points, diagnostics = [], [], [], []
        for pair in pairs:
            identity = {key: pair[key] for key in ("case_id", "split", "evidence_status", "seed")}
            metrics.extend(identity | {"interval_type": kind, "phase": phase, "origin_set": "all_valid"} | value for kind, phases in pair["metrics"].items() for phase, value in phases.items())
            metrics.extend(identity | {"interval_type": kind, "phase": phase, "origin_set": "paired_forecast_origins"} | value for kind, phases in pair["paired_forecasts"].items() for phase, value in phases.items())
            paired.extend(identity | {"interval_type": kind, "phase": phase} | value for kind, phases in pair["paired_deltas"].items() for phase, value in phases.items())
            points.extend(identity | row for row in pair["point_metrics"])
            diagnostics.extend(identity | {"model": model} | value for model, value in pair["diagnostics"].items())
        pd.DataFrame(metrics).to_csv(out / "trial_metrics.csv", index=False)
        pd.DataFrame(paired).to_csv(out / "paired_metrics.csv", index=False)
        pd.DataFrame(diagnostics).to_csv(out / "diagnostics.csv", index=False)
        with (out / "point_metrics.csv.gz").open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as points_file:
            points_file.write(pd.DataFrame(points).to_csv(index=False, lineterminator="\n").encode())
        render_figures(summary, pairs, out)
        index = {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.rglob("*")) if path.is_file()}
        _write_json(out / "artifacts.json", {"status": "complete", "sha256": index})
        return summary
    except Exception as exc:
        _write_json(out / "failure.json", {"status": "incomplete", "completed_pair_count": len(pairs), "error_type": type(exc).__name__, "message": str(exc)})
        raise


def load_calibration_summary(path=None):
    """Verify complete packaged calibration evidence, without running a model."""
    path = Path(path or DEFAULT_RESULTS / "summary.json")
    if path.name != "summary.json":
        raise ValueError("Select the calibration summary.json artifact")
    artifacts = json.loads((path.parent / "artifacts.json").read_text(encoding="utf-8"))
    index = artifacts.get("sha256", {})
    required = {"summary.json", "manifest.json", "PROTOCOL.md", "freeze.json", "frozen_source.zip", "histories.jsonl.gz", "trial_metrics.csv", "paired_metrics.csv", "diagnostics.csv", "point_metrics.csv.gz", "freshness_audit.json", "historical_reference.json", "calibration_coverage.png", "calibration_failure.png"}
    if artifacts.get("status") != "complete" or not required.issubset(index):
        raise ValueError("Calibration evidence is incomplete")
    expanded = path.parent / "frozen_source"
    for name, expected in index.items():
        _check_relative_path(name)
        if name.startswith("frozen_source/") and not expanded.exists():
            continue
        if hashlib.sha256((path.parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Calibration artifact changed: {name}")
    summary = json.loads(path.read_text(encoding="utf-8"))
    freeze = json.loads((path.parent / "freeze.json").read_text(encoding="utf-8"))
    manifest_bytes = (path.parent / "manifest.json").read_bytes()
    manifest = SensitivityManifest.model_validate_json(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if summary["manifest_sha256"] != manifest_hash or freeze["manifest_sha256"] != manifest_hash:
        raise ValueError("Calibration manifest identity differs from frozen records")
    if freeze["protocol_sha256"] != hashlib.sha256((path.parent / "PROTOCOL.md").read_bytes()).hexdigest():
        raise ValueError("Calibration protocol identity differs from frozen record")
    if summary["study_id"] != manifest.study_id or summary["baseline_settings"] != manifest.baseline_settings or summary["sensitivity_settings"] != manifest.sensitivity_settings:
        raise ValueError("Calibration summary differs from executed design")
    sources = freeze["source_sha256"]
    if not sources or summary["source_fingerprint"] != _digest(sources) or freeze["source_fingerprint"] != _digest(sources):
        raise ValueError("Calibration source fingerprint differs from frozen records")
    for name, expected in sources.items():
        _check_relative_path(name)
        if index.get(f"frozen_source/{name}") != expected:
            raise ValueError("Calibration source and artifact indexes differ")
    if {name for name in index if name.startswith("frozen_source/")} != {f"frozen_source/{name}" for name in sources}:
        raise ValueError("Unexpected calibration source index member")
    with zipfile.ZipFile(path.parent / "frozen_source.zip") as archive:
        names = archive.namelist()
        for name in names:
            _check_relative_path(name)
        if len(names) != len(set(names)) or set(names) != set(sources):
            raise ValueError("Calibration source archive differs from source index")
        for name, expected in sources.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Calibration archived source changed: {name}")
    if expanded.exists() and {item.relative_to(expanded).as_posix() for item in expanded.rglob("*") if item.is_file()} != set(sources):
        raise ValueError("Expanded calibration source differs from source index")
    return summary
