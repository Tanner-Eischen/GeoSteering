"""Compare acquired fork branches without revealing future data or sealed truth."""

from __future__ import annotations

import hashlib
import math
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

from app.io.project_store import read_json
from app.services.decisions import load_decisions
from app.services.interpretations import load_interpretations
from app.services.project_data import load_well_frames
from app.services.run_metrics import load_run_metrics
from app.services.run_paths import run_root
from app.services.run_transactions import run_access_lock
from app.sim.sim_store import load_simulation_config, load_simulation_state


def _lineage(root, run_id):
    chain, seen = [], set()
    while run_id is not None:
        scope = run_root(root, run_id)
        if run_id in seen:
            raise ValueError("Fork ancestry contains a cycle")
        if not scope.is_dir() or not (scope / "manifest.json").is_file():
            raise ValueError("Fork ancestry is missing; keep the parent run in this project")
        seen.add(run_id)
        manifest = read_json(scope / "manifest.json")
        if manifest.get("run_id") != run_id:
            raise ValueError("Run manifest identity does not match its directory")
        chain.append((run_id, manifest))
        run_id = manifest.get("parent_run_id")
    return list(reversed(chain))


def _label(run_id, mode, manifest):
    parent = manifest.get("parent_run_id")
    relationship = f"fork of {parent[:8]} at step {manifest['forked_at_step']}" if parent else "original"
    return f"{mode.title()} · {run_id[:8]} · {relationship}"


def list_run_catalog(root) -> list[dict]:
    """Public relationship/status metadata only; no truth or evaluation files."""
    rows = []
    for scope in sorted((Path(root) / "runs").glob("*")):
        if not scope.is_dir():
            continue
        try:
            chain = _lineage(root, scope.name)
            with run_access_lock(scope):
                config = load_simulation_config(root, scope.name)
                state = load_simulation_state(root, scope.name)
                manifest = read_json(scope / "manifest.json")
                if config.run_id != scope.name or state.run_id != scope.name:
                    raise ValueError("Saved run identity is inconsistent")
                rows.append({
                    "run_id": scope.name, "label": _label(scope.name, config.mode, manifest),
                    "parent_run_id": manifest.get("parent_run_id"), "forked_at_step": manifest.get("forked_at_step"),
                    "family_root_id": chain[0][0], "depth": len(chain) - 1,
                    "mode": config.mode, "step_index": state.step_index,
                    "revealed_md_ft": state.revealed_md_ft, "complete": state.complete,
                    "status": "Complete" if state.complete else "In progress", "available": True,
                })
        except (OSError, ValueError, KeyError) as exc:
            rows.append({"run_id": scope.name, "label": f"Unavailable · {scope.name[:8]}", "status": str(exc), "available": False})
    return sorted(rows, key=lambda row: (row.get("family_root_id", "~"), row.get("depth", 0), row["run_id"]))


