from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

CURVE_COLORS = {"GR": "#1565c0", "RES": "#f57f17"}


def build_correlation_figure(
    logs_by_well: Mapping[str, pd.DataFrame],
    markers_by_well: Mapping[str, Sequence[dict]] | None = None,
    curves: Sequence[str] | None = None,
    depth_min: float | None = None,
    depth_max: float | None = None,
    display_shifts_ft: Mapping[str, float] | None = None,
    x_range: tuple[float, float] | None = None,
    x_ranges: Mapping[str, tuple[float, float]] | None = None,
    exclude_outliers: bool = False,
    normalize_curves: bool = False,
    curve_colors: Mapping[str, str] | None = None,
) -> go.Figure:
    well_names = list(logs_by_well.keys())
    if not well_names:
        fig = go.Figure()
        fig.update_layout(title="No wells selected")
        return fig

    selected_curves = list(curves or ["GR", "RES"])
    shifts = display_shifts_ft or {}
    markers_by_well = markers_by_well or {}
    x_ranges = x_ranges or {}
    curve_colors = curve_colors or CURVE_COLORS
    per_curve_axis_range: tuple[float, float] | None = None
    if not normalize_curves and x_range is None and x_ranges:
        lows: list[float] = []
        highs: list[float] = []
        for curve in selected_curves:
            range_tuple = x_ranges.get(curve)
            if not range_tuple:
                continue
            low, high = float(range_tuple[0]), float(range_tuple[1])
            if np.isfinite(low) and np.isfinite(high) and high > low:
                lows.append(low)
                highs.append(high)
        if lows and highs:
            per_curve_axis_range = (float(min(lows)), float(max(highs)))

    fig = make_subplots(rows=1, cols=len(well_names), shared_yaxes=True, subplot_titles=well_names)
    legend_seen: set[str] = set()
    for i, well_name in enumerate(well_names, start=1):
        df = logs_by_well[well_name].copy().sort_values("md_ft")
        if depth_min is not None:
            df = df[df["md_ft"] >= float(depth_min)]
        if depth_max is not None:
            df = df[df["md_ft"] <= float(depth_max)]
        shift = float(shifts.get(well_name, 0.0))
        y = df["md_ft"] + shift

        for curve in selected_curves:
            if curve not in df.columns:
                continue
            series = pd.to_numeric(df[curve], errors="coerce")
            x = series.copy()
            range_tuple = x_ranges.get(curve)
            if not normalize_curves and x_range is not None:
                range_tuple = x_range

            if range_tuple:
                low, high = range_tuple
                should_clip = exclude_outliers or (not normalize_curves and x_range is None and curve in x_ranges)
                if should_clip:
                    mask = (x < low) | (x > high)
                    x[mask] = np.nan
                if normalize_curves and high > low:
                    if not should_clip:
                        x = x.clip(lower=low, upper=high)
                    x = (x - low) / (high - low)
            elif normalize_curves:
                finite = x.dropna()
                if not finite.empty:
                    low = float(finite.min())
                    high = float(finite.max())
                    if high > low:
                        x = (x - low) / (high - low)

            color = curve_colors.get(curve)
            showlegend = curve not in legend_seen
            if showlegend:
                legend_seen.add(curve)
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=curve,
                    legendgroup=curve,
                    showlegend=showlegend,
                    line={"color": color} if color else None,
                ),
                row=1,
                col=i,
            )

        for marker in markers_by_well.get(well_name, []):
            y_val = float(marker["md_ft"]) + shift
            fig.add_hline(
                y=y_val,
                line_dash="dot",
                line_color="#9e9e9e",
                row=1,
                col=i,
                annotation_text=str(marker.get("name", "")),
                annotation_position="top left",
            )

        title_curves = "/".join([c for c in selected_curves if c in df.columns])
        if normalize_curves:
            fig.update_xaxes(title_text=f"Normalized {title_curves}", range=[0, 1], row=1, col=i)
        elif x_range:
            fig.update_xaxes(title_text=title_curves, range=[x_range[0], x_range[1]], row=1, col=i)
        elif per_curve_axis_range:
            fig.update_xaxes(
                title_text=title_curves,
                range=[per_curve_axis_range[0], per_curve_axis_range[1]],
                row=1,
                col=i,
            )
        else:
            fig.update_xaxes(title_text=title_curves, row=1, col=i)

    fig.update_yaxes(autorange="reversed", title_text="MD (ft)")
    fig.update_layout(height=780, margin={"l": 32, "r": 16, "t": 64, "b": 32}, legend_title_text="Curves")
    return fig
