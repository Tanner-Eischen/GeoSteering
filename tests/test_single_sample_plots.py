"""A newly acquired station must remain visible before a line segment exists."""

import pandas as pd
from streamlit.testing.v1 import AppTest

from app.plot.correlation_panel import build_correlation_figure
from app.plot.log_tracks import build_log_tracks_figure


def test_log_tracks_show_single_acquired_sample_and_keep_future_samples_out():
    logs = pd.DataFrame({"md_ft": [2000., 2100.], "GR": [80., 95.], "RES": [10., 12.]})
    figure, metadata = build_log_tracks_figure(logs, curves=["GR", "RES"], depth_min=1999., depth_max=2001.)
    assert metadata.rendered_points == 1
    for trace in figure.data:
        assert "markers" in trace.mode
        assert list(trace.y) == [2000.]


def test_correlation_shows_single_acquired_sample():
    logs = pd.DataFrame({"md_ft": [2000.], "GR": [80.], "RES": [10.]})
    figure = build_correlation_figure({"Active": logs}, curves=["GR", "RES"])
    assert len(figure.data) == 2
    assert all("markers" in trace.mode for trace in figure.data)


def test_viewer_single_acquired_trajectory_point_is_visible(tmp_path, monkeypatch):
    import json

    from app.pages import well_viewer
    from tests.test_run_history import prepare_run

    root, _, _, _ = prepare_run(tmp_path)
    original = well_viewer.load_well_frames

    def single_station(*args, **kwargs):
        frames = original(*args, **kwargs)
        # The standard replay fixture includes its pre-landing trajectory.
        # Represent a well whose acquired support contains just one station.
        return {**frames, "logs": frames["logs"].tail(1),
                "trajectory": frames["trajectory"].tail(1), "markers": []}

    monkeypatch.setattr(well_viewer, "load_well_frames", single_station)
    app = AppTest.from_string(
        f"from app.pages.well_viewer import render\nrender({str(root)!r})", default_timeout=30,
    ).run()
    assert not app.exception
    trajectory = json.loads(app.get("plotly_chart")[1].proto.spec)
    assert "markers" in trajectory["data"][0]["mode"]
