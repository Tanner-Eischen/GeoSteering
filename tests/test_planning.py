from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.model.schemas import PlanParameters
from app.plan.plan_export import PLAN_EXPORT_COLUMNS, export_plan_csv
from app.plan.plan_generator import generate_plan


def test_d1_plan_station_count() -> None:
    params = PlanParameters(
        kickoff_md_ft=1000.0,
        landing_md_ft=3000.0,
        lateral_length_ft=5000.0,
        planned_azi_deg=90.0,
        step_ft=100.0,
    )
    result = generate_plan(params, dls_max_deg_per_100ft=3.0)
    assert len(result.stations) == 81


def test_d2_dls_exceedance_detection() -> None:
    params = PlanParameters(
        kickoff_md_ft=1000.0,
        landing_md_ft=1200.0,
        lateral_length_ft=5000.0,
        planned_azi_deg=90.0,
        step_ft=100.0,
    )
    result = generate_plan(params, dls_max_deg_per_100ft=3.0)
    assert len(result.exceedances) >= 1


def test_d3_plan_export_columns(tmp_path: Path) -> None:
    params = PlanParameters(
        kickoff_md_ft=1000.0,
        landing_md_ft=3000.0,
        lateral_length_ft=5000.0,
        planned_azi_deg=90.0,
        step_ft=100.0,
    )
    result = generate_plan(params, dls_max_deg_per_100ft=3.0)
    out = tmp_path / "plan.csv"
    export_plan_csv(result.stations, out)

    df = pd.read_csv(out)
    assert list(df.columns) == PLAN_EXPORT_COLUMNS

