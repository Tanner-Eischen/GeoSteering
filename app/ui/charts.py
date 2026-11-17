"""Consistent chart navigation without trapping page scrolling."""
from __future__ import annotations

from hashlib import sha256

import plotly.graph_objects as go
import streamlit as st

from app.ui.chart_viewport import preserve_chart_viewport, viewport_container_key


def chart_config(*, wheel_zoom: bool = False) -> dict:
    return {
        "scrollZoom": wheel_zoom,
        "displayModeBar": True,
        "displaylogo": False,
        "responsive": True,
        "doubleClick": "reset",
    }


def _interaction_controls(key: str, *, compact: bool) -> tuple[str, bool, int]:
    mode_col, wheel_col, reset_col = (st, st, st) if compact else st.columns([2, 2, 1])
    mode = mode_col.radio("Drag to", ["Pan", "Box zoom"], horizontal=True, key=f"{key}_drag")
    wheel_zoom = wheel_col.checkbox(
        "Wheel zoom", value=False, key=f"{key}_wheel",
        help="Off by default so the mouse wheel scrolls the page while over the chart.",
    )
    reset_key = f"{key}_reset_count"
    if reset_col.button("Reset view", key=f"{key}_reset", width="stretch"):
        st.session_state[reset_key] = st.session_state.get(reset_key, 0) + 1
    return mode, wheel_zoom, st.session_state.get(reset_key, 0)


def render_chart(
    fig: go.Figure, *, key: str, help_text: str | None = None, compact: bool = False,
    view_revision: str | None = None,
) -> None:
    """Render a chart; an explicit view revision preserves zoom across figure edits.

    Callers supplying a revision must change it when wells, ranges, or other
    display context changes. Reset view always restores the supplied ranges.
    """
    guidance = help_text or "Drag to move or zoom. Reset view restores the displayed range. Use the chart toolbar to save an image."
    if compact:
        with st.popover("Chart controls"):
            mode, wheel_zoom, reset_count = _interaction_controls(key, compact=True)
            st.caption(guidance)
    else:
        mode, wheel_zoom, reset_count = _interaction_controls(key, compact=False)
    revision = view_revision if view_revision is not None else sha256(fig.to_json().encode("utf-8")).hexdigest()
    fig.update_layout(
        dragmode="pan" if mode == "Pan" else "zoom",
        uirevision=f"{revision}:{reset_count}",
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    if not compact:
        st.caption(guidance)
    if view_revision is not None:
        with st.container(key=viewport_container_key(key)):
            preserve_chart_viewport(key, f"{revision}:{reset_count}")
            st.plotly_chart(
                fig, width="stretch", key=f"{key}_plot_{reset_count}",
                config=chart_config(wheel_zoom=wheel_zoom),
            )
    else:
        st.plotly_chart(
            fig, width="stretch", key=f"{key}_plot_{reset_count}",
            config=chart_config(wheel_zoom=wheel_zoom),
        )
