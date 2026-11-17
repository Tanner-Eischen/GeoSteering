from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import zipfile

import pytest

from app.study import calibration_sensitivity as study
from app.study.robustness import SensorConfig


def compact_manifest():
    data = study.load_manifest().model_dump()
    data["cases"] = [data["cases"][1], {
        "case_id": "eval_software_test", "label": "Software test only", "split": "evaluation",
        "description": "Not part of the fresh scientific evaluation", "evidence_status": "fresh_evaluation",
        "historical_reference": None,
        "geology": {"regional_dip": 0.0029, "disturbance_height_ft": 3.0, "disturbance_width_ft": 600.0, "disturbance_x_ft": 3450.0, "thickness_ft": 22.0},
        "sensor": {"bias_api": 4.0},
    }]
    data["development_seeds"] = [9901]
    data["evaluation_seeds"] = [9907]
    data["baseline_settings"]["member_count"] = 32
    data["sensitivity_settings"]["member_count"] = 32
    return study.SensitivityManifest.model_validate(data)


def test_fresh_manifest_disjoint_from_both_observed_protocols_and_historical_reuse_explicit():
    manifest = study.load_manifest()
    assert len([case for case in manifest.cases if case.split == "evaluation"]) == 6
    assert 2 * len(manifest.development_seeds) + 6 * len(manifest.evaluation_seeds) == 20
    assert study.validate_freshness(manifest)["evaluation_geology_disjoint"]
    reused = [case for case in manifest.cases if case.evidence_status == "diagnostic_reused"]
    assert len(reused) == 1 and reused[0].historical_reference == "uncertainty_v1/eval_bias/7001"
    reference = study._historical_reference(manifest)
    assert reference["metrics"]["posterior_current"]["coverage_pct"] == pytest.approx(2.9702970297029703)
    assert "empirically" in manifest.design_note
    changed = manifest.model_dump()
    changed["evaluation_seeds"] = [7001]
    with pytest.raises(ValueError, match="seeds must be disjoint"):
        study.SensitivityManifest.model_validate(changed)
    changed = manifest.model_dump()
    changed["evaluation_seeds"] = [1001]
    with pytest.raises(ValueError, match="already observed"):
        study.validate_freshness(study.SensitivityManifest.model_validate(changed))
    changed = manifest.model_dump()
    old = json.loads((study._previous_root() / "robustness_v1/results/manifest.json").read_text())
    changed["cases"][2]["geology"] = old["cases"][2]["geology"]
    with pytest.raises(ValueError, match="already observed"):
        study.validate_freshness(study.SensitivityManifest.model_validate(changed))


def test_support_and_noncalibration_settings_cannot_change_silently():
    data = compact_manifest().model_dump()
    data["sensitivity_settings"]["calibration_biases_api"] = [-24, -8, 0, 8, 24]
    with pytest.raises(ValueError, match="support is fixed"):
        study.SensitivityManifest.model_validate(data)
    data = compact_manifest().model_dump()
    data["sensitivity_settings"]["model_discrepancy_std_api"] = 8
    with pytest.raises(ValueError, match="conditional settings must match"):
        study.SensitivityManifest.model_validate(data)


@pytest.fixture(scope="module")
def completed_pair():
    manifest = compact_manifest()
    return manifest, study.run_pair(manifest.cases[1], manifest.evaluation_seeds[0], manifest)


def test_pair_shares_observations_zero_branch_rng_and_fixed_weights(completed_pair):
    _, pair = completed_pair
    assert pair["initial_states"]["v1"] == study._zero_branch(pair["initial_states"]["v2"])
    assert len(pair["events"]) == 101
    for event in pair["events"]:
        assert event["zero_bias_matches_v1"]
        assert event["health"]["v2"]["fixed_component_weights"] == [0.2] * 5
        assert event["health"]["v1"]["measurement_used"] == event["health"]["v2"]["measurement_used"]
        for phase in ("prior_current", "posterior_current"):
            baseline = event["intervals"]["v1_nominal"][phase]
            envelope = event["intervals"]["v2_envelope"][phase]
            assert envelope["q05"] <= baseline["q05"] <= baseline["q95"] <= envelope["q95"]


