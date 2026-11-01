from __future__ import annotations

from typing import Sequence

import pandas as pd
import plotly.graph_objects as go


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

