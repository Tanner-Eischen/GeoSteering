"""Frozen paired study using public observations and existing causal mechanics.

The policy boundary is choose_command: it receives no Scenario or SensorConfig.
Private geology is used only by the synthetic instrument and final evaluator.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import platform
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.geo.evaluation import evaluate_trajectory
from app.geo.formation import Scenario, formation_top_base
from app.sim.causal import guided_command, landing_trajectory
from app.sim.trajectory_response import advance_station

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "case_studies" / "robustness_v1" / "manifest.json"
if not DEFAULT_MANIFEST.is_file():
    DEFAULT_MANIFEST = Path(sys.prefix) / "share" / "geosteering" / "case_studies" / "robustness_v1" / "manifest.json"
DEFAULT_RESULTS = DEFAULT_MANIFEST.parent / "results"
STRATEGIES = {"hold": "HOLD", "regional_plan": "Offset-derived plan", "guided": "Observation-guided"}
NOTES = [
    "Synthetic, handpicked cases; descriptive results do not estimate real-field performance.",
    "The evaluation cases and noise seeds were declared before this study run; the policy was not retuned using these results.",
    "Seed ranges describe repeated measurement noise within one fixed geology; they are not confidence intervals over geology.",
    "The original signed-distance guided controller is unchanged. A fixed wrapper rejects saturated or missing measurements and retains delayed acquisition poses.",
    "When a step delivers no usable measurement, guided uses HOLD. Old observations enter the controller history only once.",
    "All strategies share landing state, geology, step-keyed noise and missingness, the 5,000-ft denominator, and the 3 degrees/100 ft lateral limit.",
    "The offset-derived plan uses exact synthetic boundary picks at x=0, 500 and 900 ft and never updates from active-well logs.",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SensorConfig(StrictModel):
    gradient_api_per_ft: float = Field(default=2.0, gt=0)
    bias_api: float = 0.0
    noise_std_api: float = Field(default=0.6, ge=0)
    clip_min_api: float = 20.0
    clip_max_api: float = 160.0
    missing_probability: float = Field(default=0.0, ge=0, le=1)
    delay_steps: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode="after")
    def ordered_limits(self):
        if self.clip_max_api <= self.clip_min_api:
            raise ValueError("Instrument clipping maximum must exceed minimum")
        return self


class StudyCase(StrictModel):
    case_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    label: str
    split: Literal["development", "evaluation"]
    description: str
    geology: dict[str, float] = Field(default_factory=dict)
    sensor: SensorConfig = Field(default_factory=SensorConfig)

    @model_validator(mode="after")
    def validate_geology(self):
        allowed = {"regional_dip", "thickness_ft", "disturbance_height_ft", "disturbance_width_ft", "disturbance_x_ft"}
        if set(self.geology) - allowed:
            raise ValueError("Study varies only dip, thickness, and structural transition parameters")
        scenario = Scenario(**self.geology)
        if scenario.disturbance_x_ft <= 900.0:
            raise ValueError("Structural change must be beyond the observed offsets")
        return self


class StudyManifest(StrictModel):
    schema_version: Literal[1]
    study_id: str
    policy_version: Literal["reference-guided-with-validity-gate-v1"]
    description: str
    development_seeds: list[int] = Field(min_length=1)
    evaluation_seeds: list[int] = Field(min_length=1)
    cases: list[StudyCase] = Field(min_length=2)

    @model_validator(mode="after")
    def distinct_holdout(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique")
        for seeds in (self.development_seeds, self.evaluation_seeds):
            if len(set(seeds)) != len(seeds) or any(type(seed) is not int or seed < 0 for seed in seeds):
                raise ValueError("Seeds must be unique nonnegative integers")
        if set(self.development_seeds) & set(self.evaluation_seeds):
            raise ValueError("Development and evaluation seeds must be disjoint")
        signatures = {split: set() for split in ("development", "evaluation")}
        for case in self.cases:
            # Held-out geology, not merely a fresh noise seed or sensor setting.
            scenario = Scenario(**case.geology)
            signatures[case.split].add(tuple(getattr(scenario, key) for key in (
                "regional_dip", "thickness_ft", "disturbance_height_ft", "disturbance_width_ft", "disturbance_x_ft",
            )))
        if not all(signatures.values()) or signatures["development"] & signatures["evaluation"]:
            raise ValueError("Development and evaluation geological configurations must be present and disjoint")
        return self


def load_manifest(path: str | Path | None = None) -> StudyManifest:
    return StudyManifest.model_validate_json(Path(path or DEFAULT_MANIFEST).read_text(encoding="utf-8"))


def step_noise(seed: int, step_index: int) -> tuple[float, float]:
    """Same standard-normal draw and missingness uniform for every paired path."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, step_index, 7183]))
    return float(rng.normal()), float(rng.uniform())