def test_forecast_domain_common_points_and_paired_deltas(completed_pair):
    _, pair = completed_pair
    for kind in study.INTERVAL_TYPES:
        assert pair["metrics"][kind]["prior_current"]["point_count"] == pair["metrics"][kind]["posterior_current"]["point_count"] == 101
        assert pair["metrics"][kind]["forecast_250"]["point_count"] == 96
        assert pair["metrics"][kind]["forecast_500"]["point_count"] == 91
        assert pair["paired_forecasts"][kind]["forecast_250"]["point_count"] == pair["paired_forecasts"][kind]["forecast_500"]["point_count"] == 91
    assert all(row["target_x_ft"] <= pair["evaluated_x_domain"][1] for row in pair["point_metrics"])
    for kind in ("v2_pooled", "v2_envelope"):
        for phase in study.PHASES:
            a, b = pair["metrics"]["v1_nominal"][phase], pair["metrics"][kind][phase]
            assert pair["paired_deltas"][kind][phase]["coverage_delta_pp"] == b["coverage_pct"] - a["coverage_pct"]
            assert pair["paired_deltas"][kind][phase]["width_delta_ft"] == b["mean_width_ft"] - a["mean_width_ft"]


def test_replay_reproduces_every_prior_posterior_and_forecast_hash(completed_pair):
    _, pair = completed_pair
    assert study.replay_pair(pair) == 101
    changed = json.loads(json.dumps(pair))
    changed["events"][30]["observation"]["GR"] += 1
    with pytest.raises(ValueError, match="posterior state differs"):
        study.replay_pair(changed)


def test_no_truth_scoring_until_both_models_finish_shared_sequence(monkeypatch):
    manifest = compact_manifest()
    original_path = study._fixed_hold_path
    monkeypatch.setattr(study, "_fixed_hold_path", lambda scenario: original_path(scenario)[:3])
    V1, V2, initialize, update, summarize, forecast = study._engine()
    count = 0

    def observed_update(*args, **kwargs):
        nonlocal count
        assert set(kwargs) == {"gr_api", "x_ft", "tvd_ft", "observation_md_ft", "step_index"}
        count += 1
        return update(*args, **kwargs)

    monkeypatch.setattr(study, "_engine", lambda: (V1, V2, initialize, observed_update, summarize, forecast))
    original_score = study.score_predictions

    def late_score(events, scenario):
        assert count == 12  # Three observations × prior/actual × two models.
        return original_score(events, scenario)

    monkeypatch.setattr(study, "score_predictions", late_score)
    pair = study.run_pair(manifest.cases[0], 9901, manifest)
    assert pair["paired_deltas"]["v2_envelope"]["forecast_500"]["coverage_delta_pp"] is None


def test_missing_observations_keep_priors_and_posteriors_equal(monkeypatch):
    manifest = compact_manifest()
    original_path = study._fixed_hold_path
    monkeypatch.setattr(study, "_fixed_hold_path", lambda scenario: original_path(scenario)[:3])
    case = manifest.cases[0].model_copy(update={"sensor": SensorConfig(missing_probability=1)})
    pair = study.run_pair(case, 9901, manifest)
    for event in pair["events"]:
        assert event["observation"]["GR"] is None
        assert event["prior_state_sha256"] == event["posterior_state_sha256"]
        for value in event["intervals"].values():
            assert value["prior_current"] == value["posterior_current"]


def test_paired_aggregate_does_not_count_model_runs_as_independent():
    rows = [{"coverage_delta_pp": 10, "width_delta_ft": 4}, {"coverage_delta_pp": -2, "width_delta_ft": 8}]
    assert study._paired_summary(rows) == {"mean_coverage_delta_pp": 4, "min_coverage_delta_pp": -2, "max_coverage_delta_pp": 10, "mean_width_delta_ft": 6, "paired_trial_count": 2, "valid_paired_trial_count": 2}


