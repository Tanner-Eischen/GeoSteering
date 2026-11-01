from __future__ import annotations

import numpy as np
import pandas as pd

from app.plot.log_tracks import build_log_tracks_figure
from app.plot.steering import build_active_window_figure


def _logs_df() -> pd.DataFrame:
    md = np.linspace(1000.0, 2000.0, 500)
    return pd.DataFrame(
        {
            "md_ft": md,
            "GR": 80.0 + 5.0 * np.sin(md / 50.0),
            "RES": 10.0 + 1.0 * np.cos(md / 60.0),
        }
    )


def test_missing_curve_degrades_gracefully() -> None:
    logs = _logs_df().drop(columns=["RES"])
    fig, meta = build_log_tracks_figure(logs_df=logs, curves=["GR", "RES"])
    assert fig is not None
    assert meta.rendered_points > 0


def test_marker_out_of_range_does_not_crash() -> None:
    logs = _logs_df()
    markers = [{"name": "Too Deep", "md_ft": 5000.0}]
    fig, _ = build_log_tracks_figure(logs_df=logs, markers=markers, curves=["GR", "RES"])
    assert fig is not None


def test_window_render_small_and_large() -> None:
    logs = _logs_df()
    fig_small, meta_small = build_log_tracks_figure(logs_df=logs, depth_min=1200.0, depth_max=1300.0, curves=["GR", "RES"])
    fig_large, meta_large = build_log_tracks_figure(logs_df=logs, depth_min=1000.0, depth_max=2000.0, curves=["GR", "RES"])

    assert fig_small is not None
    assert fig_large is not None
    assert meta_large.rendered_points >= meta_small.rendered_points


def test_single_acquired_reading_is_visible_and_excludes_future_data():
    logs = pd.DataFrame({"md_ft": [2000.0, 4000.0, 6000.0], "GR": [80.0, 35.0, 999999.0]})
    figure = build_active_window_figure(logs, 4000.0, 500.0, ["GR"])
    assert list(figure.data[0].x) == [4000.0]
    assert list(figure.data[0].y) == [35.0]
    assert "markers" in figure.data[0].mode

