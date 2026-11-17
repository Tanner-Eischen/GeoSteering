from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.io import create_project, load_project
from app.services.import_preview import check_import_folders, parse_well_paths
from tools.generate_sample_data import generate_sample_data


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_path_parser_preserves_mixed_quoted_and_unquoted_entries():
    assert parse_well_paths('"C:\\Well A"; C:\\Well_B\n"C:\\Well;C"') == [
        Path(r"C:\Well A"), Path(r"C:\Well_B"), Path(r"C:\Well;C"),
    ]
    with pytest.raises(ValueError, match="unmatched"):
        parse_well_paths('"C:\\Well A')


def test_preview_detects_duplicates_missing_files_and_existing_names(tmp_path):
    folder = tmp_path / "well"
    folder.mkdir()
    (folder / "survey.csv").touch()
    rows = check_import_folders([folder, folder], ["Well", "well"], [])
    assert all(not row["ready"] for row in rows)
    assert all("Missing logs.las" in row["File check"] for row in rows)
    assert all("Folder listed more than once" in row["File check"] for row in rows)
    assert all("unique name" in row["File check"] for row in rows)
    (folder / "logs.las").touch()
    assert check_import_folders([folder], ["Well"], ["well"])[0]["ready"] is False
    assert check_import_folders([folder], ["New well"], ["well"])[0]["ready"] is True


def test_import_results_survive_rerun_and_duplicate_import_is_disabled(tmp_path):
    source = tmp_path / "source"
    generate_sample_data(source, seed=123)
    root = tmp_path / "project"
    create_project(root, "Import workflow")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "survey.csv").write_text("wrong_column\n0\n", encoding="utf-8")
    (broken / "logs.las").write_text("invalid", encoding="utf-8")
    valid = source / "wells" / "active_01"
    app = AppTest.from_string(
        f"from app.pages.data_import import render\nrender({str(root)!r})", default_timeout=30,
    ).run()
    app.text_area[0].set_value(f'"{valid}"\n{broken}').run()
    _button(app, "Review folders").click().run()
    assert not app.exception
    assert len(load_project(root).wells) == 0
    assert not _button(app, "Import 2 well(s)").disabled
    _button(app, "Import 2 well(s)").click().run()
    assert not app.exception
    assert len(load_project(root).wells) == 1
    assert any("Imported 1 of 2" in item.value for item in app.success)
    assert any("missing columns" in item.value for item in app.error)
    app.run()
    assert not app.exception
    assert any("Imported 1 of 2" in item.value for item in app.success)
    assert any("missing columns" in item.value for item in app.error)
    assert _button(app, "Import 2 well(s)").disabled
    assert len(load_project(root).wells) == 1


def test_changed_paths_require_fresh_review(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Review")
    folder = tmp_path / "well"
    folder.mkdir()
    for filename in ("survey.csv", "logs.las"):
        (folder / filename).touch()
    app = AppTest.from_string(f"from app.pages.data_import import render\nrender({str(root)!r})").run()
    app.text_area[0].set_value(str(folder)).run()
    _button(app, "Review folders").click().run()
    assert not _button(app, "Import 1 well(s)").disabled
    app.text_area[0].set_value(str(tmp_path / "different")).run()
    assert _button(app, "Import 1 well(s)").disabled
    assert not app.exception
