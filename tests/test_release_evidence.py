from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.io.project_store import atomic_write_json, read_json
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import load_simulation_config, save_simulation_config
from tools.release_provenance import describe_code, write_manifest
from tools.release_verify import independent_references, verify_project
from tools.run_case_study import run_case_study


def test_packaged_provenance_without_git_and_corruption(tmp_path):
    for package in ("app", "tools"):
        (tmp_path / package).mkdir()
        (tmp_path / package / "__init__.py").write_text('"""Fixture."""\n', encoding="utf8")
    frozen = write_manifest(tmp_path)
    result = describe_code(tmp_path)
    assert result["basis"] == "verified_packaged_source_manifest"
    assert result["runtime_git_revision"] is None
    assert result["dirty_working_tree"] is None
    assert result["source_fingerprint"] == frozen["source_fingerprint"]
    (tmp_path / "app/__init__.py").write_text("# changed\n", encoding="utf8")
    with pytest.raises(ValueError, match="bytes changed"):
        describe_code(tmp_path)


def test_absent_git_has_unknown_not_true_dirty_flag(tmp_path):
    for package in ("app", "tools"):
        (tmp_path / package).mkdir()
    result = describe_code(tmp_path)
    assert result["code_revision"] == "unavailable"
    assert result["dirty_working_tree"] is None


def test_portable_truth_config_and_legacy_path_rebinding(tmp_path):
    scope = tmp_path / "runs/test-run"
    truth = scope / "environment/truth.json"
    truth.parent.mkdir(parents=True)
    truth.write_text("{}", encoding="utf8")
    config = SimulationConfig(
        run_id="test-run", active_well_id="active", end_md_ft=100.0, hidden_truth_path=str(truth.resolve())
    )
    save_simulation_config(scope, config)
    raw = read_json(scope / "simulations/simulation_config.json")
    assert raw["hidden_truth_path"] == "environment/truth.json"
    assert Path(load_simulation_config(scope).hidden_truth_path) == truth.resolve()
    raw["hidden_truth_path"] = "C:/old/copied/project/runs/test-run/environment/truth.json"
    atomic_write_json(scope / "simulations/simulation_config.json", raw)
    assert Path(load_simulation_config(scope).hidden_truth_path) == truth.resolve()
    raw["hidden_truth_path"] = "../../outside.json"
    atomic_write_json(scope / "simulations/simulation_config.json", raw)
    with pytest.raises(ValueError, match="inside its run"):
        load_simulation_config(scope)


def test_independent_analytic_references():
    result = independent_references()
    assert result["max_position_error_ft"] < 1e-8
    assert result["tiny_actual_dls_deg_per_100ft"] == pytest.approx(1e-7, rel=1e-12)


@pytest.fixture(scope="module")
def canonical(tmp_path_factory):
    root = tmp_path_factory.mktemp("release-verifier")
    run_case_study(root)
    return root / "project"


def test_current_release_gate_and_relocated_project(canonical, tmp_path):
    first = verify_project(canonical)
    destination = tmp_path / "relocated"
    shutil.copytree(canonical, destination)
    second = verify_project(destination)
    assert first == second
    config = load_simulation_config(destination)
    assert Path(config.hidden_truth_path).is_relative_to(destination)


@pytest.mark.parametrize(
    "relative",
    ["exports/summary.json", "exports/kpi_summary.json", "exports/decision_log.csv", "exports/plan_demo.csv"],
)
def test_export_mutants_are_rejected(canonical, relative):
    path = canonical / relative
    original = path.read_bytes()
    try:
        if path.suffix == ".json":
            payload = json.loads(original)
            if path.name == "summary.json":
                payload["causal_comparison"]["guided"]["percent_in_zone"] = 99.0
            else:
                payload["percent_in_zone"] = -10.0
            path.write_text(json.dumps(payload), encoding="utf8")
        else:
            lines = original.decode().splitlines()
            cells = lines[1].split(",")
            cells[0] = "99999"
            lines[1] = ",".join(cells)
            path.write_text("\n".join(lines) + "\n", encoding="utf8")
        with pytest.raises(ValueError):
            verify_project(canonical)
    finally:
        path.write_bytes(original)
