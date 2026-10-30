from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


@dataclass
class LogTrackMetadata:
    clipped_res_count: int
    rendered_points: int
    excluded_by_curve: dict[str, int]


def _depth_window(df: pd.DataFrame, depth_min: float | None, depth_max: float | None) -> pd.DataFrame:
    out = df.copy()
    if depth_min is not None:
        out = out[out["md_ft"] >= float(depth_min)]
    if depth_max is not None:
        out = out[out["md_ft"] <= float(depth_max)]
    return out.sort_values("md_ft").reset_index(drop=True)


def _decimate(df: pd.DataFrame, max_points: int = 3000) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    stride = int(np.ceil(len(df) / max_points))
    return df.iloc[::stride].reset_index(drop=True)


def build_log_tracks_figure(
    logs_df: pd.DataFrame,
    markers: Sequence[dict] | None = None,
    curves: Sequence[str] | None = None,
    depth_min: float | None = None,
    depth_max: float | None = None,
    max_points: int = 3000,
    bit_md_ft: float | None = None,
    x_ranges: dict[str, tuple[float, float]] | None = None,
    exclude_outliers: bool = False,
) -> tuple[go.Figure, LogTrackMetadata]:
    if "md_ft" not in logs_df.columns:
        raise ValueError("logs_df must include md_ft")
    selected_curves = list(curves or ["GR", "RES"])
    selected_curves = [c for c in selected_curves if c in logs_df.columns]

    if not selected_curves:
        fig = go.Figure()
        fig.update_layout(title="No selected curves available", height=700)
        return fig, LogTrackMetadata(clipped_res_count=0, rendered_points=0, excluded_by_curve={})

    df = _depth_window(logs_df, depth_min=depth_min, depth_max=depth_max)
    df = _decimate(df, max_points=max_points)
    md = df["md_ft"]

    fig = make_subplots(rows=1, cols=len(selected_curves), shared_yaxes=True, subplot_titles=selected_curves)
    clipped_count = 0
    excluded_by_curve: dict[str, int] = {}
    ranges = x_ranges or {}

    for i, curve in enumerate(selected_curves, start=1):
        series = pd.to_numeric(df[curve], errors="coerce")
        x = series.copy()
        range_tuple = ranges.get(curve)
        if curve.upper() == "RES":
            clipped = x <= 0
            clipped_count = int(clipped.fillna(False).sum())
            x[clipped] = np.nan
            if range_tuple and exclude_outliers:
                low, high = range_tuple
                mask = (x < low) | (x > high)
                excluded_by_curve[curve] = int(mask.fillna(False).sum())
                x[mask] = np.nan
            fig.add_trace(go.Scatter(x=x, y=md, mode="lines", name="RES", line={"color": "#f57f17"}), row=1, col=i)
            if range_tuple:
                low, high = range_tuple
                if low > 0 and high > low:
                    fig.update_xaxes(type="log", range=[np.log10(low), np.log10(high)], title_text="RES (log)", row=1, col=i)
                else:
                    fig.update_xaxes(type="log", title_text="RES (log)", row=1, col=i)
            else:
                fig.update_xaxes(type="log", title_text="RES (log)", row=1, col=i)
        else:
            if range_tuple and exclude_outliers:
                low, high = range_tuple
                mask = (x < low) | (x > high)
                excluded_by_curve[curve] = int(mask.fillna(False).sum())
                x[mask] = np.nan
            fig.add_trace(
                go.Scatter(x=x, y=md, mode="lines", name=curve, line={"color": "#1565c0"}),
                row=1,
                col=i,
            )
            if range_tuple and range_tuple[1] > range_tuple[0]:
                fig.update_xaxes(range=[range_tuple[0], range_tuple[1]], title_text=curve, row=1, col=i)
            else:
                fig.update_xaxes(title_text=curve, row=1, col=i)

        if markers:
            for marker in markers:
                md_marker = float(marker["md_ft"])
                fig.add_hline(
                    y=md_marker,
                    line_dash="dot",
                    line_color="#9e9e9e",
                    row=1,
                    col=i,
                    annotation_text=str(marker.get("name", "")),
                    annotation_position="top left",
                )

        if bit_md_ft is not None:
            fig.add_hline(y=float(bit_md_ft), line_dash="dash", line_color="#c62828", row=1, col=i)

    fig.update_yaxes(autorange="reversed", title_text="MD (ft)")
    fig.update_layout(height=760, legend_orientation="h", margin={"l": 32, "r": 24, "t": 60, "b": 32})
    return fig, LogTrackMetadata(
        clipped_res_count=clipped_count,
        rendered_points=len(df),
        excluded_by_curve=excluded_by_curve,
    )
