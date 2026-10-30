from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd

GR_ALIASES = {"GR", "GAM", "GRC", "SGR", "GRMA", "CGR", "ECGR", "GRD"}
RES_ALIASES = {"RES", "RT", "ILD", "RDEP", "AT90", "RESD", "RT_ARC", "RLA1", "RLA2", "RLA3", "RLA4", "RLA5"}


@dataclass(frozen=True)
class CanonicalCurve:
    canonical_name: str
    source_column: str


def canonical_name(mnemonic: str) -> str | None:
    m = mnemonic.strip().upper()
    if m in GR_ALIASES:
        return "GR"
    if m in RES_ALIASES:
        return "RES"
    return None


def normalize_curve_table(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, list[str]]]:
    if "md_ft" not in df.columns:
        raise ValueError("LAS table must contain md_ft column.")

    alias_map: Dict[str, list[str]] = {}
    out = pd.DataFrame({"md_ft": df["md_ft"]})

    for col in df.columns:
        if col == "md_ft":
            continue
        c_name = canonical_name(col)
        if c_name is None:
            continue
        alias_map.setdefault(c_name, []).append(col)
        # Keep first match for deterministic behavior.
        if c_name not in out.columns:
            out[c_name] = pd.to_numeric(df[col], errors="coerce")

    return out, alias_map
