from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


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
            fig.add_trace(go.Scatter(x=window["md_ft"], y=window[curve], mode="lines", name=curve))
    fig.add_vline(x=revealed_md_ft, line_dash="dash", line_color="#c62828")
    fig.update_layout(height=280, xaxis_title="MD (ft)", yaxis_title="Curve value", title="Active well window")
    return fig


def build_offset_comparison_figure(
    offset_logs: Mapping[str, pd.DataFrame],
    revealed_md_ft: float,
    window_size_ft: float,
    curve: str = "GR",
) -> go.Figure:
    fig = go.Figure()
    md_min = revealed_md_ft - window_size_ft
    md_max = revealed_md_ft
    for name, logs in offset_logs.items():
        if curve not in logs.columns:
            continue
        window = logs[(logs["md_ft"] >= md_min) & (logs["md_ft"] <= md_max)]
        fig.add_trace(go.Scatter(x=window["md_ft"], y=window[curve], mode="lines", name=name))
    fig.update_layout(height=280, xaxis_title="MD (ft)", yaxis_title=curve, title=f"Offsets ({curve})")
    return fig


def build_interpretation_overlay_figure(
    trajectory_df: pd.DataFrame,
    md_grid: np.ndarray,
    top_tvd: np.ndarray,
    base_tvd: np.ndarray,
) -> go.Figure:
    well_tvd = np.interp(md_grid, trajectory_df["md_ft"], trajectory_df["tvd_ft"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=md_grid, y=well_tvd, mode="lines", name="Well TVD", line={"color": "#1e88e5"}))
    fig.add_trace(go.Scatter(x=md_grid, y=top_tvd, mode="lines", name="Top TVD", line={"color": "#2e7d32"}))
    fig.add_trace(go.Scatter(x=md_grid, y=base_tvd, mode="lines", name="Base TVD", line={"color": "#ef6c00"}))
    fig.update_layout(height=320, xaxis_title="MD (ft)", yaxis_title="TVD (ft)", title="Interpretation Overlay")
    return fig


def build_kpi_trend_figure(step_index: Sequence[int], percent_in_zone: Sequence[float]) -> go.Figure:
    fig = go.Figure(
        data=[go.Scatter(x=list(step_index), y=list(percent_in_zone), mode="lines+markers", name="% In Zone")]
    )
    fig.update_layout(height=260, xaxis_title="Step", yaxis_title="% In Zone", title="KPI Trend")
    return fig

