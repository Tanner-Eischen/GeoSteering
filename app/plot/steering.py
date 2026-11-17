from __future__ import annotations

from typing import Sequence

import pandas as pd
import plotly.graph_objects as go

from app.alg.interpretation_model import evaluate_piecewise_linear


def build_active_window_figure(
    logs_df: pd.DataFrame,
    revealed_md_ft: float,
    window_size_ft: float,
    curves: Sequence[str],
) -> go.Figure:
    md_min = max(float(logs_df["md_ft"].min()), revealed_md_ft - window_size_ft)
    md_max = revealed_md_ft
    window = logs_df[(logs_df["md_ft"] >= md_min) & (logs_df["md_ft"] <= md_max)]

    fig = go.Figure()
    for curve in curves:
        if curve in window.columns:
            fig.add_trace(go.Scatter(x=window["md_ft"], y=window[curve],
                                    mode="lines+markers" if len(window) == 1 else "lines", name=curve))
    fig.add_vline(x=revealed_md_ft, line_dash="dash", line_color="#c62828")
    fig.update_layout(height=280, xaxis_title="MD (ft)", yaxis_title="Curve value", title="Active well window")
    return fig


def build_kpi_trend_figure(step_index: Sequence[int], percent_in_zone: Sequence[float]) -> go.Figure:
    fig = go.Figure(
        data=[go.Scatter(x=list(step_index), y=list(percent_in_zone), mode="lines+markers", name="% In Zone")]
    )
    fig.update_layout(height=260, xaxis_title="Step", yaxis_title="% In Zone", title="KPI Trend")
    return fig


def build_command_preview_figure(trajectory, preview, interpretation) -> go.Figure:
    """Acquired path and geometric projection, with estimated geology only."""
    previous, station = preview["previous"], preview["station"]
    window = trajectory.loc[trajectory.md_ft >= previous["md_ft"] - 250]
    xcol = "x_ft" if "x_ft" in window else "east_ft"
    domain = [float(window[xcol].min()) - 5, station["x_ft"] + 10]
    fig = go.Figure()
    for points, name, color in (
        (interpretation.top_control_points, "Estimated top", "#729a83"),
        (interpretation.base_control_points, "Estimated base", "#729a83"),
    ):
        knots = sorted({*domain, *(float(point.x_ft) for point in points if domain[0] <= point.x_ft <= domain[-1])})
        fig.add_trace(go.Scatter(x=knots, y=evaluate_piecewise_linear(points, knots),
                                 name=name, line={"color": color, "width": 1.5}))
    fig.add_trace(go.Scatter(x=window[xcol], y=window.tvd_ft, mode="lines+markers",
                             name="Acquired path", line={"color": "#234b65", "width": 3}))
    fig.add_trace(go.Scatter(x=[previous["x_ft"], station["x_ft"]],
                             y=[previous["tvd_ft"], station["tvd_ft"]], mode="lines+markers",
                             name="Next station projection", line={"color": "#b45309", "width": 3, "dash": "dash"}))
    fig.update_layout(height=400, margin={"l": 55, "r": 25, "t": 85, "b": 55},
                      legend={"orientation": "h", "y": 1.02, "x": 0, "yanchor": "bottom"},
                      xaxis_title="Along-section x (ft)")
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(autorange="reversed", title_text="TVD (ft), positive down", automargin=True)
    return fig

