"""Backward-compatible entry point for the complete scientific case study."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.run_case_study import build_case_study


def bootstrap_demo_project(project_root: Path, sample_root: Path, steps: int | None = None) -> Path:
    return build_case_study(project_root, sample_root, steps=steps)


def main():
    parser = argparse.ArgumentParser(description="Build a new isolated replay and report; complete by default.")
    parser.add_argument("--project-root", type=Path, default=Path("data/demo_project"))
    parser.add_argument("--sample-root", type=Path, default=Path("data/sample_project"))
    parser.add_argument("--steps", type=int, help="Explicit partial replay length")
    args = parser.parse_args()
    report = bootstrap_demo_project(args.project_root, args.sample_root, steps=args.steps)
    print(f"Demo bootstrap complete. Report: {report}")


if __name__ == "__main__":
    main()
