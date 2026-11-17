from __future__ import annotations

import argparse
from pathlib import Path

from app.report.report_builder import build_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export geosteering PDF report from saved project state.")
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--run-id", help="Saved run to export; defaults to the active run")
    parser.add_argument("--plan-id", help="Explicit saved plan; otherwise preserve the run's pinned plan")
    parser.add_argument("--include-well", action="append", dest="include_wells", help="Well name or ID; may be repeated")
    parser.add_argument("--include-step", action="append", type=int, dest="include_steps", help="Saved history step; may be repeated")
    parser.add_argument("--strict", action="store_true", help="Require scientific provenance, figures and completed evaluation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = build_report(
        args.project_root, run_id=args.run_id, plan_id=args.plan_id,
        include_wells=args.include_wells, include_steps=args.include_steps, strict=args.strict,
    )
    print(f"Report exported: {out}")


if __name__ == "__main__":
    main()

