from io import BytesIO

import pytest
from streamlit.testing.v1 import AppTest

from app.io import create_project, load_project
from app.services.upload_import import collect_uploads, import_uploaded_well, upload_signature
from tools.generate_sample_data import generate_sample_data


@pytest.mark.parametrize("filename", ["../survey.csv", r"..\survey.csv", "other.csv", "/survey.csv"])
def test_uploads_reject_non_whitelisted_paths(filename):
    with pytest.raises(ValueError, match="Unexpected filename"):
        collect_uploads([(filename, b"data")])


def test_uploads_reject_duplicate_files_and_fingerprint_contents():
    with pytest.raises(ValueError, match="More than one survey.csv"):
        collect_uploads([("survey.csv", b"one"), ("survey.csv", b"two")])
    first = {"survey.csv": b"one", "logs.las": b"two"}
    assert upload_signature(first) == upload_signature(dict(reversed(list(first.items()))))
    assert upload_signature(first) != upload_signature({**first, "logs.las": b"three"})


def test_invalid_upload_errors_hide_staging_paths_and_leave_project_unchanged(tmp_path):
    root = tmp_path / "project"
    create_project(root, "Invalid upload")
    with pytest.raises(ValueError, match="required files"):
        import_uploaded_well(root, {"survey.csv": b""}, "Example")
    with pytest.raises(ValueError, match="uploaded files") as error:
        import_uploaded_well(root, {"survey.csv": b"wrong_column\n0\n", "logs.las": b"invalid"}, "Example")
    assert "geosteering-upload-" not in str(error.value)
    assert not load_project(root).wells


def test_upload_page_imports_real_files_and_prevents_content_repeat(tmp_path, monkeypatch):
    from app.pages import data_import

    source = tmp_path / "source"
    generate_sample_data(source, seed=123)
    root = tmp_path / "project"
    create_project(root, "Upload workflow")
    uploads = []
    for filename in ("survey.csv", "logs.las", "markers.csv", "reference.json"):
        stream = BytesIO((source / "wells" / "offset_01" / filename).read_bytes())
        stream.name = filename
        uploads.append(stream)
    monkeypatch.setattr(data_import.st, "file_uploader", lambda *args, **kwargs: uploads)
    app = AppTest.from_string(
        f"from app.pages.data_import import render\nrender({str(root)!r})", default_timeout=30,
    ).run()
    app.radio(key="import_method").set_value("Upload files").run()
    assert not app.exception
    assert all("Selected" in value for value in app.dataframe[0].value["Status"])
    app.text_input[0].set_value("Uploaded Well").run()
    button = next(button for button in app.button if button.label == "Import uploaded well")
    assert not button.disabled
    button.click().run()
    assert not app.exception
    assert [well.name for well in load_project(root).wells] == ["Uploaded Well"]
    assert any("Imported 1 of 1" in item.value for item in app.success)
    app.text_input[0].set_value("Another name").run()
    assert any("already imported in this session" in item.value for item in app.warning)
    assert next(button for button in app.button if button.label == "Import uploaded well").disabled
    assert any("Imported 1 of 1" in item.value for item in app.success)
    assert len(load_project(root).wells) == 1
    with pytest.raises(ValueError, match="already exists"):
        import_uploaded_well(root, {upload.name: upload.getvalue() for upload in uploads}, "uploaded well")
