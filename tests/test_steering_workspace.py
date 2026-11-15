"""Streamlit component checks for command state and legacy run compatibility."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.io.project_store import atomic_write_json, read_json
from app.services.operator_workflow import load_operator_view
from app.services.runs import active_run_id
from tests.test_run_history import prepare_run


def workspace(root, run_id):
    return AppTest.from_string(f'''
from pathlib import Path
from app.services.operator_workflow import load_operator_view
from app.pages.steering_console import _command_workspace
root = Path({str(root)!r})
view = load_operator_view(root, {run_id!r})
_command_workspace(root, view['config'], view['state'], view['interpretation'], view['frames']['trajectory'])
''', default_timeout=15).run()


def test_target_and_evidence_survive_command_toggles(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    app = workspace(root, run_id)
    assert not app.exception
    app.radio[0].set_value("BUILD").run()
    app.checkbox[0].check().run()
    app.number_input[0].set_value(93).run()
    app.text_area[0].set_value("Observed landing signal supports a bounded command").run()
    app.radio[0].set_value("HOLD").run()
    assert app.number_input[0].value == 93 and app.number_input[0].disabled
    app.radio[0].set_value("BUILD").run()
    assert app.number_input[0].value == 93 and not app.number_input[0].disabled
    assert app.text_area[0].value == "Observed landing signal supports a bounded command"
    assert not app.exception
    assert load_operator_view(root, run_id)["state"].step_index == 0


def test_legacy_causal_run_can_advance_without_preview(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    (Path(root) / "runs" / run_id / "environment" / "mechanics.json").unlink()
    provenance_path = Path(root) / "runs" / run_id / "environment" / "provenance.json"
    provenance = read_json(provenance_path)
    provenance.pop("mechanics_sha256")
    atomic_write_json(provenance_path, provenance)
    app = workspace(root, run_id)
    assert not app.exception
    assert any("older run" in warning.value for warning in app.warning)
    assert not app.button[0].disabled
    app.text_area[0].set_value("Acquired logs support HOLD in this saved run").run()
    app.button[0].click().run()
    assert not app.exception
    assert load_operator_view(root, run_id)["state"].step_index == 1


def test_changed_mechanics_disable_advance_instead_of_legacy_fallback(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    path = Path(root) / "runs" / run_id / "environment" / "mechanics.json"
    path.write_text(path.read_text().replace("3.0", "1.0"))
    app = workspace(root, run_id)
    assert not app.exception
    assert app.button[0].disabled
    assert any("mechanical limits changed" in error.value for error in app.error)


def test_missing_mechanics_in_modern_run_disable_advance(tmp_path):
    root, _, _, _ = prepare_run(tmp_path, "causal")
    run_id = active_run_id(root)
    (Path(root) / "runs" / run_id / "environment" / "mechanics.json").unlink()
    app = workspace(root, run_id)
    assert not app.exception
    assert app.button[0].disabled
    assert any("mechanical limits are missing" in error.value for error in app.error)
