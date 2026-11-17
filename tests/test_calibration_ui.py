"""Versioned calibration presentation and run-integration regressions."""

from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app.io.project_store import atomic_write_json
from app.plot.uncertainty import ensemble_figure
from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.prejob import save_prejob_model
from app.services.runs import fork_run, initialize_run
from app.services.uncertainty import load_uncertainty_snapshot
from app.services.uncertainty_assessment import assess_commands
from app.sim.sim_models import SimulationConfig
from app.sim.sim_store import load_simulation_config
from app.uncertainty.ensemble import initialize_ensemble, summarize_ensemble, target_probability_range
from app.uncertainty.models import CalibrationSettings, EnsembleSettings
from tests.test_run_history import prepare_run


def hashes(root):
    return {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def enabled(root, config, top, base, settings):
    configured = config.model_copy(update={"ensemble_settings": settings})
    state = initialize_run(root, configured, top, base)
    return state.run_id


def test_configuration_roundtrips_explicit_versions_without_retagging_v1():
    common = {"active_well_id": "active", "end_md_ft": 100}
    legacy = SimulationConfig(**common, ensemble_settings={"member_count": 32})
    assert type(legacy.ensemble_settings) is EnsembleSettings
    assert legacy.ensemble_settings.version == "spatial-particle-v1"
    encoded = legacy.model_dump(mode="json")
    assert SimulationConfig.model_validate(encoded).model_dump(mode="json") == encoded
    modern = SimulationConfig(**common, ensemble_settings=CalibrationSettings(member_count=32))
    encoded = modern.model_dump(mode="json")
    decoded = SimulationConfig.model_validate(encoded)
    assert type(decoded.ensemble_settings) is CalibrationSettings
    assert decoded.model_dump(mode="json") == encoded
    assert encoded["ensemble_settings"]["calibration_biases_api"] == [-16, -8, 0, 8, 16]
    with pytest.raises(ValueError):
        SimulationConfig(**common, ensemble_settings={"version": "unknown-v99", "member_count": 32})


def tail_state():
    state = initialize_ensemble(
        [{"x_ft": 0, "tvd_ft": 988}, {"x_ft": 100, "tvd_ft": 988}],
        [{"x_ft": 0, "tvd_ft": 1012}, {"x_ft": 100, "tvd_ft": 1012}],
        0, settings=CalibrationSettings(member_count=32, calibration_biases_api=(-16, 0, 16)), seed=2,
    )
    for component in state["components"]:
        conditional = component["ensemble"]
        for index, member in enumerate(conditional["members"]):
            member["center_tvd_ft"] = (1000 if index == 0 else 1100) + component["bias_api"]
        conditional["weights"] = [0.949, 0.051] + [0.0] * 30
        conditional["ess"] = 1 / (0.949**2 + 0.051**2)
    state["ess"] = min(component["ensemble"]["ess"] for component in state["components"])
    return state


def test_v2_current_cards_use_exact_conditional_tails_and_distinguish_mixture():
    state = tail_state()
    snapshot = {"ensemble": state, "step_index": 0, "observation_status": "updated", "measurement": None}
    exact = summarize_ensemble(state)
    low, high = target_probability_range(exact, 0, 1000)
    app = AppTest.from_string(f'''
import pandas as pd
from app.pages.uncertainty import render_snapshot
render_snapshot({snapshot!r}, pd.DataFrame({{'md_ft':[2000.0], 'x_ft':[0.0], 'tvd_ft':[1000.0]}}), compact=True)
''', default_timeout=30).run()
    assert not app.exception
    assert [metric.label for metric in app.metric] == [
        "Calibration envelope width", "Minimum effective models", "Target probability range",
    ]
    assert app.metric[0].value == "132.00 ft"
    assert app.metric[2].value == f"{100 * low:.1f}–{100 * high:.1f}%"
    assert any("Assumed-mixture summary" in caption.value for caption in app.caption)
    assert any("not itself a 90% confidence interval" in caption.value for caption in app.caption)
    assert any("cannot identify the true bias" in caption.value for caption in app.caption)


def test_v2_plot_keeps_calibration_envelope_separate_from_mixture_band():
    summary = summarize_ensemble(tail_state())
    figure = ensemble_figure(summary, pd.DataFrame())
    names = [trace.name for trace in figure.data]
    assert "Calibration envelope · center" in names
    assert "Assumed-mixture 90% interval" in names
    assert "90% model interval · center" not in names
    envelope = next(trace for trace in figure.data if trace.name == "Calibration envelope · center")
    mixture = next(trace for trace in figure.data if trace.name == "Assumed-mixture 90% interval")
    assert list(envelope.y) == summary["calibration_envelope"]["center"]["q95"]
    assert list(mixture.y) == summary["center"]["q95"]


def test_v2_command_ranges_share_forecast_and_do_not_read_truth(tmp_path, monkeypatch):
    root, config, top, base = prepare_run(tmp_path, "causal")
    run_id = enabled(root, config, top, base, CalibrationSettings(member_count=32))
    before = hashes(root)
    from app.sim import environment
    monkeypatch.setattr(environment, "load_private_scenario", lambda *a: pytest.fail("Private truth read"))
    monkeypatch.setattr(environment, "sample_station", lambda *a: pytest.fail("Future log sampled"))
    result = assess_commands(root, run_id, 0)
    assert result == assess_commands(root, run_id, 0)
    assert result["forecast"]["calibration_biases_api"] == [-16, -8, 0, 8, 16]
    for row in result["actions"]:
        lower = row["Min conditional probability (%)"]
        upper = row["Max conditional probability (%)"]
        pooled = row["Assumed-mixture probability in target (%)"]
        assert 0 <= lower <= pooled + 1e-9 <= upper + 1e-9 <= 100 + 1e-9
        assert row["Calibration envelope width (ft)"] + 1e-9 >= row["Mixture center interval width (ft)"]
        assert "Model probability in target (%)" not in row
        assert row["Next x (ft)"] in result["forecast"]["x_ft"]
    assert hashes(root) == before


def test_v2_initialize_advance_fork_retry_preserve_saved_v1_bytes(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    old_id = enabled(root, config, top, base, EnsembleSettings(member_count=32))
    old_scope = root / "runs" / old_id
    old_bytes = hashes(old_scope)
    old_snapshot = load_uncertainty_snapshot(root, old_id)
    modern_id = enabled(root, config, top, base, CalibrationSettings(member_count=32))
    snapshot = load_uncertainty_snapshot(root, modern_id)
    assert snapshot["ensemble"]["version"] == "spatial-calibration-state-v2"
    assert "members" not in snapshot["ensemble"] and "weights" not in snapshot["ensemble"]
    assert [component["weight"] for component in snapshot["ensemble"]["components"]] == [0.2] * 5
    serialized = load_simulation_config(root, modern_id).model_dump(mode="json")
    assert SimulationConfig.model_validate(serialized).model_dump(mode="json") == serialized
    parent_before = hashes(root / "runs" / modern_id)
    child = fork_run(root, modern_id)
    assert load_uncertainty_snapshot(root, child.run_id) == snapshot
    view = load_operator_view(root, child.run_id)
    form = {"run_id": child.run_id, "expected_step_index": 0,
            "interpretation_version_id": view["interpretation"].version_id,
            "action": "HOLD", "observations": "Current acquired signal supports HOLD across the declared bias hypotheses"}
    result = submit_steering(root, **form)
    after = hashes(root)
    assert submit_steering(root, **form) == result
    assert hashes(root) == after
    assert load_uncertainty_snapshot(root, child.run_id)["step_index"] == 1
    assert hashes(root / "runs" / modern_id) == parent_before
    assert load_uncertainty_snapshot(root, old_id) == old_snapshot
    assert hashes(old_scope) == old_bytes
    assert old_snapshot["ensemble"]["version"] == "spatial-particle-state-v1"


def test_new_run_ui_defaults_to_v2_when_enabled_and_keeps_legacy_option(tmp_path):
    root, config, _, _ = prepare_run(tmp_path)
    save_prejob_model(root, config.offset_well_ids, active_well_id=config.active_well_id)
    atomic_write_json(root / "manifest.json", {"scenario_version": "structural_dip_01-v1", "seed": 123,
                                               "lateral_start_md_ft": 2000})
    app = AppTest.from_string(f'''
from app.pages.steering_console import render
render({str(root)!r})
''', default_timeout=30).run()
    assert not app.exception
    checkbox = next(widget for widget in app.checkbox if widget.label == "Enable uncertainty ensemble · synthetic GR calibration")
    checkbox.check().run()
    assert not app.exception
    version = next(widget for widget in app.selectbox if widget.label == "Uncertainty model")
    assert version.value == "Calibration uncertainty (v2)"
    assert "Known calibration (legacy v1)" in version.options
    next(button for button in app.button if button.label == "Initialize new run").click().run()
    assert not app.exception
    saved = load_simulation_config(root)
    assert isinstance(saved.ensemble_settings, CalibrationSettings)
    assert saved.ensemble_settings.version == "spatial-calibration-v2"
    assert saved.ensemble_settings.calibration_biases_api == (-16, -8, 0, 8, 16)
    assert any(metric.label == "Target probability range" for metric in app.metric)
    json.dumps(load_uncertainty_snapshot(root, saved.run_id), allow_nan=False)
