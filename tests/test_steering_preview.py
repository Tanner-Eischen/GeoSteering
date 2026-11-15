from __future__ import annotations

import pytest

from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.runs import active_run_id, initialize_run
from app.services.steering_preview import preview_command
from app.sim import environment
from tests.test_run_history import prepare_run


def snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize(("action", "target"), [("HOLD", None), ("BUILD", 180), ("DROP", 0)])
def test_preview_matches_actual_step_without_sampling_or_writing(tmp_path, monkeypatch, action, target):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    view = load_operator_view(root, run_id)
    before = snapshot(root)
    with monkeypatch.context() as patch:
        patch.setattr(environment, "sample_station", lambda *a, **kw: pytest.fail("Preview sampled a future log"))
        patch.setattr(environment, "load_private_scenario", lambda *a, **kw: pytest.fail("Preview loaded private truth"))
        preview = preview_command(root, run_id=run_id, expected_step_index=0, action=action, target_inc_deg=target)
    assert snapshot(root) == before
    submit_steering(root, run_id=run_id, expected_step_index=0,
                    interpretation_version_id=view["interpretation"].version_id,
                    action=action, observations="Current acquired signal supports command", target_inc_deg=target)
    after = load_operator_view(root, run_id)
    for key, value in preview["station"].items():
        assert after["frames"]["trajectory"].iloc[-1][key] == pytest.approx(value)
    response = after["metrics"][-1]["command_response"]
    for key in ("effective_inc_deg", "requested_inc_deg", "clipped", "limit_reason"):
        assert preview[key] == response[key]


def test_preview_short_final_step_and_explicit_selected_run(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    selected = initialize_run(root, config.model_copy(update={"end_md_ft": 2025.0}), top, base)
    initialize_run(root, config, top, base)
    preview = preview_command(root, run_id=selected.run_id, expected_step_index=0, action="BUILD", target_inc_deg=180)
    assert preview["md_to_ft"] == 2025
    assert preview["effective_inc_deg"] == pytest.approx(90.75)
    before = snapshot(root)
    for step, action, target in [(1, "HOLD", None), (False, "HOLD", None), (0, "DROP", 100)]:
        with pytest.raises(ValueError):
            preview_command(root, run_id=selected.run_id, expected_step_index=step, action=action, target_inc_deg=target)
    assert snapshot(root) == before


def test_replay_preview_never_reads_future_trajectory(tmp_path, monkeypatch):
    root, _, _, _ = prepare_run(tmp_path)
    run_id = active_run_id(root)
    from app.services import steering_preview
    original = steering_preview.load_operator_view

    def acquired_only(*args):
        view = original(*args)
        assert view["frames"]["trajectory"].md_ft.max() == 2000
        return view

    monkeypatch.setattr(steering_preview, "load_operator_view", acquired_only)
    before = snapshot(root)
    preview = preview_command(root, run_id=run_id, expected_step_index=0, action="BUILD")
    assert preview["mode"] == "replay" and "station" not in preview
    assert preview["md_to_ft"] == 2100
    assert snapshot(root) == before


def test_legacy_causal_run_without_public_mechanics_has_actionable_message(tmp_path):
    from app.io.project_store import atomic_write_json, read_json

    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    (root / "runs" / run_id / "environment" / "mechanics.json").unlink()
    provenance_path = root / "runs" / run_id / "environment" / "provenance.json"
    provenance = read_json(provenance_path)
    provenance.pop("mechanics_sha256")
    atomic_write_json(provenance_path, provenance)
    before = snapshot(root)
    with pytest.raises(ValueError, match="Start a new causal run"):
        preview_command(root, run_id=run_id, expected_step_index=0, action="HOLD")
    assert snapshot(root) == before


def test_preview_rejects_changed_public_mechanics(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    path = root / "runs" / run_id / "environment" / "mechanics.json"
    path.write_text(path.read_text().replace("3.0", "1.0"))
    before = snapshot(root)
    with pytest.raises(ValueError, match="mechanical limits changed"):
        preview_command(root, run_id=run_id, expected_step_index=0, action="BUILD")
    assert snapshot(root) == before


def test_preview_plot_preserves_interior_interpretation_knots(tmp_path):
    from app.model.schemas import ControlPoint
    from app.plot.steering import build_command_preview_figure

    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    view = load_operator_view(root, run_id)
    preview = preview_command(root, run_id=run_id, expected_step_index=0, action="HOLD")
    x = preview["previous"]["x_ft"]
    revised = view["interpretation"].model_copy(update={"top_control_points": [
        ControlPoint(md_ft=0, x_ft=0, tvd_ft=1400),
        ControlPoint(md_ft=x, x_ft=x, tvd_ft=1430),
        ControlPoint(md_ft=x + 1000, x_ft=x + 1000, tvd_ft=1400),
    ]})
    fig = build_command_preview_figure(view["frames"]["trajectory"], preview, revised)
    top = fig.data[0]
    assert x in top.x
    assert top.y[list(top.x).index(x)] == 1430
