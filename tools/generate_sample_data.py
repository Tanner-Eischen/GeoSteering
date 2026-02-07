from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import lasio
import numpy as np
import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory


def top_tvd(md_ft: np.ndarray, base_top: float, trend_ft_per_1000ft: float) -> np.ndarray:
    return base_top + trend_ft_per_1000ft * (md_ft / 1000.0) + 6.0 * np.sin(md_ft / 700.0)


def base_tvd(md_ft: np.ndarray, base_top: float, trend_ft_per_1000ft: float, zone_thickness_ft: float) -> np.ndarray:
    return top_tvd(md_ft, base_top, trend_ft_per_1000ft) + zone_thickness_ft


def write_las(path: Path, well_name: str, md_ft: np.ndarray, gr: np.ndarray, res: np.ndarray) -> None:
    las = lasio.LASFile()
    las.well.WELL = well_name
    las.well.DATE = "2026-01-01"
    las.well.NULL = -999.25
    las.append_curve("DEPT", md_ft, unit="FT", descr="Measured depth")
    las.append_curve("GR", gr, unit="API", descr="Gamma ray")
    las.append_curve("RT", res, unit="OHMM", descr="Resistivity")
    las.write(str(path), version=2.0)


def build_survey(
    md_ft: np.ndarray,
    landing_md_ft: float,
    planned_azi_deg: float,
    drift_fn: Callable[[np.ndarray], np.ndarray],
) -> pd.DataFrame:
    inc = np.clip((md_ft / landing_md_ft) * 90.0, 0.0, 90.0)
    lateral_mask = md_ft >= landing_md_ft
    inc[lateral_mask] = np.clip(90.0 + drift_fn(md_ft[lateral_mask]), 85.0, 95.0)
    azi = np.full_like(md_ft, planned_azi_deg, dtype=float)
    return pd.DataFrame({"md_ft": md_ft, "inc_deg": inc, "azi_deg": azi})


def make_well_dataset(
    well_root: Path,
    well_name: str,
    md_log_ft: np.ndarray,
    survey_md_ft: np.ndarray,
    landing_md_ft: float,
    planned_azi_deg: float,
    base_top: float,
    trend: float,
    zone_thickness_ft: float,
    rng: np.random.Generator,
    drift_fn: Callable[[np.ndarray], np.ndarray],
    add_markers: bool,
) -> dict:
    well_root.mkdir(parents=True, exist_ok=True)

    survey_df = build_survey(
        md_ft=survey_md_ft,
        landing_md_ft=landing_md_ft,
        planned_azi_deg=planned_azi_deg,
        drift_fn=drift_fn,
    )
    survey_df.to_csv(well_root / "survey.csv", index=False)

    trajectory = compute_trajectory(survey_df)
    well_tvd = np.interp(md_log_ft, trajectory["md_ft"], trajectory["tvd_ft"])
    top = top_tvd(md_log_ft, base_top=base_top, trend_ft_per_1000ft=trend)
    base = base_tvd(md_log_ft, base_top=base_top, trend_ft_per_1000ft=trend, zone_thickness_ft=zone_thickness_ft)
    in_zone = (well_tvd >= top) & (well_tvd <= base)

    gr = np.where(in_zone, 70.0, 110.0) + rng.normal(0.0, 3.0, size=md_log_ft.size)
    res = np.where(in_zone, 40.0, 8.0) + rng.normal(0.0, 1.2, size=md_log_ft.size)
    res = np.clip(res, 0.2, None)

    write_las(well_root / "logs.las", well_name=well_name, md_ft=md_log_ft, gr=gr, res=res)

    if add_markers:
        markers = pd.DataFrame(
            {
                "marker_name": ["Top_A", "Mid_A", "Base_A"],
                "md_ft": [2000.0, 4500.0, 7000.0],
                "notes": ["Synthetic marker", "Synthetic marker", "Synthetic marker"],
            }
        )
        markers.to_csv(well_root / "markers.csv", index=False)

    return {
        "well_name": well_name,
        "percent_in_zone": float(in_zone.mean() * 100.0),
        "avg_center_distance_ft": float(np.mean(np.abs(well_tvd - (top + base) / 2.0))),
    }


