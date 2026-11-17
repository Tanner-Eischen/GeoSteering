from __future__ import annotations

import argparse
from pathlib import Path

from app.io.well_import import import_well_folder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a well folder into a project.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--well-folder", required=True, type=Path)
    parser.add_argument("--well-name", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = import_well_folder(
        project_root=args.project_root,
        well_folder=args.well_folder,
        well_name=args.well_name,
    )
    print(
        f"Imported well '{result['well_name']}' as {result['well_id']} "
        f"(survey_rows={result['survey_rows']}, log_rows={result['log_rows']}, markers={result['markers_loaded']})"
    )


if __name__ == "__main__":
    main()