def sample_instrument(station: dict, scenario: Scenario, sensor: SensorConfig, seed: int, step_index: int) -> dict:
    normal, missing_uniform = step_noise(seed, step_index)
    top, base = formation_top_base(station["x_ft"], scenario)
    raw = 80.0 + sensor.bias_api + sensor.gradient_api_per_ft * (station["tvd_ft"] - float((top + base) / 2))
    saturated = raw <= sensor.clip_min_api or raw >= sensor.clip_max_api
    gr = float(np.clip(raw, sensor.clip_min_api, sensor.clip_max_api) + sensor.noise_std_api * normal)
    missing = missing_uniform < sensor.missing_probability
    # Saturation is the instrument's clipping flag, not a field-coordinate hint.
    return {
        "acquired_step": step_index, "delivered_step": step_index + sensor.delay_steps,
        "md_ft": station["md_ft"], "x_ft": station["x_ft"], "tvd_ft": station["tvd_ft"],
        "GR": None if missing else gr, "missing": missing, "saturated": saturated,
    }


def offset_evidence(scenario: Scenario) -> dict:
    """Synthetic observed marker picks only; unknown disturbance is not supplied."""
    x = np.array([0.0, 500.0, 900.0])
    top, base = formation_top_base(x, scenario)
    slope, intercept = np.polyfit(x, (top + base) / 2, 1)
    return {
        "markers": [{"x_ft": float(a), "top_tvd_ft": float(b), "base_tvd_ft": float(c)} for a, b, c in zip(x, top, base)],
        "slope": float(slope), "intercept_ft": float(intercept),
    }


def choose_command(strategy: str, station: dict, observations: list[dict], regional: dict, *, fresh_usable: bool) -> tuple[str, float]:
    """Controller boundary: only current pose, delivered measurements and offsets.

    Delayed measurements retain the pose at which they were acquired. The
    unchanged guided controller consequently experiences actual measurement lag.
    """
    if strategy not in STRATEGIES:
        raise ValueError("Unknown study strategy")
    if strategy == "hold" or (strategy == "guided" and not fresh_usable):
        return "HOLD", station["inc_deg"]
    if strategy == "guided":
        return guided_command(station, observations)
    center = regional["slope"] * station["x_ft"] + regional["intercept_ft"]
    desired_slope = np.clip(regional["slope"] + (center - station["tvd_ft"]) / 150.0, -0.08, 0.08)
    target = math.degrees(math.acos(float(desired_slope)))
    delta = target - station["inc_deg"]
    return ("HOLD" if abs(delta) < 0.03 else ("BUILD" if delta > 0 else "DROP")), target


