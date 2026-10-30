from __future__ import annotations

from html import escape
from typing import Sequence

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


def _apply_plotly_theme() -> None:
    if "geosteering_theme" in pio.templates:
        pio.templates.default = "geosteering_theme"
        return

    layout = go.Layout(
        font={"family": "IBM Plex Sans", "color": "#16323f", "size": 13},
        paper_bgcolor="rgba(255,255,255,0.92)",
        plot_bgcolor="rgba(248,251,252,1.0)",
        colorway=["#0f766e", "#b45309", "#1d4ed8", "#be123c", "#0e7490"],
        legend={"orientation": "h", "y": 1.02, "x": 0.0},
        margin={"l": 30, "r": 20, "t": 40, "b": 30},
    )
    template = go.layout.Template(layout=layout)
    template.layout.xaxis = {"gridcolor": "#dce6ea", "zeroline": False}
    template.layout.yaxis = {"gridcolor": "#dce6ea", "zeroline": False}
    pio.templates["geosteering_theme"] = template
    pio.templates.default = "geosteering_theme"


def apply_theme() -> None:
    _apply_plotly_theme()
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --gs-ink: #14303d;
  --gs-muted: #5f7280;
  --gs-surface: rgba(255, 255, 255, 0.84);
  --gs-surface-strong: #ffffff;
  --gs-accent: #0f766e;
  --gs-accent-soft: #dff5f2;
  --gs-warn: #b45309;
  --gs-danger: #be123c;
  --gs-border: #d7e3e8;
  --gs-header-offset: 3.25rem;
}

html, body, [class*="stApp"] {
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  color: var(--gs-ink);
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1200px 600px at 95% -5%, #d8edf5 0%, rgba(216, 237, 245, 0) 60%),
    radial-gradient(900px 500px at -10% 105%, #f9e9d6 0%, rgba(249, 233, 214, 0) 55%),
    linear-gradient(180deg, #f6fbfd 0%, #eef5f8 100%);
  padding-top: var(--gs-header-offset);
}

.block-container {
  padding-top: 0;
  padding-bottom: 2rem;
}

header[data-testid="stHeader"] {
  background: rgba(246, 251, 253, 0.92);
  height: var(--gs-header-offset);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 999;
  backdrop-filter: blur(6px);
}

div[data-testid="stToolbar"] {
  top: 0.4rem;
  right: 0.6rem;
}

section.main {
  padding-top: 0;
}

section[data-testid="stSidebar"] {
  padding-top: var(--gs-header-offset);
}

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #17344a 0%, #1f475d 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.12);
}

section[data-testid="stSidebar"] * {
  color: #eef7fb !important;
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: #deecf3 !important;
}

h1, h2, h3 {
  letter-spacing: -0.01em;
  color: var(--gs-ink);
}

.gs-hero {
  background: linear-gradient(125deg, #ffffff 0%, #f2faf8 52%, #f8efe4 100%);
  border: 1px solid var(--gs-border);
  border-radius: 18px;
  padding: 1rem 1.2rem;
  box-shadow: 0 10px 30px rgba(15, 42, 54, 0.08);
  margin-bottom: 1rem;
  animation: gsFadeUp .45s ease-out both;
}

.gs-hero-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--gs-ink);
}

.gs-hero-subtitle {
  margin: 0.3rem 0 0.75rem 0;
  color: var(--gs-muted);
  font-size: 0.96rem;
}

.gs-chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.gs-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid #cde4ea;
  background: #f7fcfd;
  color: #1d4050;
  font-size: 0.78rem;
  padding: 0.2rem 0.6rem;
}

[data-testid="stMetric"] {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: 14px;
  padding: 0.5rem 0.8rem;
}

[data-testid="stDataFrame"] {
  border: 1px solid var(--gs-border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--gs-surface-strong);
}

.stButton > button {
  border-radius: 10px;
  border: 1px solid #0b5f59;
  background: linear-gradient(180deg, #0f766e 0%, #0e625b 100%);
  color: #f8fffe;
  font-weight: 600;
}

.stButton > button:hover {
  border-color: #0f766e;
  background: linear-gradient(180deg, #11867d 0%, #0f766e 100%);
}

code, pre, kbd {
  font-family: "IBM Plex Mono", monospace !important;
}

@keyframes gsFadeUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .gs-hero { padding: 0.9rem 0.9rem; }
  .gs-hero-title { font-size: 1.15rem; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str | None = None, chips: Sequence[str] | None = None) -> None:
    safe_title = escape(title)
    safe_subtitle = escape(subtitle or "")
    chips_markup = "".join(f'<span class="gs-chip">{escape(c)}</span>' for c in (chips or []))
    st.markdown(
        f"""
<div class="gs-hero">
  <p class="gs-hero-title">{safe_title}</p>
  <p class="gs-hero-subtitle">{safe_subtitle}</p>
  <div class="gs-chip-wrap">{chips_markup}</div>
</div>
        """,
        unsafe_allow_html=True,
    )
