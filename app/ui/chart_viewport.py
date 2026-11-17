"""Opt-in viewport continuity across Streamlit's Plotly element replacements.

Streamlit 1.66 hashes the figure into its element ID even with a user key.
Use Plotly's public event/relayout API to carry only axis viewport state across
those replacements. State is browser-memory-only and scoped to a chart/context.
"""
from __future__ import annotations

import json
from hashlib import sha256

import streamlit as st

_SCRIPT = r"""<script>
(() => {
  const config = __CONFIG__;
  const registry = window.__geoSteeringChartViewports ||= new Map();
  let entry = registry.get(config.key);
  if (!entry) {
    entry = {context: config.context, viewport: null, graph: null, listener: null,
             observer: null, frame: null, restoring: false};
    registry.set(config.key, entry);
  }
  const detach = () => {
    if (entry.graph && entry.listener) {
      entry.graph.removeListener?.("plotly_relayout", entry.listener);
    }
    entry.graph = null;
    entry.listener = null;
    entry.restoring = false;
  };
  if (entry.context !== config.context) {
    detach();
    entry.context = config.context;
    entry.viewport = null;
  }
  entry.observer?.disconnect();
  if (entry.frame !== null) cancelAnimationFrame(entry.frame);
  entry.frame = null;

  const attach = () => {
    entry.frame = null;
    const container = document.querySelector(config.selector);
    if (!container) {
      detach();
      entry.observer?.disconnect();
      return;
    }
    const graph = container.querySelector(".js-plotly-plot");
    const readiness = [Boolean(graph), typeof graph?.on === "function",
      Boolean(graph?.layout), graph?.layout?.uirevision === config.context,
      Boolean(window.Plotly?.relayout)];
    if (!readiness.every(Boolean)) return;
    if (entry.graph === graph) return;
    detach();
    entry.graph = graph;
    entry.listener = (event) => {
      if (entry.graph !== graph || entry.context !== config.context ||
          !graph.isConnected || entry.restoring) return;
      if (!Object.keys(event || {}).some(key => /^(xaxis\d*|yaxis\d*)\.(range(?:\[\d+\])?|autorange)$/.test(key))) return;
      const viewport = {...(entry.viewport || {})};
      for (const [attribute, value] of Object.entries(event || {})) {
        const match = /^(xaxis\d*|yaxis\d*)\.(range(?:\[(\d+)\])?|autorange)$/.exec(attribute);
        if (!match) continue;
        const axis = match[1];
        const rangeKey = axis + ".range";
        const autoKey = axis + ".autorange";
        if (match[2] === "autorange") {
          viewport[autoKey] = value;
          if (value !== false) delete viewport[rangeKey];
        } else if (match[3] !== undefined) {
          const range = [...(viewport[rangeKey] || graph.layout[axis]?.range || [])];
          range[Number(match[3])] = value;
          if (range.length === 2 && range.every(item => item !== undefined)) viewport[rangeKey] = range;
          viewport[autoKey] = false;
        } else if (Array.isArray(value) && value.length === 2) {
          viewport[rangeKey] = [...value];
          viewport[autoKey] = false;
        }
      }
      entry.viewport = viewport;
    };
    graph.on("plotly_relayout", entry.listener);
    if (entry.viewport && Object.keys(entry.viewport).length) {
      entry.restoring = true;
      Promise.resolve().then(() => {
        if (entry.graph === graph && entry.context === config.context && graph.isConnected) {
          return window.Plotly.relayout(graph, entry.viewport);
        }
      }).catch(() => {
        // A replacement may be purged while an earlier restore is in flight.
      }).finally(() => {
        if (entry.graph === graph && entry.context === config.context) entry.restoring = false;
      });
    }
  };
  const schedule = () => {
    if (entry.frame === null) entry.frame = requestAnimationFrame(attach);
  };
  entry.observer = new MutationObserver(schedule);
  entry.observer.observe(document.getElementById("stMain") || document.body, {
    childList: true, subtree: true,
  });
  schedule();
})();
</script>"""


def viewport_container_key(key: str) -> str:
    return "chart_viewport_" + sha256(key.encode("utf-8")).hexdigest()[:16]


def viewport_script(key: str, context: str) -> str:
    config = {
        "key": key,
        "context": context,
        "selector": ".st-key-" + viewport_container_key(key),
    }
    # Escape HTML delimiters as well as JS strings: a user-derived context must
    # never be able to close the script element or insert executable markup.
    payload = json.dumps(config, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _SCRIPT.replace("__CONFIG__", payload)


def preserve_chart_viewport(key: str, context: str) -> None:
    st.html(viewport_script(key, context), unsafe_allow_javascript=True)
