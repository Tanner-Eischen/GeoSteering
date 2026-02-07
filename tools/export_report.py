from __future__ import annotations

import argparse
from pathlib import Path

from app.report.report_builder import build_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export geosteering PDF report from saved project state.")
    parser.add_argument("project_root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = build_report(args.project_root)
    print(f"Report exported: {out}")


if __name__ == "__main__":
    main()

