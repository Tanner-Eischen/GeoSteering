from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from app.io.project_store import append_only_write, read_json
from app.model.schemas import DecisionEntry, Recommendation
from app.services.interpretations import get_interpretation_by_id
from app.services.run_paths import run_root
from app.services.run_transactions import recover_run


def _path(project_root: str | Path, run_id: str | None = None) -> Path:
    return run_root(project_root, run_id) / "decisions" / "decisions.json"


def load_decisions(project_root: str | Path, run_id: str | None = None) -> list[DecisionEntry]:
    recover_run(run_root(project_root, run_id))
    rows = read_json(_path(project_root, run_id), default=[])
    entries = [DecisionEntry.model_validate(r) for r in rows]
    return sorted(entries, key=lambda d: (d.step_index, d.created_at))


def _save_decisions(project_root: str | Path, decisions: Sequence[DecisionEntry]) -> None:
    ordered = sorted(decisions, key=lambda d: (d.step_index, d.created_at))
    append_only_write(
        _path(project_root),
        [d.model_dump(mode="json") for d in ordered],
        key_fields=["decision_id"],
    )


def create_decision(
    project_root: str | Path,
    step_index: int,
    md_from_ft: float,
    md_to_ft: float,
    interpretation_version_id: str,
    observations: str,
    action: str,
    target_inc_deg: float | None = None,
    target_azi_deg: float | None = None,
    risk_note: str | None = None,
) -> DecisionEntry:
    # Ensure traceability to an existing interpretation version.
    get_interpretation_by_id(project_root, interpretation_version_id)

    decision = DecisionEntry(
        step_index=step_index,
        md_from_ft=md_from_ft,
        md_to_ft=md_to_ft,
        interpretation_version_id=interpretation_version_id,
        observations=observations,
        recommendation=Recommendation(
            action=action,
            target_inc_deg=target_inc_deg,
            target_azi_deg=target_azi_deg,
        ),
        risk_note=risk_note,
    )
    decisions = load_decisions(project_root)
    decisions.append(decision)
    _save_decisions(project_root, decisions)
    return decision


def export_decision_log_csv(
    project_root: str | Path,
    out_csv: str | Path,
    *,
    revealed_md_ft: float | None = None,
    curves_used: Sequence[str] | None = None,
    offsets_used: Sequence[str] | None = None,
    interpretation_delta_summary: str = "",
) -> Path:
    rows = []
    for d in load_decisions(project_root):
        rows.append(
            {
                "step_index": d.step_index,
                "md_from_ft": d.md_from_ft,
                "md_to_ft": d.md_to_ft,
                "revealed_md_ft": d.md_from_ft,
                "curves_used": ",".join(curves_used or []),
                "offsets_used": ",".join(offsets_used or []),
                "interpretation_version_id": d.interpretation_version_id,
                "interpretation_delta_summary": interpretation_delta_summary,
                "recommendation_action": d.recommendation.action,
                "target_inc_deg": d.recommendation.target_inc_deg,
                "target_azi_deg": d.recommendation.target_azi_deg,
                "observations": d.observations,
                "risk_note": d.risk_note,
                "created_at": d.created_at.isoformat(),
            }
        )

    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path

