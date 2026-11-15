from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import shutil
import zipfile

import pytest

from app.geo.formation import Scenario
from app.study import uncertainty_calibration as study
from app.study.robustness import SensorConfig, StudyCase


def compact_manifest():
    data = study.load_manifest().model_dump()
    # Dedicated test geology is separate from the unobserved evaluation protocol.
    data["cases"] = [data["cases"][0], {
        "case_id": "eval_test_only", "label": "Test-only", "split": "evaluation", "description": "Software test, excluded from reported study",
        "geology": {"regional_dip": 0.0027, "disturbance_height_ft": 2.0, "disturbance_width_ft": 400.0, "disturbance_x_ft": 3500.0, "thickness_ft": 23.0},
        "sensor": {},
    }]
    data["development_seeds"] = [8801]
    data["evaluation_seeds"] = [8803]
    data["settings"]["member_count"] = 64
    return study.CalibrationManifest.model_validate(data)


def _signature(case):
    scenario = Scenario(**case.geology)
    return tuple(getattr(scenario, name) for name in ("regional_dip", "thickness_ft", "disturbance_height_ft", "disturbance_width_ft", "disturbance_x_ft"))


def test_predeclared_evaluation_is_new_geology_and_noise():
    manifest = study.load_manifest()
    previous = json.loads((study.ROOT / "case_studies/robustness_v1/manifest.json").read_text())
    old = [StudyCase.model_validate(case) for case in previous["cases"]]
    assert len(manifest.cases) == 8
    assert len([case for case in manifest.cases if case.split == "evaluation"]) == 6
    assert not {_signature(case) for case in manifest.cases} & {_signature(case) for case in old}
    assert not set(manifest.development_seeds + manifest.evaluation_seeds) & set(previous["development_seeds"] + previous["evaluation_seeds"])
    changed = manifest.model_dump()
    changed["evaluation_seeds"] = changed["development_seeds"]
    with pytest.raises(ValueError, match="seeds must be disjoint"):
        study.CalibrationManifest.model_validate(changed)
    changed = manifest.model_dump()
    changed["cases"][2]["geology"] = changed["cases"][0]["geology"]
    with pytest.raises(ValueError, match="geological configurations"):
        study.CalibrationManifest.model_validate(changed)
    changed = manifest.model_dump()
    changed["cases"][2]["sensor"]["delay_steps"] = 2
    with pytest.raises(ValueError, match="Delayed measurements"):
        study.CalibrationManifest.model_validate(changed)


def test_current_prior_is_queried_before_measurement_and_truth_scores_after_completion(monkeypatch):
    manifest = compact_manifest()
    Settings, initialize, update, summarize, forecast = study._engine()
    calls = []
    pending = None

    def observed_update(state, **kwargs):
        nonlocal pending
        digest = study._digest(state)
        assert set(kwargs) == {"x_ft", "tvd_ft", "gr_api", "observation_md_ft", "step_index"}
        assert "scenario" not in inspect.signature(update).parameters
        if len(calls) % 2 == 0:
            assert kwargs["gr_api"] is None
            pending = digest
        else:
            assert digest == pending
        result = update(state, **kwargs)
        assert study._digest(state) == digest, "Filter mutated an old particle state"
        calls.append(kwargs["step_index"])
        return result

    monkeypatch.setattr(study, "_engine", lambda: (Settings, initialize, observed_update, summarize, forecast))
    original_score = study.score_predictions

    def late_score(events, scenario):
        assert len(calls) == 202 and len(events) == 101
        return original_score(events, scenario)

    monkeypatch.setattr(study, "score_predictions", late_score)
    trial = study.run_trial(manifest.cases[0], 8801, manifest)
    assert len(trial["events"]) == 101
    assert trial["metrics"]["prior_current"]["point_count"] == trial["metrics"]["posterior_current"]["point_count"] == 101


