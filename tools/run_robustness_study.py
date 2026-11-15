"""Run the predeclared synthetic robustness study into a fresh directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.study.robustness import run_study


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    summary = run_study(args.out, args.manifest)
    print(json.dumps({"study_id": summary["study_id"], "counts": summary["counts"], "evaluation": summary["evaluation"], "worst_guided": summary["worst_guided"]}, indent=2))


if __name__ == "__main__":
    main()