@pytest.fixture(scope="module")
def complete_evidence(tmp_path_factory):
    root = tmp_path_factory.mktemp("calibration-evidence")
    manifest = root / "manifest.json"
    manifest.write_text(compact_manifest().model_dump_json(), encoding="utf-8")
    (root / "PROTOCOL.md").write_text("# Isolated software-test protocol\n", encoding="utf-8")
    out = root / "results"
    study.run_study(out, manifest)
    return out, manifest


def test_frozen_source_protocol_and_historical_provenance_are_verified(complete_evidence):
    out, manifest = complete_evidence
    summary = study.load_calibration_summary(out / "summary.json")
    assert summary["counts"]["paired_trial_count"] == 2
    assert summary["counts"]["model_run_count"] == 4
    freeze = json.loads((out / "freeze.json").read_text())
    assert freeze["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert freeze["protocol_sha256"] == hashlib.sha256((out / "PROTOCOL.md").read_bytes()).hexdigest()
    with zipfile.ZipFile(out / "frozen_source.zip") as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    with gzip.open(out / "histories.jsonl.gz", "rt", encoding="utf-8") as stream:
        pairs = [json.loads(line) for line in stream]
    assert len(pairs) == 2 and study.replay_pair(pairs[1]) == 101
    assert json.loads((out / "historical_reference.json").read_text())["evidence_status"] == "diagnostic_reused"


def test_repetition_is_exact_without_replacing_prior_evidence(complete_evidence, tmp_path):
    out, manifest = complete_evidence
    repeated = tmp_path / "repeat"
    study.run_study(repeated, manifest)
    assert (out / "histories.jsonl.gz").read_bytes() == (repeated / "histories.jsonl.gz").read_bytes()
    assert (out / "point_metrics.csv.gz").read_bytes() == (repeated / "point_metrics.csv.gz").read_bytes()
    with pytest.raises(ValueError, match="evidence is never replaced"):
        study.run_study(out, manifest)


def test_root_only_installed_evidence_verifies_archive_without_source_tree(complete_evidence, tmp_path):
    source, _ = complete_evidence
    out = tmp_path / "installed"
    out.mkdir()
    for item in source.iterdir():
        if item.is_file():
            shutil.copyfile(item, out / item.name)
    assert study.load_calibration_summary(out / "summary.json")["counts"]["paired_trial_count"] == 2
    (out / "frozen_source.zip").unlink()
    with pytest.raises(FileNotFoundError):
        study.load_calibration_summary(out / "summary.json")


@pytest.mark.parametrize("name", ["paired_metrics.csv", "historical_reference.json", "PROTOCOL.md", "frozen_source/app/study/calibration_sensitivity.py"])
def test_modified_evidence_or_source_is_rejected(complete_evidence, tmp_path, name):
    source, _ = complete_evidence
    out = tmp_path / "changed"
    shutil.copytree(source, out)
    (out / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        study.load_calibration_summary(out / "summary.json")


def test_metadata_inconsistency_and_unsafe_index_are_rejected(complete_evidence, tmp_path):
    source, _ = complete_evidence
    out = tmp_path / "changed"
    shutil.copytree(source, out)
    summary_path = out / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["sensitivity_settings"]["calibration_biases_api"] = [-24, -8, 0, 8, 24]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    index_path = out / "artifacts.json"
    index = json.loads(index_path.read_text())
    index["sha256"]["summary.json"] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError, match="executed design"):
        study.load_calibration_summary(summary_path)
    index["sha256"]["../outside.py"] = "not-read"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe"):
        study.load_calibration_summary(summary_path)


def test_failure_does_not_publish_complete_index(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(compact_manifest().model_dump_json(), encoding="utf-8")
    (tmp_path / "PROTOCOL.md").write_text("# Failure test\n", encoding="utf-8")
    monkeypatch.setattr(study, "run_pair", lambda *args: (_ for _ in ()).throw(RuntimeError("Deliberate failure")))
    out = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="Deliberate"):
        study.run_study(out, manifest)
    assert json.loads((out / "failure.json").read_text())["completed_pair_count"] == 0
    assert not (out / "artifacts.json").exists()