def test_forecast_domain_denominators_and_paired_locations():
    manifest = compact_manifest()
    trial = study.run_trial(manifest.cases[0], 8801, manifest)
    assert trial["metrics"]["forecast_250"]["point_count"] == 96
    assert trial["metrics"]["forecast_500"]["point_count"] == 91
    assert trial["paired_forecasts"]["forecast_250"]["point_count"] == trial["paired_forecasts"]["forecast_500"]["point_count"] == 91
    assert trial["diagnostics"]["forecast_exclusion_count"] == 15
    endpoint = trial["evaluated_x_domain"][1]
    assert all(row["target_x_ft"] <= endpoint for row in trial["point_metrics"])
    prior = [(row["target_x_ft"], row["true_center_tvd_ft"]) for row in trial["point_metrics"] if row["phase"] == "prior_current"]
    posterior = [(row["target_x_ft"], row["true_center_tvd_ft"]) for row in trial["point_metrics"] if row["phase"] == "posterior_current"]
    assert prior == posterior
    assert all(item["reason"] == "outside_evaluated_x_domain" for event in trial["events"] for item in event["forecast_exclusions"])


def test_missing_measurements_propagate_without_weight_update():
    manifest = compact_manifest()
    case = manifest.cases[0].model_copy(update={"sensor": SensorConfig(missing_probability=1)})
    trial = study.run_trial(case, 8801, manifest)
    assert trial["diagnostics"]["measurement_used_count"] == 0
    assert trial["diagnostics"]["missing_measurement_count"] == trial["diagnostics"]["dropped_measurement_count"] == 101
    for event in trial["events"]:
        assert event["prior_current"] == event["posterior_current"]
        assert event["prior_state_sha256"] == event["posterior_state_sha256"]


def test_saturation_uses_available_clipped_likelihood_instead_of_exact_inversion():
    manifest = compact_manifest()
    case = manifest.cases[0].model_copy(update={"sensor": SensorConfig(bias_api=200, noise_std_api=0.6)})
    trial = study.run_trial(case, 8801, manifest)
    assert trial["diagnostics"]["saturated_measurement_count"] == 101
    assert trial["diagnostics"]["measurement_used_count"] == 101
    assert trial["diagnostics"]["dropped_measurement_count"] == 0
    assert all("saturated" not in event["diagnostics"] for event in trial["events"])


def test_analytic_center_scoring_coverage_and_width():
    scenario = Scenario(regional_dip=0, disturbance_height_ft=0)
    center = scenario.landing_center_tvd_ft
    event = {
        "step_index": 0, "x_ft": scenario.landing_x_ft,
        "prior_current": {"q05": center - 4, "q50": center, "q95": center + 4},
        "posterior_current": {"q05": center + 1, "q50": center + 2, "q95": center + 3},
        "forecasts": [], "paired_forecast_origin": False,
    }
    rows = study.score_predictions([event], scenario)
    assert study._point_metrics(rows) == {"point_count": 2, "covered_count": 1, "coverage_pct": 50, "mean_width_ft": 5, "mean_abs_center_error_ft": 1}


def test_aggregation_averages_trial_coverage_instead_of_pooling_correlated_points():
    first = {"point_count": 1, "coverage_pct": 100, "mean_width_ft": 2, "mean_abs_center_error_ft": 1}
    second = {"point_count": 99, "coverage_pct": 0, "mean_width_ft": 8, "mean_abs_center_error_ft": 3}
    result = study._aggregate_metrics([first, second])
    assert result["mean_coverage_pct"] == 50
    assert result["mean_width_ft"] == 5
    assert result["total_point_count"] == 100


def test_full_trial_state_and_forecast_replay_is_exact_and_detects_changed_observation():
    manifest = compact_manifest()
    trial = study.run_trial(manifest.cases[0], 8801, manifest)
    assert study.replay_trial_history(trial) == 101
    trial["events"][30]["measurement"]["GR"] += 1
    with pytest.raises(ValueError, match="posterior state differs"):
        study.replay_trial_history(trial)


