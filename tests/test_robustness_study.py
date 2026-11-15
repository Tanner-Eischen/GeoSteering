from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import shutil
import zipfile

import pytest

from app.geo.formation import Scenario
from app.study import robustness as study


def compact_manifest():
    manifest = study.load_manifest().model_dump()
    manifest["cases"] = [manifest["cases"][0], manifest["cases"][2]]
    manifest["development_seeds"] = [101]
    manifest["evaluation_seeds"] = [1001]
    return study.StudyManifest.model_validate(manifest)


def test_manifest_has_real_geological_holdout_and_rejects_overlap():
    manifest = study.load_manifest()
    assert len([case for case in manifest.cases if case.split == "evaluation"]) == 8
    data = manifest.model_dump()
    data["evaluation_seeds"] = data["development_seeds"]
    with pytest.raises(ValueError, match="seeds must be disjoint"):
        study.StudyManifest.model_validate(data)
    data = manifest.model_dump()
    data["cases"][2]["geology"] = data["cases"][0]["geology"]
    with pytest.raises(ValueError, match="geological configurations"):
        study.StudyManifest.model_validate(data)
    data = manifest.model_dump()
    data["cases"][2]["geology"]["disturbance_x_ft"] = 500
    with pytest.raises(ValueError, match="beyond the observed offsets"):
        study.StudyManifest.model_validate(data)


def test_sensor_pairing_bias_saturation_missingness_and_validation():
    station = {"md_ft": 2000.0, "x_ft": 954.9296585513721, "tvd_ft": 1454.929658551372}
    sensor = study.SensorConfig(noise_std_api=0)
    first = study.sample_instrument(station, Scenario(), sensor, 1001, 0)
    second = study.sample_instrument(station | {"tvd_ft": station["tvd_ft"] + 5}, Scenario(), sensor, 1001, 0)
    assert second["GR"] - first["GR"] == pytest.approx(10)
    noisy = study.SensorConfig(noise_std_api=2, missing_probability=0.2)
    a = study.sample_instrument(station, Scenario(), noisy, 1001, 1)
    b = study.sample_instrument(station | {"tvd_ft": station["tvd_ft"] + 5}, Scenario(), noisy, 1001, 1)
    assert a["missing"] == b["missing"]
    if not a["missing"]:
        assert b["GR"] - a["GR"] == pytest.approx(10)
    biased = study.sample_instrument(station, Scenario(), study.SensorConfig(bias_api=12, noise_std_api=0), 1001, 0)
    assert biased["GR"] == pytest.approx(first["GR"] + 12)
    saturated = study.sample_instrument(station | {"tvd_ft": 1600}, Scenario(), sensor, 1001, 0)
    assert saturated["GR"] == 160
    assert saturated["saturated"]
    missing = study.sample_instrument(station, Scenario(), study.SensorConfig(missing_probability=1), 1001, 0)
    assert missing["missing"] and missing["GR"] is None
    with pytest.raises(ValueError, match="maximum must exceed"):
        study.SensorConfig(clip_min_api=90, clip_max_api=80)


def test_policy_boundary_has_no_private_geology_and_fixed_fallback():
    assert set(inspect.signature(study.choose_command).parameters) == {
        "strategy", "station", "observations", "regional", "fresh_usable",
    }
    station = {"inc_deg": 90.0, "tvd_ft": 1450.0, "x_ft": 1000.0}
    regional = {"slope": 0.005, "intercept_ft": 1445.0}
    assert study.choose_command("guided", station, [], regional, fresh_usable=False) == ("HOLD", 90)
    assert study.choose_command("hold", station, [], regional, fresh_usable=True) == ("HOLD", 90)
    with pytest.raises(ValueError, match="Unknown"):
        study.choose_command("oracle", station, [], regional, fresh_usable=True)


def test_delayed_observations_keep_original_pose_and_are_not_repeated(monkeypatch):
    case = study.StudyCase(
        case_id="eval_delayed", label="Delayed", split="evaluation", description="Test",
        geology={"regional_dip": 0.007}, sensor=study.SensorConfig(delay_steps=3),
    )
    seen = []
    original = study.choose_command

    def check(strategy, station, observations, regional, *, fresh_usable):
        step = round((station["md_ft"] - 2000) / 50)
        assert all(item["delivered_step"] <= step for item in observations)
        ids = [item["acquired_step"] for item in observations]
        assert ids == sorted(set(ids))
        if fresh_usable:
            assert observations[-1]["md_ft"] == station["md_ft"] - 150
            seen.append((step, observations[-1]["acquired_step"], observations[-1]["tvd_ft"]))
        return original(strategy, station, observations, regional, fresh_usable=fresh_usable)

    monkeypatch.setattr(study, "choose_command", check)
    trial = study.run_trial(case, 1001, "guided")
    assert all(event["fallback_hold"] for event in trial["decisions"][:3])
    for step, acquired_step, acquisition_tvd in seen:
        assert step - acquired_step == 3
        assert acquisition_tvd == trial["trajectory"][40 + acquired_step]["tvd_ft"]
    assert trial["metrics"]["evaluated_length_ft"] == 5000


