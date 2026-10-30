from __future__ import annotations

import json

import lasio
import numpy as np
import pytest

from tools.generate_sample_data import generate_sample_data


def test_generation_repeats_numerical_products_and_records_sensor_limits(tmp_path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    generate_sample_data(first, seed=321)
    generate_sample_data(second, seed=321)
    assert json.loads((first / "truth.json").read_text()) == json.loads((second / "truth.json").read_text())
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest == json.loads((second / "manifest.json").read_text())
    assert "disturbance_x_ft" not in str(manifest)
    assert manifest["sensor_calibration"]["gr_saturation_api"] == [20.0, 160.0]
    for name in ["offset_01", "offset_02", "offset_03", "active_01"]:
        a, b = first / "wells" / name, second / "wells" / name
        assert (a / "survey.csv").read_bytes() == (b / "survey.csv").read_bytes()
        np.testing.assert_array_equal(lasio.read(a / "logs.las").data, lasio.read(b / "logs.las").data)


def test_generator_refuses_populated_destination_without_altering_it(tmp_path) -> None:
    sentinel = tmp_path / "existing.csv"
    sentinel.write_text("valuable input\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not empty"):
        generate_sample_data(tmp_path)
    assert list(tmp_path.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "valuable input\n"