def run_trial(case: StudyCase, seed: int, strategy: str) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError("Unknown study strategy")
    scenario = Scenario(**case.geology, seed=seed)
    regional = offset_evidence(scenario)
    trajectory = landing_trajectory(scenario).to_dict(orient="records")
    station = trajectory[-1]
    usable_history, pending, decisions = [], [], []
    step = 0
    while station["md_ft"] < scenario.max_md_ft - 1e-9:
        acquired = sample_instrument(station, scenario, case.sensor, seed, step)
        pending.append(acquired)
        delivered = [item for item in pending if item["delivered_step"] == step]
        pending = [item for item in pending if item["delivered_step"] > step]
        usable = [item for item in delivered if not item["missing"] and not item["saturated"]]
        usable_history.extend(usable)
        action, target = choose_command(strategy, station, usable_history, regional, fresh_usable=bool(usable))
        next_station, response = advance_station(
            station, action, min(scenario.step_ft, scenario.max_md_ft - station["md_ft"]),
            scenario.max_dls_deg_per_100ft, target,
        )
        decisions.append({
            "step_index": step, "md_from_ft": station["md_ft"], "md_to_ft": next_station["md_ft"],
            "acquired": acquired, "delivered": delivered,
            "usable_measurement_count": len(usable_history), "fallback_hold": strategy == "guided" and not usable,
            "previous_inc_deg": station["inc_deg"], **response,
        })
        trajectory.append(next_station)
        station = next_station
        step += 1
    metrics = evaluate_trajectory(pd.DataFrame(trajectory), scenario)
    metrics.update({
        "clipped_command_count": sum(bool(item["clipped"]) for item in decisions),
        "action_change_count": sum(a["action"] != b["action"] for a, b in zip(decisions, decisions[1:])),
        "total_inc_change_deg": sum(abs(item["effective_inc_deg"] - item["previous_inc_deg"]) for item in decisions),
        "fallback_hold_count": sum(bool(item["fallback_hold"]) for item in decisions),
        "missing_measurement_count": sum(bool(item["acquired"]["missing"]) for item in decisions),
        "saturated_measurement_count": sum(bool(item["acquired"]["saturated"]) for item in decisions),
        "usable_measurement_count": len(usable_history),
    })
    return {
        "case_id": case.case_id, "split": case.split, "seed": seed, "strategy": strategy,
        "metrics": metrics, "offset_evidence": regional, "trajectory": trajectory, "decisions": decisions,
    }


def paired_stats(values: list[float]) -> dict:
    return {
        "mean": float(np.mean(values)), "min": min(values), "max": max(values),
        "wins": sum(value > 1e-9 for value in values), "losses": sum(value < -1e-9 for value in values),
        "ties": sum(abs(value) <= 1e-9 for value in values),
    }