def generate_sample_data(
    out: Path,
    seed: int = 123,
    number_of_offsets: int = 3,
    active_well_length_ft: float = 8000.0,
    sampling_step_ft: float = 0.5,
    zone_thickness_ft: float = 20.0,
    structure_trend_ft_per_1000ft: float = 5.0,
) -> None:
    if number_of_offsets != 3:
        raise ValueError("MVP sample contract currently expects exactly 3 offsets.")

    wells_root = out / "wells"
    wells_root.mkdir(parents=True, exist_ok=True)

    survey_md_ft = np.arange(0.0, active_well_length_ft + 100.0, 100.0)
    md_log_ft = np.arange(0.0, active_well_length_ft + sampling_step_ft, sampling_step_ft)

    drift_events = [
        {"md_from_ft": 3600.0, "md_to_ft": 4600.0, "inc_shift_deg": 1.6},
        {"md_from_ft": 5600.0, "md_to_ft": 6400.0, "inc_shift_deg": -1.8},
    ]

    def active_drift(md: np.ndarray) -> np.ndarray:
        shift = np.zeros_like(md, dtype=float)
        shift += np.where((md >= 3600.0) & (md <= 4600.0), 1.6, 0.0)
        shift += np.where((md >= 5600.0) & (md <= 6400.0), -1.8, 0.0)
        shift += 0.6 * np.sin(md / 900.0)
        return shift

    offset_drifts = [
        lambda md: 0.4 * np.sin(md / 1000.0),
        lambda md: -0.3 * np.sin(md / 1100.0) + 0.2,
        lambda md: 0.25 * np.sin(md / 850.0) - 0.15,
    ]

    wells = []
    for idx in range(number_of_offsets):
        rng = np.random.default_rng(seed + idx + 1)
        well_name = f"offset_{idx + 1:02d}"
        structural_shift = (idx - 1) * 6.0
        well_summary = make_well_dataset(
            well_root=wells_root / well_name,
            well_name=well_name,
            md_log_ft=md_log_ft,
            survey_md_ft=survey_md_ft,
            landing_md_ft=2200.0,
            planned_azi_deg=90.0 + idx * 2.0,
            base_top=1260.0 + structural_shift,
            trend=structure_trend_ft_per_1000ft,
            zone_thickness_ft=zone_thickness_ft,
            rng=rng,
            drift_fn=offset_drifts[idx],
            add_markers=True,
        )
        wells.append(well_summary)

    active_rng = np.random.default_rng(seed + 100)
    active_summary = make_well_dataset(
        well_root=wells_root / "active_01",
        well_name="active_01",
        md_log_ft=md_log_ft,
        survey_md_ft=survey_md_ft,
        landing_md_ft=2200.0,
        planned_azi_deg=90.0,
        base_top=1260.0,
        trend=structure_trend_ft_per_1000ft,
        zone_thickness_ft=zone_thickness_ft,
        rng=active_rng,
        drift_fn=active_drift,
        add_markers=False,
    )
    wells.append(active_summary)

    control_md = list(np.arange(0.0, active_well_length_ft + 1.0, 1000.0))
    truth = {
        "seed": seed,
        "zone_model": {
            "base_top_ft": 1260.0,
            "trend_ft_per_1000ft": structure_trend_ft_per_1000ft,
            "zone_thickness_ft": zone_thickness_ft,
            "top_control_points": [
                {"md_ft": float(md), "tvd_ft": float(top_tvd(np.array([md]), 1260.0, structure_trend_ft_per_1000ft)[0])}
                for md in control_md
            ],
            "base_control_points": [
                {
                    "md_ft": float(md),
                    "tvd_ft": float(
                        base_tvd(np.array([md]), 1260.0, structure_trend_ft_per_1000ft, zone_thickness_ft)[0]
                    ),
                }
                for md in control_md
            ],
        },
        "drift_events": drift_events,
        "expected_baseline_kpis": {
            "active_01": {
                "percent_in_zone": round(active_summary["percent_in_zone"], 4),
                "avg_center_distance_ft": round(active_summary["avg_center_distance_ft"], 4),
            }
        },
        "wells": wells,
    }

    with (out / "truth.json").open("w", encoding="utf-8") as f:
        json.dump(truth, f, indent=2, sort_keys=True, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic geosteering sample data.")
    parser.add_argument("--out", type=Path, default=Path("data/sample_project"))
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--number-of-offsets", type=int, default=3)
    parser.add_argument("--active-well-length-ft", type=float, default=8000.0)
    parser.add_argument("--sampling-step-ft", type=float, default=0.5)
    parser.add_argument("--zone-thickness-ft", type=float, default=20.0)
    parser.add_argument("--structure-trend-ft-per-1000ft", type=float, default=5.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_sample_data(
        out=args.out,
        seed=args.seed,
        number_of_offsets=args.number_of_offsets,
        active_well_length_ft=args.active_well_length_ft,
        sampling_step_ft=args.sampling_step_ft,
        zone_thickness_ft=args.zone_thickness_ft,
        structure_trend_ft_per_1000ft=args.structure_trend_ft_per_1000ft,
    )
    print(f"Generated sample dataset at {args.out}")


if __name__ == "__main__":
    main()

