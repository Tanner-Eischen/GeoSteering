from __future__ import annotations

import argparse
import json
from pathlib import Path

import lasio
import numpy as np
import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory
from app.geo.formation import Scenario, default_scenario, formation_top_base
from app.geo.observation_model import sample_logs
from app.sim.causal import landing_trajectory


def write_las(path: Path, well_name: str, md_ft: np.ndarray, gr: np.ndarray, res: np.ndarray) -> None:
    las = lasio.LASFile()
    las.well.WELL = well_name
    las.well.DATE = '2026-01-01'
    las.well.NULL = -999.25
    las.append_curve('DEPT', md_ft, unit='FT', descr='Measured depth')
    las.append_curve('GR', gr, unit='API', descr='Gamma ray')
    las.append_curve('RT', res, unit='OHMM', descr='Resistivity')
    las.write(str(path), version=2.0)


def _grid(end: float, step: float) -> np.ndarray:
    return np.unique(np.append(np.arange(0.0, end, step), end))


def _write_well(root: Path, name: str, trajectory: pd.DataFrame, scenario: Scenario,
                sampling_step_ft: float, origin_east_ft: float, seed: int, offsets: bool) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    trajectory[['md_ft', 'inc_deg', 'azi_deg']].to_csv(root / 'survey.csv', index=False)
    reference = {'origin_east_ft': origin_east_ft, 'origin_north_ft': 0.0,
                 'initial_tvd_ft': 0.0, 'vertical_datum': 'LOCAL_TVD',
                 'coordinate_system': 'LOCAL_EAST_NORTH_FT'}
    (root / 'reference.json').write_text(json.dumps(reference, indent=2, sort_keys=True), encoding='utf-8')
    (root / 'well.json').write_text(json.dumps({'name': name, 'role': 'offset' if offsets else 'active', **reference}, indent=2, sort_keys=True), encoding='utf-8')
    md = _grid(float(trajectory.md_ft.max()), sampling_step_ft)
    samples = pd.DataFrame({'md_ft': md})
    for key in ['east_ft', 'tvd_ft']:
        samples[key] = np.interp(md, trajectory.md_ft, trajectory[key])
    samples['x_ft'] = samples.east_ft
    logs = sample_logs(samples, scenario, seed)
    write_las(root / 'logs.las', name, md, logs.GR.to_numpy(), logs.RES.to_numpy())
    if offsets:
        top, base = formation_top_base(origin_east_ft, scenario)
        pd.DataFrame({'marker_name': ['Top_A', 'Mid_A', 'Base_A'],
                      'md_ft': [float(top), float((top + base) / 2), float(base)],
                      'notes': ['Observed synthetic layer crossing'] * 3}).to_csv(root / 'markers.csv', index=False)
    top, base = formation_top_base(samples.x_ft.to_numpy(), scenario)
    inside = (samples.tvd_ft >= top) & (samples.tvd_ft <= base)
    return {'well_name': name, 'percent_in_zone': float(inside.mean() * 100),
            'avg_center_distance_ft': float(np.abs(samples.tvd_ft - (top + base) / 2).mean())}