def summarize(manifest: StudyManifest, trials: list[dict]) -> tuple[dict, list[dict]]:
    expected = {
        (case.case_id, seed, strategy)
        for case in manifest.cases
        for seed in (manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds)
        for strategy in STRATEGIES
    }
    indexed = {(run["case_id"], run["seed"], run["strategy"]): run for run in trials}
    if len(indexed) != len(trials) or set(indexed) != expected:
        raise ValueError("Study requires exactly one completed trial for every declared case/seed/strategy")
    case_results, paired = [], []
    for case in manifest.cases:
        seeds = manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds
        strategies = {}
        for strategy in STRATEGIES:
            metrics = [indexed[case.case_id, seed, strategy]["metrics"] for seed in seeds]
            scores = [item["percent_in_zone"] for item in metrics]
            strategies[strategy] = {
                "mean_percent_in_zone": float(np.mean(scores)), "min_percent_in_zone": min(scores), "max_percent_in_zone": max(scores),
                "mean_max_overshoot_ft": float(np.mean([item["max_overshoot_ft"] for item in metrics])),
                "max_dls_violation_count": max(item["dls_violation_count"] for item in metrics),
                "mean_total_inc_change_deg": float(np.mean([item["total_inc_change_deg"] for item in metrics])),
                "mean_fallback_hold_count": float(np.mean([item["fallback_hold_count"] for item in metrics])),
            }
        case_paired = {}
        for baseline in ("hold", "regional_plan"):
            key = f"guided_minus_{baseline}_pp"
            values = []
            for seed in seeds:
                delta = indexed[case.case_id, seed, "guided"]["metrics"]["percent_in_zone"] - indexed[case.case_id, seed, baseline]["metrics"]["percent_in_zone"]
                values.append(delta)
                paired.append({"case_id": case.case_id, "split": case.split, "seed": seed, "comparison": key, "difference_pp": delta})
            case_paired[key] = paired_stats(values)
        case_results.append({
            "case_id": case.case_id, "label": case.label, "split": case.split, "description": case.description,
            "geology": case.geology, "sensor": case.sensor.model_dump(), "seed_count": len(seeds),
            "strategies": strategies, "paired": case_paired,
        })
    evaluation = [item for item in case_results if item["split"] == "evaluation"]
    eval_runs = [item for item in trials if item["split"] == "evaluation"]
    worst = min((item for item in eval_runs if item["strategy"] == "guided"), key=lambda item: item["metrics"]["percent_in_zone"])
    summary = {
        "schema_version": 1, "study_id": manifest.study_id, "policy_version": manifest.policy_version,
        "strategies": STRATEGIES,
        "counts": {"development_cases": len(case_results) - len(evaluation), "evaluation_cases": len(evaluation), "trial_count": len(trials)},
        "case_results": case_results,
        "evaluation": {
            "mean_percent_in_zone": {strategy: float(np.mean([case["strategies"][strategy]["mean_percent_in_zone"] for case in evaluation])) for strategy in STRATEGIES},
            "paired": {key: paired_stats([item["difference_pp"] for item in paired if item["split"] == "evaluation" and item["comparison"] == key]) for key in ("guided_minus_hold_pp", "guided_minus_regional_plan_pp")},
            "dls_violation_count": sum(item["metrics"]["dls_violation_count"] for item in eval_runs),
        },
        "worst_guided": {"case_id": worst["case_id"], "seed": worst["seed"], **worst["metrics"]},
        "interpretation_notes": NOTES,
    }
    return summary, paired


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def freeze_sources(out: Path, manifest_bytes: bytes) -> dict:
    """Capture executable source bytes before starting any evaluation trial."""
    hashes = {}
    for package in ("app", "tools"):
        for source in sorted((ROOT / package).rglob("*.py")):
            relative = source.relative_to(ROOT)
            data = source.read_bytes()
            target = out / "frozen_source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    for source in [ROOT / "pyproject.toml", *sorted(ROOT.glob("requirements*.txt"))]:
        if not source.is_file():
            continue
        target = out / "frozen_source" / source.name
        data = source.read_bytes()
        target.write_bytes(data)
        hashes[source.name] = hashlib.sha256(data).hexdigest()
    (out / "manifest.json").write_bytes(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    frozen = {
        "manifest_sha256": manifest_hash, "source_fingerprint": fingerprint, "source_sha256": hashes,
        "python_version": sys.version, "platform": platform.platform(),
        "dependencies": {name: version(name) for name in ("numpy", "pandas", "pydantic", "matplotlib", "streamlit", "pyarrow")},
        "freeze_order": "Manifest and executable source copies written before first trial; no policy parameter search",
    }
    _write_json(out / "freeze.json", frozen)
    # A self-contained source archive also travels in installed wheel evidence.
    # Stable entry order, timestamps, permissions and bytes make it reproducible.
    with zipfile.ZipFile(out / "frozen_source.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(hashes):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, (out / "frozen_source" / name).read_bytes(), compresslevel=9)
    return frozen


def render_figures(summary: dict, trials: list[dict], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cases = [case for case in summary["case_results"] if case["split"] == "evaluation"]
    colors = {"hold": "#a75d34", "regional_plan": "#5d7181", "guided": "#0f766e"}
    fig, ax = plt.subplots(figsize=(12, 7.5), layout="constrained")
    y = np.arange(len(cases))
    for index, (strategy, label) in enumerate(STRATEGIES.items()):
        rows = [case["strategies"][strategy] for case in cases]
        means = np.array([row["mean_percent_in_zone"] for row in rows])
        positions = y + (index - 1) * 0.24
        minima = [row["min_percent_in_zone"] for row in rows]
        maxima = [row["max_percent_in_zone"] for row in rows]
        ax.barh(positions, means, height=0.22, label=label, color=colors[strategy])
        ax.hlines(positions, minima, maxima, color="#182f3b", linewidth=0.8)
        ax.plot(minima, positions, "|", color="#182f3b", markersize=4)
        ax.plot(maxima, positions, "|", color="#182f3b", markersize=4)
    ax.set_yticks(y, [case["label"] for case in cases])
    ax.invert_yaxis()
    ax.set_xlim(0, 101)
    seed_counts = {case["seed_count"] for case in cases}
    seed_label = f"{next(iter(seed_counts))} noise seeds" if len(seed_counts) == 1 else "declared noise seeds"
    ax.set_xlabel(f"True lateral in target (%) · mean and min–max across {seed_label}")
    ax.set_title("Held-out synthetic robustness study", loc="left", fontweight="bold", pad=16)
    ax.legend(loc="lower right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)
    fig.savefig(out / "robustness_results.png", dpi=180)
    plt.close(fig)

    worst = summary["worst_guided"]
    case = next(case for case in cases if case["case_id"] == worst["case_id"])
    scenario = Scenario(**case["geology"])
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained", gridspec_kw={"height_ratios": [2, 1]})
    x = np.linspace(scenario.landing_x_ft, scenario.landing_x_ft + scenario.lateral_length_ft, 1200)
    top, base = formation_top_base(x, scenario)
    axes[0].fill_between(x, top, base, color="#d9e8d4", label="Withheld target (evaluation only)")
    for strategy in STRATEGIES:
        run = next(run for run in trials if run["case_id"] == worst["case_id"] and run["seed"] == worst["seed"] and run["strategy"] == strategy)
        path = pd.DataFrame(run["trajectory"])
        path = path[path.md_ft >= scenario.lateral_start_md_ft]
        axes[0].plot(path.x_ft, path.tvd_ft, color=colors[strategy], label=f"{STRATEGIES[strategy]} · {run['metrics']['percent_in_zone']:.1f}%")
        if strategy == "guided":
            events = run["decisions"]
            axes[1].plot([event["md_from_ft"] for event in events], [event["acquired"]["GR"] if not event["acquired"]["missing"] else np.nan for event in events], color=colors[strategy], label="Acquired GR")
            invalid = [event for event in events if event["acquired"]["saturated"] and not event["acquired"]["missing"]]
            axes[1].scatter([event["md_from_ft"] for event in invalid], [event["acquired"]["GR"] for event in invalid], color="#a75d34", marker="x", label="Saturated; excluded from inversion", zorder=4)
    axes[0].invert_yaxis()
    axes[0].set_ylabel("Local TVD (ft; positive down)")
    axes[0].set_xlabel("Along-track x (ft)")
    axes[0].set_title(f"Failure review: {case['label']} · seed {worst['seed']}", loc="left", fontweight="bold")
    axes[1].set_xlabel("Acquisition measured depth (ft)")
    axes[1].set_ylabel("Synthetic GR (API)")
    for ax in axes:
        ax.legend(frameon=False, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.15)
    fig.savefig(out / "robustness_worst_case.png", dpi=180)
    plt.close(fig)


def run_study(out: str | Path, manifest_path: str | Path | None = None) -> dict:
    manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
    manifest_bytes = manifest_path.read_bytes()
    manifest = StudyManifest.model_validate_json(manifest_bytes)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose a new or empty study output directory; existing evidence is never replaced")
    out.mkdir(parents=True, exist_ok=True)
    frozen = freeze_sources(out, manifest_bytes)
    trials = []
    try:
        with (out / "histories.jsonl.gz").open("wb") as raw_history, gzip.GzipFile(filename="", mode="wb", fileobj=raw_history, mtime=0) as history:
            for case in manifest.cases:
                seeds = manifest.development_seeds if case.split == "development" else manifest.evaluation_seeds
                for seed in seeds:
                    for strategy in STRATEGIES:
                        trial = run_trial(case, seed, strategy)
                        trials.append(trial)
                        history.write((json.dumps(trial, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
        summary, paired = summarize(manifest, trials)
        summary.update({"manifest_sha256": frozen["manifest_sha256"], "source_fingerprint": frozen["source_fingerprint"]})
        _write_json(out / "summary.json", summary)
        pd.DataFrame([{key: trial[key] for key in ("case_id", "split", "seed", "strategy")} | trial["metrics"] for trial in trials]).to_csv(out / "trials.csv", index=False)
        pd.DataFrame(paired).to_csv(out / "paired.csv", index=False)
        render_figures(summary, trials, out)
        artifacts = {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.rglob("*")) if path.is_file()}
        _write_json(out / "artifacts.json", {"status": "complete", "sha256": artifacts})
        return summary
    except Exception as exc:
        _write_json(out / "failure.json", {"status": "incomplete", "completed_trial_count": len(trials), "error_type": type(exc).__name__, "message": str(exc)})
        raise


def load_summary(path: str | Path | None = None) -> dict:
    """Read only complete, artifact-verified saved results; never runs a study."""
    path = Path(path or DEFAULT_RESULTS / "summary.json")
    if path.name != "summary.json":
        raise ValueError("Select the study summary.json artifact")
    artifacts = json.loads((path.parent / "artifacts.json").read_text(encoding="utf-8"))
    if artifacts.get("status") != "complete":
        raise ValueError("Robustness study is incomplete")
    index = artifacts["sha256"]
    required = {"summary.json", "manifest.json", "freeze.json", "frozen_source.zip", "trials.csv", "paired.csv", "histories.jsonl.gz", "robustness_results.png", "robustness_worst_case.png"}
    if not required.issubset(index):
        raise ValueError("Study artifact index is incomplete")
    expanded = path.parent / "frozen_source"
    for name, expected in index.items():
        _check_relative_path(name)
        # Wheels carry the mandatory source archive rather than duplicate source
        # trees. If an expanded tree exists, every indexed source is required.
        if name.startswith("frozen_source/") and not expanded.exists():
            continue
        actual = hashlib.sha256((path.parent / name).read_bytes()).hexdigest()
        if expected != actual:
            raise ValueError(f"Study artifact changed: {name}")
    summary = json.loads(path.read_text(encoding="utf-8"))
    freeze = json.loads((path.parent / "freeze.json").read_text(encoding="utf-8"))
    manifest_bytes = (path.parent / "manifest.json").read_bytes()
    manifest = StudyManifest.model_validate_json(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if summary["manifest_sha256"] != manifest_hash or freeze["manifest_sha256"] != manifest_hash:
        raise ValueError("Study manifest identity does not match summary and freeze")
    if summary["study_id"] != manifest.study_id or summary["policy_version"] != manifest.policy_version:
        raise ValueError("Study summary does not match manifest identity")
    source_index = freeze["source_sha256"]
    if not source_index:
        raise ValueError("Frozen source index is empty")
    for name, expected in source_index.items():
        _check_relative_path(name)
        if index.get(f"frozen_source/{name}") != expected:
            raise ValueError(f"Frozen source index does not match artifact index: {name}")
    fingerprint = hashlib.sha256(json.dumps(source_index, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if summary["source_fingerprint"] != fingerprint or freeze["source_fingerprint"] != fingerprint:
        raise ValueError("Frozen source fingerprint does not match summary and freeze")
    expected_expanded = {f"frozen_source/{name}" for name in source_index}
    if {name for name in index if name.startswith("frozen_source/")} != expected_expanded:
        raise ValueError("Artifact index contains an unexpected frozen source")
    with zipfile.ZipFile(path.parent / "frozen_source.zip") as archive:
        names = archive.namelist()
        for name in names:
            _check_relative_path(name)
        if len(names) != len(set(names)) or set(names) != set(source_index):
            raise ValueError("Frozen source archive does not match source index")
        for name, expected in source_index.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Frozen source archive changed: {name}")
    if expanded.exists():
        actual_names = {item.relative_to(expanded).as_posix() for item in expanded.rglob("*") if item.is_file()}
        if actual_names != set(source_index):
            raise ValueError("Expanded frozen source does not match source index")
    return summary


def _check_relative_path(name: str) -> None:
    """Reject escaping or ambiguous index/archive names; never extract archives."""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Unsafe study artifact path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name or name == ".":
        raise ValueError("Unsafe study artifact path")
