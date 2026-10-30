from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.sim.causal import compare_strategies


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare completed synthetic HOLD and observation-guided runs.")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--out", type=Path, default=Path("comparison.json"))
    args = parser.parse_args()
    result = compare_strategies(seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({name: run["metrics"] for name, run in result["runs"].items()}, indent=2))


if __name__ == "__main__":
    main()
