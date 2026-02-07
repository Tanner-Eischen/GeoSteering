from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.io.project_store import atomic_write_json, read_json
from app.model.schemas import DLSExceedance, Plan, PlanParameters


def save_plan(
    project_root: str | Path,
    name: str,
    parameters: PlanParameters,
    stations: pd.DataFrame,
    dls_max_deg_per_100ft: float,
    exceedances: list[DLSExceedance],
) -> Plan:
    root = Path(project_root)
    plans_dir = root / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    plan_id = str(uuid4())
    stations_rel = f"plans/{plan_id}_stations.parquet"
    stations_path = root / stations_rel
    stations.sort_values("md_ft").to_parquet(stations_path, index=False)

    plan = Plan(
        plan_id=plan_id,
        name=name,
        parameters=parameters,
        stations_path=stations_rel,
        dls_max_deg_per_100ft=dls_max_deg_per_100ft,
        dls_exceedances=exceedances,
    )
    atomic_write_json(plans_dir / f"{plan_id}.json", plan.model_dump(mode="json"))
    return plan


def load_plan(project_root: str | Path, plan_id: str) -> tuple[Plan, pd.DataFrame]:
    root = Path(project_root)
    plan_json = read_json(root / "plans" / f"{plan_id}.json")
    plan = Plan.model_validate(plan_json)
    stations = pd.read_parquet(root / plan.stations_path)
    return plan, stations

