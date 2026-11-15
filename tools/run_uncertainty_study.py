"""Evaluate fixed ensemble settings on a new predeclared synthetic study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.study.uncertainty_calibration import run_study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    summary = run_study(args.out, args.manifest)
    print(json.dumps({key: summary[key] for key in ("study_id", "counts", "evaluation", "worst_trial")}, indent=2))


if __name__ == "__main__":
    main()