@pytest.fixture(scope="module")
def complete_evidence(tmp_path_factory):
    root = tmp_path_factory.mktemp("uncertainty-evidence")
    manifest = root / "manifest.json"
    manifest.write_text(compact_manifest().model_dump_json(), encoding="utf-8")
    (root / "PROTOCOL.md").write_text("# Isolated software-test protocol\n", encoding="utf-8")
    out = root / "results"
    study.run_study(out, manifest)
    return out, manifest


def test_complete_output_reproducibility_and_protocol_source_freeze(complete_evidence, tmp_path):
    out, manifest = complete_evidence
    summary = study.load_uncertainty_summary(out / "summary.json")
    assert summary["counts"]["trial_count"] == 2
    with gzip.open(out / "histories.jsonl.gz", "rt", encoding="utf-8") as handle:
        histories = [json.loads(line) for line in handle]
    assert len(histories) == 2 and study.replay_trial_history(histories[0]) == 101
    freeze = json.loads((out / "freeze.json").read_text())
    assert freeze["protocol_sha256"] == hashlib.sha256((out / "PROTOCOL.md").read_bytes()).hexdigest()
    with zipfile.ZipFile(out / "frozen_source.zip") as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    repeat = tmp_path / "repeat"
    study.run_study(repeat, manifest)
    assert (out / "histories.jsonl.gz").read_bytes() == (repeat / "histories.jsonl.gz").read_bytes()
    assert (out / "point_metrics.csv.gz").read_bytes() == (repeat / "point_metrics.csv.gz").read_bytes()
    with pytest.raises(ValueError, match="evidence is never replaced"):
        study.run_study(out, manifest)


def test_installed_wheel_style_evidence_needs_no_expanded_source(complete_evidence, tmp_path):
    source, _ = complete_evidence
    out = tmp_path / "installed"
    out.mkdir()
    for item in source.iterdir():
        if item.is_file():
            shutil.copyfile(item, out / item.name)
    assert study.load_uncertainty_summary(out / "summary.json")["counts"]["trial_count"] == 2
    (out / "frozen_source.zip").unlink()
    with pytest.raises(FileNotFoundError):
        study.load_uncertainty_summary(out / "summary.json")


@pytest.mark.parametrize("artifact", ["trial_metrics.csv", "PROTOCOL.md", "frozen_source/app/study/uncertainty_calibration.py", "frozen_source.zip"])
def test_tampered_metrics_protocol_or_source_are_rejected(complete_evidence, tmp_path, artifact):
    source, _ = complete_evidence
    out = tmp_path / "changed"
    shutil.copytree(source, out)
    (out / artifact).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        study.load_uncertainty_summary(out / "summary.json")


def test_metadata_and_unsafe_index_paths_are_rejected(complete_evidence, tmp_path):
    source, _ = complete_evidence
    out = tmp_path / "changed"
    shutil.copytree(source, out)
    summary_path = out / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["source_fingerprint"] = "changed"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    index_path = out / "artifacts.json"
    index = json.loads(index_path.read_text())
    index["sha256"]["summary.json"] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        study.load_uncertainty_summary(summary_path)
    index["sha256"]["../outside.py"] = "not-read"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe"):
        study.load_uncertainty_summary(summary_path)


def test_failure_never_creates_complete_evidence(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(compact_manifest().model_dump_json(), encoding="utf-8")
    (tmp_path / "PROTOCOL.md").write_text("# Failure test\n", encoding="utf-8")

    def fail(*args):
        raise RuntimeError("Deliberate engine failure")

    monkeypatch.setattr(study, "run_trial", fail)
    out = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="Deliberate"):
        study.run_study(out, manifest)
    assert json.loads((out / "failure.json").read_text())["completed_trial_count"] == 0
    assert not (out / "artifacts.json").exists()