def generate_sample_data(out: Path, seed: int = 123, number_of_offsets: int = 3,
                         active_well_length_ft: float = 7000.0, sampling_step_ft: float = 0.5,
                         zone_thickness_ft: float = 24.0, structure_trend_ft_per_1000ft: float = 5.0) -> None:
    '''Generate four wells in one shared spatial field.

    Operator inputs are manifest, surveys, logs, markers, and coordinate references.
    truth.json is reserved for the independent end-of-run evaluator.
    '''
    if number_of_offsets != 3:
        raise ValueError('The flagship scenario requires exactly three offsets.')
    if sampling_step_ft <= 0 or active_well_length_ft <= 2000:
        raise ValueError('Positive sampling step and a lateral after MD 2000 ft are required.')
    scenario = default_scenario(seed).model_copy(update={
        'thickness_ft': zone_thickness_ft,
        'regional_dip': structure_trend_ft_per_1000ft / 1000,
        'lateral_length_ft': active_well_length_ft - 2000,
    })
    scenario = Scenario.model_validate(scenario.model_dump())
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Scenario destination is not empty: {out}. Choose a new directory.")
    summaries = []
    for index, origin in enumerate([0.0, 500.0, 900.0]):
        md = _grid(1800.0, 50.0)
        traj = compute_trajectory(pd.DataFrame({'md_ft': md, 'inc_deg': np.zeros(len(md)), 'azi_deg': np.zeros(len(md))}))
        traj['east_ft'] = origin
        traj['x_ft'] = origin
        name = f'offset_{index + 1:02d}'
        summaries.append(_write_well(out / 'wells' / name, name, traj, scenario, sampling_step_ft, origin, seed + index + 1, True))
    landing = landing_trajectory(scenario)
    lateral_md = _grid(scenario.lateral_length_ft, 50.0)[1:] + scenario.landing_md_ft
    survey = pd.DataFrame({'md_ft': lateral_md, 'inc_deg': np.full(len(lateral_md), 90.0), 'azi_deg': np.full(len(lateral_md), 90.0)})
    active = compute_trajectory(pd.concat([landing[['md_ft', 'inc_deg', 'azi_deg']], survey], ignore_index=True))
    active['x_ft'] = active.east_ft
    summary = _write_well(out / 'wells' / 'active_01', 'active_01', active, scenario, sampling_step_ft, 0.0, seed + 100, False)
    summaries.append(summary)
    top, base = formation_top_base(active.x_ft.to_numpy(), scenario)
    manifest = {'scenario_version': scenario.version, 'seed': seed,
                'mode': 'interpretation_replay', 'offset_wells': [f'offset_{i:02d}' for i in range(1, 4)],
                'active_well': 'active_01', 'lateral_start_md_ft': scenario.landing_md_ft,
                'end_md_ft': scenario.max_md_ft, 'zone_thickness_ft': scenario.thickness_ft,
                'coordinate_system': 'LOCAL_EAST_NORTH_FT', 'vertical_datum': 'LOCAL_TVD',
                'positive_tvd_direction': 'down', 'sensor_calibration': {'gr_center_api': 80.0, 'gr_gradient_api_per_ft': 2.0,
                'gr_noise_std_api': 0.6, 'gr_saturation_api': [20.0, 160.0]},
                'uncertainty_note': 'Scenario-assumed band; not a calibrated confidence interval.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    truth = {'seed': seed, 'scenario': scenario.model_dump(), 'wells': summaries,
             'zone_model': {'base_top_ft': float(top[0]), 'trend_ft_per_1000ft': structure_trend_ft_per_1000ft,
                'zone_thickness_ft': scenario.thickness_ft,
                'top_control_points': [{'md_ft': float(md), 'tvd_ft': float(y)} for md, y in zip(active.md_ft, top)],
                'base_control_points': [{'md_ft': float(md), 'tvd_ft': float(y)} for md, y in zip(active.md_ft, base)]},
             'expected_baseline_kpis': {'active_01': {'percent_in_zone': round(summary['percent_in_zone'], 4),
                 'avg_center_distance_ft': round(summary['avg_center_distance_ft'], 4)}}}
    (out / 'truth.json').write_text(json.dumps(truth, indent=2, sort_keys=True), encoding='utf-8')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate the shared-coordinate structural uncertainty scenario.')
    parser.add_argument('--out', type=Path, default=Path('data/sample_project'))
    parser.add_argument('--seed', type=int, default=123)
    parser.add_argument('--number-of-offsets', type=int, default=3)
    parser.add_argument('--active-well-length-ft', type=float, default=7000.0)
    parser.add_argument('--sampling-step-ft', type=float, default=0.5)
    parser.add_argument('--zone-thickness-ft', type=float, default=24.0)
    parser.add_argument('--structure-trend-ft-per-1000ft', type=float, default=5.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_sample_data(args.out, args.seed, args.number_of_offsets, args.active_well_length_ft,
                         args.sampling_step_ft, args.zone_thickness_ft, args.structure_trend_ft_per_1000ft)
    print(f'Generated sample dataset at {args.out}')


if __name__ == '__main__':
    main()