def _file(scope, name):
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("Invalid frozen input path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name or not name.startswith("inputs/"):
        raise ValueError("Invalid frozen input path")
    return Path(scope) / name


def _public_identity(scope, config, manifest):
    """Verify observed input/mechanics bytes; leave private scenario bytes sealed."""
    hashes = manifest.get("input_hashes")
    if not hashes:
        raise ValueError("This run has no frozen input fingerprints; initialize a new experiment")
    for name, expected in hashes.items():
        if hashlib.sha256(_file(scope, name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen run inputs changed; this comparison is not valid")
    provenance = read_json(scope / "environment" / "provenance.json", default={})
    truth_hash = provenance.get("private_scenario_sha256" if config.mode == "causal" else "source_truth_sha256")
    mechanics = {"mode": "fixed recorded replay"}
    if config.mode == "causal":
        if not truth_hash:
            raise ValueError("Causal comparison requires a captured field fingerprint")
        path = scope / "environment" / "mechanics.json"
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != provenance.get("mechanics_sha256"):
            raise ValueError("Causal mechanics are missing or changed; start a new causal experiment")
        mechanics = read_json(path)
    code = manifest.get("code_provenance", {}).get("source_fingerprint")
    if not code:
        raise ValueError("This run has no frozen code identity; initialize a new experiment")
    return {"input_hashes": hashes, "truth_sha256": truth_hash, "mechanics": mechanics, "source_fingerprint": code}


def _prefix_step(left_chain, right_chain):
    shared = 0
    for left, right in zip(left_chain, right_chain):
        if left[0] != right[0]:
            break
        shared += 1
    if shared == 0:
        raise ValueError("Choose parent/child or sibling branches from the same fork family")
    edges = []
    for chain in (left_chain, right_chain):
        if len(chain) > shared:
            step = chain[shared][1].get("forked_at_step")
            if type(step) is not int or step < 0:
                raise ValueError("Fork step metadata is invalid")
            edges.append(step)
    return min(edges)


def _load_run(root, run_id):
    scope = run_root(root, run_id)
    config = load_simulation_config(root, run_id)
    state = load_simulation_state(root, run_id)
    if config.run_id != run_id or state.run_id != run_id:
        raise ValueError("Saved run identity is inconsistent")
    manifest = read_json(scope / "manifest.json")
    versions = load_interpretations(root, run_id)
    if not versions:
        raise ValueError("Run has no frozen baseline interpretation")
    return {
        "scope": scope, "config": config, "state": state, "manifest": manifest,
        "identity": _public_identity(scope, config, manifest), "versions": versions,
        "decisions": load_decisions(root, run_id), "metrics": load_run_metrics(root, run_id),
        "frames": load_well_frames(root, config.active_well_id, run_id=run_id),
    }


def _verify_pair(left, right, prefix_step):
    _verify_configs(left["config"], right["config"])
    for key, reason in (("input_hashes", "frozen input evidence"), ("truth_sha256", "captured field fingerprints"), ("mechanics", "causal mechanics"), ("source_fingerprint", "frozen code identity")):
        if left["identity"][key] != right["identity"][key]:
            raise ValueError(f"Runs have different {reason}; this is not a controlled branch comparison")
    if left["versions"][0] != right["versions"][0]:
        raise ValueError("Runs have different frozen baseline models")
    for item in (left, right):
        if item["state"].step_index < prefix_step or len(item["decisions"]) < prefix_step or len(item["metrics"]) < prefix_step or len(item["state"].version_id_by_step) <= prefix_step:
            raise ValueError("Fork metadata exceeds the saved acquired history")
    if left["state"].version_id_by_step[:prefix_step + 1] != right["state"].version_id_by_step[:prefix_step + 1]:
        raise ValueError("Fork branches do not preserve the same interpretation prefix")
    if left["decisions"][:prefix_step] != right["decisions"][:prefix_step] or left["metrics"][:prefix_step] != right["metrics"][:prefix_step]:
        raise ValueError("Fork branches do not preserve the same decision/metric prefix")
    md = left["decisions"][prefix_step - 1].md_to_ft if prefix_step else left["config"].start_md_ft
    for name in ("trajectory", "logs"):
        a = left["frames"][name]
        b = right["frames"][name]
        if a[a.md_ft <= md].to_dict(orient="records") != b[b.md_ft <= md].to_dict(orient="records"):
            raise ValueError("Fork branches do not preserve the same acquired data prefix")
    return md


def _verify_configs(left_config, right_config):
    excluded = {"run_id", "hidden_truth_path"}
    a, b = (config.model_dump(mode="json", exclude=excluded) for config in (left_config, right_config))
    different = [key for key in a if a[key] != b[key]]
    if different:
        raise ValueError(f"Run configurations differ ({', '.join(different)}); compare branches of one experiment")


def _snapshot(item, endpoint, start):
    rows = [row for row in item["metrics"] if row["revealed_md_ft"] <= endpoint and math.isclose(row["md_to_ft"], endpoint, abs_tol=1e-8)]
    if not rows:
        return None
    row = rows[-1]
    if not math.isclose(row.get("evaluated_length_ft", -1), max(0.0, endpoint - start), abs_tol=1e-6):
        return None
    # Return the persisted decision-time row, never recompute under a later model.
    keys = {
        "step_index", "revealed_md_ft", "decision_time_md_ft", "interpretation_version_id", "decision_id",
        "md_from_ft", "md_to_ft", "metric_basis", "coordinate_basis", "action", "uncertainty_band_tvd_ft",
        "percent_in_zone", "avg_center_distance", "last_step_in_zone", "in_zone_length_ft", "evaluated_length_ft", "max_overshoot_ft",
    }
    return {key: value for key, value in row.items() if key in keys}


def _public_response(response):
    if not response:
        return None
    allowed = {"action", "requested_inc_deg", "effective_inc_deg", "clipped", "limit_reason", "step_index", "md_from_ft", "md_to_ft"}
    return {key: value for key, value in response.items() if key in allowed}


def compare_runs(root, left_run_id, right_run_id, evaluate=False) -> dict:
    """Read a fair acquired comparison; compute truth only by explicit completion gate."""
    if left_run_id == right_run_id:
        raise ValueError("Choose two different saved runs")
    left_chain, right_chain = _lineage(root, left_run_id), _lineage(root, right_run_id)
    ids = sorted({run_id for chain in (left_chain, right_chain) for run_id, _ in chain})
    with ExitStack() as locks:
        for run_id in ids:
            locks.enter_context(run_access_lock(run_root(root, run_id)))
        # Manifests are immutable during normal advancement; reject a changed
        # ancestry rather than using relationships discovered before locking.
        if _lineage(root, left_run_id) != left_chain or _lineage(root, right_run_id) != right_chain:
            raise ValueError("Fork ancestry changed; reload this comparison")
        prefix_step = _prefix_step(left_chain, right_chain)
        _verify_configs(load_simulation_config(root, left_run_id), load_simulation_config(root, right_run_id))
        left, right = _load_run(root, left_run_id), _load_run(root, right_run_id)
        prefix_md = _verify_pair(left, right, prefix_step)
        limit = min(left["state"].revealed_md_ft, right["state"].revealed_md_ft)
        # Restrict to a recorded station present in both acquired paths. No
        # interpolation can introduce a station from the more advanced branch.
        left_md = set(left["frames"]["trajectory"].md_ft)
        common = left_md.intersection(right["frames"]["trajectory"].md_ft)
        common = [float(md) for md in common if md <= limit]
        if not common:
            raise ValueError("Branches have no common acquired trajectory station")
        endpoint = max(common)
        start = max(left["config"].start_md_ft, left["config"].lateral_start_md_ft)
        interval = {"start_md_ft": start, "end_md_ft": endpoint, "evaluated_length_ft": max(0.0, endpoint - start), "branch_start_md_ft": prefix_md}
        runs, command_maps = {}, {}
        for side, item in (("left", left), ("right", right)):
            config, state = item["config"], item["state"]
            decisions = [entry for entry in item["decisions"] if entry.md_to_ft <= endpoint]
            metric_by_step = {row["step_index"]: row for row in item["metrics"] if row["revealed_md_ft"] <= endpoint}
            command_maps[side] = {
                entry.step_index: {
                    "action": entry.recommendation.action, "target_inc_deg": entry.recommendation.target_inc_deg,
                    "observations": entry.observations, "interpretation_version_id": entry.interpretation_version_id,
                    "response": _public_response(metric_by_step.get(entry.step_index, {}).get("command_response")),
                    "md_from_ft": entry.md_from_ft, "md_to_ft": entry.md_to_ft,
                } for entry in decisions if entry.step_index > prefix_step
            }
            runs[side] = {
                "run_id": config.run_id, "label": _label(config.run_id, config.mode, item["manifest"]),
                "mode": config.mode, "complete": state.complete, "revealed_md_ft": state.revealed_md_ft,
                "trajectory": item["frames"]["trajectory"].query("@start <= md_ft <= @endpoint").to_dict(orient="records"),
                "logs": item["frames"]["logs"].query("@start <= md_ft <= @endpoint").to_dict(orient="records"),
                "decisions": [entry.model_dump(mode="json") for entry in decisions],
                "estimated_snapshot": _snapshot(item, endpoint, start),
            }
        command_rows = [{"step_index": step, "left": command_maps["left"].get(step), "right": command_maps["right"].get(step)} for step in sorted(set(command_maps["left"]) | set(command_maps["right"]))]
        differences = {"command_rows": command_rows, "endpoint_tvd_ft": None, "endpoint_x_ft": None, "estimated_percent_in_zone_pp": None}
        if all(runs[side]["trajectory"] for side in runs):
            a, b = (runs[side]["trajectory"][-1] for side in ("left", "right"))
            differences.update({"endpoint_tvd_ft": b["tvd_ft"] - a["tvd_ft"], "endpoint_x_ft": b.get("x_ft", b["east_ft"]) - a.get("x_ft", a["east_ft"])})
        estimates = [runs[side]["estimated_snapshot"] for side in ("left", "right")]
        if all(estimates):
            differences["estimated_percent_in_zone_pp"] = estimates[1]["percent_in_zone"] - estimates[0]["percent_in_zone"]
        both_complete = left["state"].complete and right["state"].complete
        truth = None
        if evaluate:
            if not both_complete:
                raise ValueError("Complete both branches before requesting independent truth evaluation")
            if endpoint != left["config"].end_md_ft or interval["evaluated_length_ft"] <= 0:
                raise ValueError("Completed truth comparison requires the same positive scoring interval")
            from app.services.evaluation import evaluate_completed_run
            scores = {side: evaluate_completed_run(root, run_id=item["config"].run_id) for side, item in (("left", left), ("right", right))}
            if any(not math.isclose(score["metrics"]["evaluated_length_ft"], interval["evaluated_length_ft"], abs_tol=1e-6) for score in scores.values()):
                raise ValueError("Independent evaluator interval differs from the compared interval")
            truth = {**scores, "differences": {key: scores["right"]["metrics"][key] - scores["left"]["metrics"][key] for key in scores["left"]["metrics"] if isinstance(scores["left"]["metrics"][key], (int, float))}}
        return {
            "left": left_run_id, "right": right_run_id,
            "relationship": {"family_root_id": left_chain[0][0], "common_prefix_step": prefix_step, "common_prefix_md_ft": prefix_md},
            "interval": interval, "runs": runs, "differences": differences,
            "both_complete": both_complete, "truth_evaluation": truth,
            "notes": [
                "All differences are right minus left; estimates use each run's original persisted interpretation at the common endpoint.",
                "Branches share frozen source, evidence, initial model, mechanics and field fingerprints. Interpretation revisions and multiple commands may differ after the fork.",
                "Common placement denominators include the shared acquired prefix. No future station or log is interpolated into this view.",
                "Replay recommendations do not change the fixed recorded path." if left["config"].mode == "replay" else "Causal commands change a simplified synthetic trajectory; this is not operational drilling validation.",
                "Independent truth is sealed until both runs complete and evaluation is explicitly requested.",
            ],
        }