def test_saturated_measurements_never_reach_center_inversion(monkeypatch):
    case = study.StudyCase(
        case_id="eval_saturated", label="Saturated", split="evaluation", description="Test",
        geology={"regional_dip": 0.007}, sensor=study.SensorConfig(bias_api=200),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Saturated observation reached the guided inversion")

    monkeypatch.setattr(study, "guided_command", forbidden)
    trial = study.run_trial(case, 1001, "guided")
    assert trial["metrics"]["usable_measurement_count"] == 0
    assert trial["metrics"]["fallback_hold_count"] == 100
    assert trial["metrics"]["saturated_measurement_count"] == 100


def test_trial_reproducibility_and_final_evaluation_only(monkeypatch):
    case = study.load_manifest().cases[2]
    original_evaluate = study.evaluate_trajectory
    calls = []

    def evaluate(path, scenario):
        assert path.md_ft.max() == scenario.max_md_ft
        calls.append(path.md_ft.max())
        return original_evaluate(path, scenario)

    monkeypatch.setattr(study, "evaluate_trajectory", evaluate)
    first = study.run_trial(case, 1001, "guided")
    assert first == study.run_trial(case, 1001, "guided")
    assert len(calls) == 2
    assert first["metrics"]["dls_violation_count"] == 0
    assert len(first["decisions"]) == 100
    assert all(event["delivered"][0]["md_ft"] == event["md_from_ft"] for event in first["decisions"])


def test_aggregation_is_paired_and_rejects_missing_or_duplicate_trials():
    manifest = compact_manifest()
    trials = []
    scores = {"hold": 30.0, "regional_plan": 50.0, "guided": 80.0}
    for case in manifest.cases:
        seed = manifest.development_seeds[0] if case.split == "development" else manifest.evaluation_seeds[0]
        for strategy, score in scores.items():
            trials.append({"case_id": case.case_id, "split": case.split, "seed": seed, "strategy": strategy, "metrics": {
                "percent_in_zone": score, "max_overshoot_ft": 2.0, "dls_violation_count": 0,
                "total_inc_change_deg": 5.0, "fallback_hold_count": 0,
            }})
    summary, paired = study.summarize(manifest, trials)
    assert summary["counts"]["trial_count"] == 6
    assert summary["evaluation"]["mean_percent_in_zone"] == scores
    assert summary["evaluation"]["paired"]["guided_minus_regional_plan_pp"] == {"mean": 30, "min": 30, "max": 30, "wins": 1, "losses": 0, "ties": 0}
    assert len(paired) == 4
    with pytest.raises(ValueError, match="exactly one"):
        study.summarize(manifest, trials[:-1])
    with pytest.raises(ValueError, match="exactly one"):
        study.summarize(manifest, trials + trials[:1])


def test_artifact_freeze_complete_outputs_and_tamper_detection(tmp_path):
    manifest = compact_manifest()
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    out = tmp_path / "study"
    summary = study.run_study(out, path)
    assert study.load_summary(out / "summary.json") == summary
    freeze = json.loads((out / "freeze.json").read_text())
    assert freeze["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    for name, expected in freeze["source_sha256"].items():
        assert hashlib.sha256((out / "frozen_source" / name).read_bytes()).hexdigest() == expected
    with gzip.open(out / "histories.jsonl.gz", "rt", encoding="utf-8") as handle:
        histories = [json.loads(line) for line in handle]
    assert len(histories) == 6
    # Stable gzip header contains neither the output path nor wall-clock mtime.
    header = (out / "histories.jsonl.gz").read_bytes()[:10]
    assert header[3] == 0 and header[4:8] == bytes(4)
    repeated = tmp_path / "repeated"
    study.run_study(repeated, path)
    assert (out / "histories.jsonl.gz").read_bytes() == (repeated / "histories.jsonl.gz").read_bytes()
    assert (out / "frozen_source.zip").read_bytes() == (repeated / "frozen_source.zip").read_bytes()
    assert (out / "robustness_results.png").stat().st_size > 10000
    assert (out / "robustness_worst_case.png").stat().st_size > 10000
    with pytest.raises(ValueError, match="never replaced"):
        study.run_study(out, path)
    (out / "trials.csv").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact changed: trials.csv"):
        study.load_summary(out / "summary.json")


def test_failed_study_is_recorded_and_cannot_be_loaded(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(compact_manifest().model_dump_json(), encoding="utf-8")

    def fail(*args):
        raise RuntimeError("Deliberate test failure")

    monkeypatch.setattr(study, "run_trial", fail)
    out = tmp_path / "study"
    with pytest.raises(RuntimeError, match="Deliberate"):
        study.run_study(out, path)
    failure = json.loads((out / "failure.json").read_text())
    assert failure["completed_trial_count"] == 0
    assert not (out / "artifacts.json").exists()
    with pytest.raises(FileNotFoundError):
        study.load_summary(out / "summary.json")


@pytest.fixture(scope="module")
def verified_evidence(tmp_path_factory):
    root = tmp_path_factory.mktemp("verified-study")
    manifest = root / "manifest.json"
    manifest.write_text(compact_manifest().model_dump_json(), encoding="utf-8")
    out = root / "results"
    study.run_study(out, manifest)
    return out


def rehash(root, name):
    index_path = root / "artifacts.json"
    index = json.loads(index_path.read_text())
    index["sha256"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")


def test_source_archive_is_self_contained_for_installed_evidence(verified_evidence, tmp_path):
    # An installed wheel deliberately includes root artifacts and the archive,
    # without installing archived Python source as importable package modules.
    out = tmp_path / "installed"
    out.mkdir()
    for item in verified_evidence.iterdir():
        if item.is_file():
            shutil.copyfile(item, out / item.name)
    summary = study.load_summary(out / "summary.json")
    assert summary["counts"]["trial_count"] == 6
    with zipfile.ZipFile(out / "frozen_source.zip") as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    (out / "frozen_source.zip").unlink()
    with pytest.raises(FileNotFoundError):
        study.load_summary(out / "summary.json")


@pytest.mark.parametrize("mode", ["changed", "missing"])
def test_expanded_source_must_be_complete_and_unchanged(verified_evidence, tmp_path, mode):
    out = tmp_path / "results"
    shutil.copytree(verified_evidence, out)
    source = out / "frozen_source" / "app" / "study" / "robustness.py"
    if mode == "changed":
        source.write_text("changed source", encoding="utf-8")
        with pytest.raises(ValueError, match="artifact changed: frozen_source"):
            study.load_summary(out / "summary.json")
    else:
        source.unlink()
        with pytest.raises(FileNotFoundError):
            study.load_summary(out / "summary.json")


def test_archive_bytes_and_each_source_are_verified(verified_evidence, tmp_path):
    out = tmp_path / "results"
    shutil.copytree(verified_evidence, out)
    archive_path = out / "frozen_source.zip"
    archive_path.write_bytes(archive_path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="artifact changed: frozen_source.zip"):
        study.load_summary(out / "summary.json")
    # Updating the outer archive checksum still cannot hide altered source.
    with zipfile.ZipFile(verified_evidence / "frozen_source.zip") as archive:
        data = {name: archive.read(name) for name in archive.namelist()}
    data["app/study/robustness.py"] = b"changed source"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in data.items():
            archive.writestr(name, content)
    rehash(out, "frozen_source.zip")
    with pytest.raises(ValueError, match="source archive changed: app/study/robustness.py"):
        study.load_summary(out / "summary.json")


@pytest.mark.parametrize("field", ["manifest_sha256", "source_fingerprint", "study_id", "policy_version"])
def test_summary_metadata_must_agree_with_manifest_and_freeze(verified_evidence, tmp_path, field):
    out = tmp_path / "results"
    shutil.copytree(verified_evidence, out)
    summary_path = out / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary[field] = "changed"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    rehash(out, "summary.json")
    with pytest.raises(ValueError, match="(identity|fingerprint)"):
        study.load_summary(summary_path)


def test_freeze_metadata_and_unsafe_paths_are_rejected(verified_evidence, tmp_path):
    out = tmp_path / "results"
    shutil.copytree(verified_evidence, out)
    freeze_path = out / "freeze.json"
    freeze = json.loads(freeze_path.read_text())
    freeze["source_fingerprint"] = "changed"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    rehash(out, "freeze.json")
    with pytest.raises(ValueError, match="fingerprint"):
        study.load_summary(out / "summary.json")
    artifacts_path = out / "artifacts.json"
    artifacts = json.loads(artifacts_path.read_text())
    artifacts["sha256"]["../outside.txt"] = "not-read"
    artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe study artifact path"):
        study.load_summary(out / "summary.json")


@pytest.mark.parametrize("name", ["../outside.py", "/absolute.py", "C:/absolute.py", "app\\file.py", "app/../file.py", "app//file.py", "."])
def test_evidence_paths_never_escape_their_directory(name):
    with pytest.raises(ValueError, match="Unsafe"):
        study._check_relative_path(name)
