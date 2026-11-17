from __future__ import annotations

from html import escape
from typing import Sequence

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


def _apply_plotly_theme() -> None:
    if "geosteering_theme" not in pio.templates:
        layout = go.Layout(
            font={"family": "Segoe UI, Arial, sans-serif", "color": "#16323f", "size": 13},
            paper_bgcolor="#ffffff", plot_bgcolor="#f8fbfc",
            colorway=["#0f766e", "#b45309", "#1d4ed8", "#be123c", "#0e7490"],
            legend={"orientation": "h", "y": 1.02, "x": 0.0},
            margin={"l": 55, "r": 25, "t": 60, "b": 60},
        )
        template = go.layout.Template(layout=layout)
        template.layout.xaxis = {"gridcolor": "#dce6ea", "zeroline": False, "automargin": True}
        template.layout.yaxis = {"gridcolor": "#dce6ea", "zeroline": False, "automargin": True}
        pio.templates["geosteering_theme"] = template
    pio.templates.default = "geosteering_theme"


def apply_theme() -> None:
    _apply_plotly_theme()
    # Leave header positioning and scroll containers to Streamlit. In particular,
    # do not clip the dataframe wrapper: it contains its own scrollbars/toolbars.
    st.markdown(
        """
<style>
:root {
  --gs-border: color-mix(in srgb, currentColor 20%, transparent);
}
html, body, [class*="stApp"] {
  font-family: "Segoe UI", Arial, sans-serif;
}
.block-container {
  padding-top: 4.5rem;
  padding-left: 2rem;
  padding-right: 2rem;
  padding-bottom: 4rem;
  max-width: 1600px;
}
[data-testid="stMain"] { container-type: inline-size; }
[data-testid="stSidebar"] {
  border-right: 1px solid var(--gs-border);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding: 0.25rem 0; }
[data-testid="stColumn"] { min-width: 0; }
button:focus-visible, input:focus-visible, textarea:focus-visible, [role="tab"]:focus-visible {
  outline: 3px solid #b45309 !important;
  outline-offset: 3px;
}
h1, h2, h3 { letter-spacing: -0.015em; }
.gs-project-context {
  color: inherit;
  font-size: 0.875rem;
  padding-bottom: 0.7rem;
  overflow-wrap: anywhere;
}
.gs-hero {
  border-bottom: 1px solid var(--gs-border);
  padding: 0 0 0.9rem;
  margin-bottom: 0.75rem;
  overflow-wrap: anywhere;
}
.gs-hero h1.gs-hero-title {
  margin: 0;
  padding: 0;
  font-size: 1.7rem;
  font-weight: 650;
  color: inherit;
}
.gs-hero-subtitle { margin: 0.35rem 0 0; color: inherit; }
.gs-chip-wrap { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.5rem; }
.gs-chip {
  border: 1px solid var(--gs-border);
  border-radius: 6px;
  padding: 0.2rem 0.55rem;
  font-size: 0.8rem;
}
[data-testid="stMetric"] {
  border: 1px solid var(--gs-border);
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  min-width: 0;
}
[data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"] > div {
  white-space: normal;
  overflow-wrap: anywhere;
  text-overflow: clip;
}
[data-testid="stMetricValue"] { font-size: clamp(1.25rem, 2.4vw, 2rem); }
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button { border-radius: 7px; min-height: 2.6rem; }
[data-testid="stButton"] button p,
[data-testid="stDownloadButton"] button p { white-space: normal; overflow-wrap: anywhere; }
/* Keep workspace charts alongside longer editing forms without nested scrolling. */
@container (min-width: 601px) {
  .st-key-steering_workspace [data-testid="stColumn"]:has(.st-key-steering_charts),
  .st-key-corr_workspace [data-testid="stColumn"]:has(.st-key-corr_charts),
  .st-key-planning_workspace [data-testid="stColumn"]:has(.st-key-planning_charts) {
    position: sticky;
    top: 4rem;
    align-self: flex-start;
  }
}
/* Respond to usable content width, including when the sidebar is open. */
@container (max-width: 900px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 260px;
    min-width: min(260px, 100%);
    width: auto;
  }
}
@container (max-width: 600px) {
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 100%;
    min-width: 0;
  }
}
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .gs-hero h1.gs-hero-title { font-size: 1.35rem; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str | None = None, chips: Sequence[str] | None = None) -> None:
    chips_markup = "".join(f'<span class="gs-chip">{escape(c)}</span>' for c in (chips or []))
    st.markdown(
        f'<div class="gs-hero"><h1 class="gs-hero-title">{escape(title)}</h1>'
        f'<p class="gs-hero-subtitle">{escape(subtitle or "")}</p>'
        f'<div class="gs-chip-wrap">{chips_markup}</div></div>',
        unsafe_allow_html=True,
    )
