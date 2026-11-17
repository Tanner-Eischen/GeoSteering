"""Compare bounded commands under one acquired-data geological forecast."""

import numpy as np

from app.services.operator_workflow import load_operator_view
from app.services.run_paths import run_root
from app.services.run_transactions import run_access_lock
from app.services.steering_preview import preview_command
from app.uncertainty.ensemble import forecast_ensemble, target_probability, target_probability_range


def assess_commands(project_root, run_id, expected_step_index):
    with run_access_lock(run_root(project_root, run_id)):
        view = load_operator_view(project_root, run_id)
        if view["state"].step_index != expected_step_index:
            raise ValueError("The run advanced. Review its current ensemble before comparing commands.")
        snapshot = view.get("uncertainty")
        if snapshot is None:
            raise ValueError("Start a new run with the uncertainty ensemble enabled.")
        if view["config"].mode != "causal" or view["state"].complete:
            raise ValueError("Command assessment requires an unfinished causal run.")
        previews = [preview_command(project_root, run_id=run_id, expected_step_index=expected_step_index, action=action)
                    for action in ("HOLD", "BUILD", "DROP")]
        state = snapshot["ensemble"]
        positions = [preview["station"]["x_ft"] for preview in previews]
        if max(positions) > state["x_ft"] + 500:
            raise ValueError("The next interval exceeds the 500-ft forecast horizon from the last filtered position. Use a shorter reveal interval or acquire a new located measurement.")
        grid = sorted({state["x_ft"], *positions})
        # One fixed-lattice geological sample is shared across all alternatives.
        forecast = forecast_ensemble(state, grid)
        rows = []
        for preview in previews:
            station = preview["station"]
            index = grid.index(station["x_ft"])
            probability = 100 * target_probability(forecast, index, station["tvd_ft"])
            width = forecast["center"]["q95"][index] - forecast["center"]["q05"][index]
            row = {"Action": preview["action"], "Applied inclination (°)": preview["effective_inc_deg"],
                   "DLS (°/100 ft)": station["dls_deg_per_100ft"]}
            if "calibration_envelope" in forecast:
                lower, upper = target_probability_range(forecast, index, station["tvd_ft"])
                envelope = forecast["calibration_envelope"]["center"]
                row.update({"Min conditional probability (%)": 100 * lower,
                            "Max conditional probability (%)": 100 * upper,
                            "Calibration envelope width (ft)": envelope["q95"][index] - envelope["q05"][index],
                            "Assumed-mixture probability in target (%)": probability,
                            "Mixture center interval width (ft)": width})
            else:
                row.update({"Model probability in target (%)": probability, "Center interval width (ft)": width})
            row.update({"Next MD (ft)": station["md_ft"], "Next x (ft)": station["x_ft"],
                        "Next TVD (ft)": station["tvd_ft"], "Clipped": preview["clipped"]})
            rows.append(row)
        probability_fields = ("Min conditional probability (%)", "Max conditional probability (%)",
                              "Assumed-mixture probability in target (%)") if "calibration_envelope" in forecast else ("Model probability in target (%)",)
        if not all(np.isfinite(row[field]) and 0 <= row[field] <= 100 for row in rows for field in probability_fields):
            raise ValueError("The command assessment contains a nonfinite probability")
        return {"step_index": expected_step_index, "snapshot_sha256": snapshot["snapshot_sha256"],
                "actions": rows, "forecast": forecast}
