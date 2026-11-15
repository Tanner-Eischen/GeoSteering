"""One explicit offset interpretation remains the same through planning and runs."""

from __future__ import annotations

import json

import pytest

from app.io.project_store import read_json
from app.model.schemas import PrejobModel
from app.plan.plan_generator import plan_to_target
from app.plan.plan_store import load_plan, save_plan
from app.services.interpretations import get_latest_interpretation
from app.services.markers import load_markers, save_markers
from app.services.prejob import list_prejob_models, load_prejob_model, save_prejob_model, validate_prejob_model
from app.services.run_paths import run_root
from app.services.runs import fork_run, initialize_run
from app.sim.sim_store import load_simulation_config
from tests.test_run_history import prepare_run


@pytest.fixture
def workspace(tmp_path):
    root, config, _, _ = prepare_run(tmp_path)
    return root, config


def changed_picks(root, well_id):
    markers = load_markers(root, well_id)
    save_markers(root, well_id, [marker.model_copy(update={"md_ft": marker.md_ft + 3}) for marker in markers])


def bound_plan(root, model):
    interpretation = model.interpretation
    parameters, generated = plan_to_target(
        interpretation.top_control_points, interpretation.base_control_points,
        kickoff_md_ft=500, lateral_length_ft=5000, dls_max_deg_per_100ft=6,
    )
    return save_plan(root, "Selected geology", parameters, generated.stations, 6, generated.exceedances,
                     geological_model=model)


def bound_run(root, config, model, plan_id=None, **updates):
    config = config.model_copy(update={"geological_model": model, "plan_id": plan_id,
                                       "offset_well_ids": model.offset_well_ids, **updates})
    interpretation = model.interpretation
    return initialize_run(root, config, interpretation.top_control_points, interpretation.base_control_points,
                          interpretation.uncertainty.band_tvd_ft)


def test_selected_subset_and_older_version_remain_exact_through_plan_and_run(workspace):
    root, config = workspace
    # Make the third offset materially different. A silent all-offset refit
    # would change the selected two-offset model and be caught here.
    changed_picks(root, config.offset_well_ids[-1])
    chosen = save_prejob_model(root, config.offset_well_ids[:2])
    latest = save_prejob_model(root, config.offset_well_ids)
    assert chosen.interpretation.top_control_points != latest.interpretation.top_control_points
    assert list_prejob_models(root)[0] == latest
    plan = bound_plan(root, load_prejob_model(root, chosen.interpretation.version_id))
    saved_plan, _ = load_plan(root, plan.plan_id)
    assert saved_plan.geological_model == chosen
    state = bound_run(root, config, chosen, plan.plan_id)
    captured = load_simulation_config(root, state.run_id)
    baseline = get_latest_interpretation(root, state.run_id)
    assert captured.geological_model == chosen
    assert captured.offset_well_ids == chosen.offset_well_ids
    assert baseline.top_control_points == chosen.interpretation.top_control_points
    manifest = read_json(run_root(root, state.run_id) / "manifest.json")
    assert manifest["geological_model"]["model_sha256"] == chosen.model_sha256
    assert manifest["geological_model"]["evidence_hashes"] == chosen.input_hashes


def test_changed_source_blocks_new_work_but_keeps_saved_plan_and_run(workspace):
    root, config = workspace
    model = save_prejob_model(root, config.offset_well_ids[:2])
    plan = bound_plan(root, model)
    state = bound_run(root, config, model, plan.plan_id)
    scope = run_root(root, state.run_id)
    before = {path.relative_to(scope): path.read_bytes() for path in scope.rglob("*") if path.is_file()}
    changed_picks(root, model.offset_well_ids[0])
    with pytest.raises(ValueError, match="evidence changed"):
        validate_prejob_model(root, model)
    with pytest.raises(ValueError, match="evidence changed"):
        bound_plan(root, model)
    with pytest.raises(ValueError, match="evidence changed"):
        bound_run(root, config, model, plan.plan_id)
    assert load_plan(root, plan.plan_id)[0].geological_model == model
    assert load_simulation_config(root, state.run_id).geological_model == model
    assert before == {path.relative_to(scope): path.read_bytes() for path in scope.rglob("*") if path.is_file()}
    refreshed = save_prejob_model(root, model.offset_well_ids)
    assert refreshed.model_sha256 != model.model_sha256
    assert load_prejob_model(root, model.interpretation.version_id) == model


def test_plan_and_run_must_use_same_model(workspace):
    root, config = workspace
    first = save_prejob_model(root, config.offset_well_ids[:2])
    second = save_prejob_model(root, config.offset_well_ids)
    plan = bound_plan(root, first)
    with pytest.raises(ValueError, match="different geological interpretations"):
        bound_run(root, config, second, plan.plan_id)


@pytest.mark.parametrize("mismatch", ["active", "offset", "bounds", "uncertainty"])
def test_run_rejects_incompatible_evidence_and_boundaries_before_writes(workspace, mismatch):
    root, config = workspace
    model = save_prejob_model(root, config.offset_well_ids[:2])
    controls = model.interpretation
    config = config.model_copy(update={"geological_model": model, "offset_well_ids": model.offset_well_ids})
    top, base = controls.top_control_points, controls.base_control_points
    uncertainty = controls.uncertainty.band_tvd_ft
    if mismatch == "active":
        config = config.model_copy(update={"active_well_id": model.offset_well_ids[0]})
    elif mismatch == "offset":
        config = config.model_copy(update={"offset_well_ids": config.offset_well_ids[1:]})
    elif mismatch == "bounds":
        top = [point.model_copy(update={"tvd_ft": point.tvd_ft + 1}) for point in top]
    else:
        uncertainty += 1
    before = set((root / "runs").iterdir())
    with pytest.raises(ValueError):
        initialize_run(root, config, top, base, uncertainty)
    assert set((root / "runs").iterdir()) == before


def test_model_hash_detects_altered_snapshot(workspace):
    root, config = workspace
    model = save_prejob_model(root, config.offset_well_ids)
    payload = json.loads(model.model_dump_json())
    payload["interpretation"]["top_control_points"][0]["tvd_ft"] += 5
    with pytest.raises(ValueError, match="does not match its hash"):
        PrejobModel.model_validate(payload)


def test_plan_model_is_adopted_when_config_does_not_repeat_snapshot(workspace):
    root, config = workspace
    model = save_prejob_model(root, config.offset_well_ids)
    plan = bound_plan(root, model)
    interpretation = model.interpretation
    state = initialize_run(root, config.model_copy(update={"plan_id": plan.plan_id}),
                           interpretation.top_control_points, interpretation.base_control_points,
                           interpretation.uncertainty.band_tvd_ft)
    assert load_simulation_config(root, state.run_id).geological_model == model


def test_fork_keeps_model_evidence_without_consulting_changed_project(workspace):
    root, config = workspace
    model = save_prejob_model(root, config.offset_well_ids)
    original = bound_run(root, config, model)
    changed_picks(root, model.offset_well_ids[0])
    forked = fork_run(root, original.run_id)
    assert load_simulation_config(root, forked.run_id).geological_model == model
    assert (run_root(root, forked.run_id) / "inputs/geological_model.json").read_bytes() == (
        run_root(root, original.run_id) / "inputs/geological_model.json").read_bytes()


def test_legacy_explicit_controls_remain_supported(workspace):
    root, config = workspace
    model = save_prejob_model(root, config.offset_well_ids)
    controls = model.interpretation
    state = initialize_run(root, config, controls.top_control_points, controls.base_control_points)
    assert load_simulation_config(root, state.run_id).geological_model is None
