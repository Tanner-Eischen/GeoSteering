"""Read-only next-command geometry using acquired stations and public mechanics."""

from __future__ import annotations

import hashlib
import math

from app.io.project_store import read_json
from app.model.schemas import Recommendation
from app.services.operator_workflow import load_operator_view
from app.services.run_paths import run_root
from app.services.run_transactions import run_access_lock
from app.sim.engine import step_forward
from app.sim.trajectory_response import advance_station


class PreviewUnavailable(ValueError):
    """A legacy run can advance, but lacks public constraints for a preview."""


def preview_command(project_root, *, run_id, expected_step_index, action, target_inc_deg=None):
    """Preview exactly one bounded geometric step; do not reveal or write data.

    Legacy causal runs without a public mechanics snapshot must be reinitialized
    to preview. Reading private scenario settings here would break information
    isolation even if a caller only intended to extract a mechanical limit.
    """
    Recommendation(action=action, target_inc_deg=target_inc_deg)
    with run_access_lock(run_root(project_root, run_id)):
        view = load_operator_view(project_root, run_id)
        config, state = view["config"], view["state"]
        if type(expected_step_index) is not int or expected_step_index != state.step_index:
            raise ValueError("The selected run has advanced. Review the current step before previewing.")
        if state.complete:
            raise ValueError("The selected run is complete.")
        next_state = step_forward(state, config)
        if config.mode == "replay":
            return {"mode": "replay", "md_from_ft": state.revealed_md_ft,
                    "md_to_ft": next_state.revealed_md_ft, "action": action,
                    "message": "This recommendation is recorded; the acquired path follows the fixed record."}
        mechanics_path = view["scope"] / "environment" / "mechanics.json"
        provenance = read_json(view["scope"] / "environment" / "provenance.json", default={})
        if not mechanics_path.is_file():
            if provenance.get("mechanics_sha256"):
                raise ValueError("The captured mechanical limits are missing. Reopen an intact run or start a new one.")
            raise PreviewUnavailable("This older run has no public mechanics snapshot. Start a new causal run to preview commands.")
        mechanics = read_json(mechanics_path)
        limit = mechanics.get("max_dls_deg_per_100ft")
        if not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit <= 0:
            raise ValueError("The captured mechanical limits are invalid. Reopen an intact run or start a new one.")
        expected = provenance.get("mechanics_sha256")
        actual = hashlib.sha256((view["scope"] / "environment" / "mechanics.json").read_bytes()).hexdigest()
        if expected != actual:
            raise ValueError("The captured mechanical limits changed. Reopen an intact run or start a new one.")
        frames = view["frames"]
        previous = frames["trajectory"].iloc[-1].to_dict()
        if abs(previous["md_ft"] - state.revealed_md_ft) > 1e-8:
            raise ValueError("The latest acquired station does not match the displayed run depth.")
        station, response = advance_station(
            previous, action, next_state.revealed_md_ft - previous["md_ft"],
            float(limit), target_inc_deg,
        )
        return {"mode": "causal", "run_id": run_id, "step_index": state.step_index,
                "md_from_ft": previous["md_ft"], "md_to_ft": station["md_ft"],
                "current_inc_deg": previous["inc_deg"], "previous": previous,
                "station": station, "max_dls_deg_per_100ft": limit, **response}
