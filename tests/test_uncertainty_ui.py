import hashlib

from streamlit.testing.v1 import AppTest

from app.services.operator_workflow import load_operator_view, submit_steering
from app.services.runs import initialize_run
from app.services.uncertainty_assessment import assess_commands
from app.uncertainty.models import EnsembleSettings
from tests.test_run_history import prepare_run


def enabled_run(tmp_path):
    root, config, top, base = prepare_run(tmp_path, "causal")
    config = config.model_copy(update={"ensemble_settings": EnsembleSettings(member_count=32)})
    state = initialize_run(root, config, top, base)
    return root, state.run_id


def hashes(root):
    return {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_command_probabilities_are_bounded_shared_and_read_only(tmp_path, monkeypatch):
    root, run_id = enabled_run(tmp_path)
    before = hashes(root)
    from app.sim import environment
    monkeypatch.setattr(environment, "load_private_scenario", lambda *a: (_ for _ in ()).throw(AssertionError("Private truth read")))
    monkeypatch.setattr(environment, "sample_station", lambda *a: (_ for _ in ()).throw(AssertionError("Future measurement sampled")))
    result = assess_commands(root, run_id, 0)
    assert result == assess_commands(root, run_id, 0)
    assert {row["Action"] for row in result["actions"]} == {"HOLD", "BUILD", "DROP"}
    assert all(0 <= row["Model probability in target (%)"] <= 100 for row in result["actions"])
    assert all(row["DLS (°/100 ft)"] <= 3 + 1e-8 for row in result["actions"])
    assert all(row["Next x (ft)"] in result["forecast"]["x_ft"] for row in result["actions"])
    assert hashes(root) == before


def page(root, run_id, monkeypatch):
    from app.pages import uncertainty
    monkeypatch.setattr(uncertainty, "_calibration", lambda: None)
    return AppTest.from_string(f'''
import streamlit as st
from app.ui.workspace import remember_selected_run
from app.pages.uncertainty import render
remember_selected_run(st.session_state, {str(root)!r}, {run_id!r})
render({str(root)!r})
''', default_timeout=20).run()


def test_uncertainty_page_current_and_historical_states(tmp_path, monkeypatch):
    root, run_id = enabled_run(tmp_path)
    view = load_operator_view(root, run_id)
    submit_steering(root, run_id=run_id, expected_step_index=0,
                    interpretation_version_id=view["interpretation"].version_id,
                    action="HOLD", observations="Current GR supports the command")
    before = hashes(root)
    app = page(root, run_id, monkeypatch)
    assert not app.exception
    assert any(metric.label == "Effective model count" for metric in app.metric)
    assert len(app.dataframe[0].value) == 3
    app.selectbox[1].set_value(0).run()
    assert not app.exception
    assert any("Select the latest acquired step" in item.value for item in app.info)
    assert any("MD 2,000.0" in item.value for item in app.caption)
    assert hashes(root) == before


def test_old_run_remains_unmodified_and_offers_explicit_opt_in(tmp_path, monkeypatch):
    root, _, _, _ = prepare_run(tmp_path)
    from app.services.runs import active_run_id
    before = hashes(root)
    app = page(root, active_run_id(root), monkeypatch)
    assert not app.exception
    assert any("no ensemble" in item.value for item in app.info)
    assert hashes(root) == before


def test_current_cards_keep_exact_posterior_tail_mass():
    from app.uncertainty.ensemble import initialize_ensemble
    state = initialize_ensemble([{"x_ft": 0, "tvd_ft": 988}, {"x_ft": 100, "tvd_ft": 988}],
                                [{"x_ft": 0, "tvd_ft": 1012}, {"x_ft": 100, "tvd_ft": 1012}],
                                0, settings=EnsembleSettings(member_count=32), seed=2)
    for index, member in enumerate(state["members"]):
        member["center_tvd_ft"] = 1000 if index == 0 else 1100
    state["weights"] = [0.949, 0.051] + [0.0] * 30
    state["ess"] = 1 / (0.949**2 + 0.051**2)
    snapshot = {"ensemble": state, "step_index": 0, "observation_status": "updated", "measurement": None}
    app = AppTest.from_string(f'''
import pandas as pd
from app.pages.uncertainty import render_snapshot
render_snapshot({snapshot!r}, pd.DataFrame({{'md_ft':[2000.0], 'x_ft':[0.0], 'tvd_ft':[1000.0]}}), compact=True)
''', default_timeout=15).run()
    assert not app.exception
    assert app.metric[0].value == "100.00 ft"
    assert app.metric[2].value == "94.9%"
