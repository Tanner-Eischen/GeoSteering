from streamlit.testing.v1 import AppTest

from app.study.calibration_sensitivity import load_calibration_summary


def test_evidence_switches_scoring_phase_and_preserves_original_failure():
    summary = load_calibration_summary()
    app = AppTest.from_string("from app.pages.uncertainty import _calibration; _calibration()",
                              default_timeout=30).run()
    assert not app.exception
    assert app.radio[0].value == "Persistent calibration sensitivity"
    assert app.metric[0].value == f"{summary['evaluation']['intervals']['v1_nominal']['phases']['posterior_current']['mean_coverage_pct']:.1f}%"
    assert any("not fresh validation" in caption.value and "2.97%" in caption.value for caption in app.caption)
    assert any("no nominal coverage guarantee" in item.value for item in app.markdown)
    assert list(app.dataframe[0].value.columns) == ["Range", "Coverage (%)", "Width (ft)"]
    outside = next(case for case in summary["case_results"] if case["case_id"] == "eval_outside_support")
    app.selectbox[1].set_value(outside).run()
    assert not app.exception
    assert app.dataframe[0].value["Coverage (%)"].tolist() == [0, 0, 0]
    assert any("0/101 stations" in item.value for item in app.warning)
    app.selectbox[0].set_value("forecast_500").run()
    assert not app.exception
    assert app.metric[2].value == f"{summary['evaluation']['intervals']['v2_envelope']['phases']['forecast_500']['mean_coverage_pct']:.1f}%"
    app.radio[0].set_value("Original known-calibration study").run()
    assert not app.exception
    assert app.metric[1].value == "70.9%"
    assert any("2.97%" in item.value for item in app.warning)
