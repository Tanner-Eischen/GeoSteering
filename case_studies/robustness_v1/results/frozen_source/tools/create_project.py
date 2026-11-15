from __future__ import annotations

import argparse
from pathlib import Path

from app.io.project_store import create_project


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a geosteering project folder.")
    parser.add_argument("project_root", type=Path, help="Project root directory.")
    parser.add_argument("--name", required=True, help="Project display name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = create_project(args.project_root, args.name)
    print(f"Created project '{project.name}' at {args.project_root}")


if __name__ == "__main__":
    main()

