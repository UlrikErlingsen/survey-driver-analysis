"""Large-data limits: fast checks that the old caps no longer block and the new ones explain themselves."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from driversignal import io as survey_io
from driversignal import reliability
from driversignal.drivers import MODEL_MAX_ROWS, fit_driver_model
from driversignal.errors import DataProblem
from driversignal.io import compact_frame, load_data
from driversignal.reporting import influence_export_note, privacy_safe_influence
from driversignal.ui.plotting import FITTED_TOP_INFLUENCE, fitted_points


def test_default_limits_match_the_1000_mb_upload_cap() -> None:
    assert survey_io.DEFAULT_MAX_UPLOAD_MB == 1000
    assert survey_io.MAX_TABLE_ROWS >= 5_000_000
    assert survey_io.MAX_TOTAL_CELLS >= 100 * survey_io.MAX_TABLE_ROWS // 2
    assert MODEL_MAX_ROWS == 1_000_000


def test_launcher_variable_sets_the_in_code_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIVERSIGNAL_MAX_UPLOAD_MB", "250")
    assert survey_io._configured_upload_mb() == 250
    monkeypatch.setenv("DRIVERSIGNAL_MAX_UPLOAD_MB", "not-a-number")
    assert survey_io._configured_upload_mb() == 1000
    monkeypatch.delenv("DRIVERSIGNAL_MAX_UPLOAD_MB")
    assert survey_io._configured_upload_mb() == 1000


def test_csv_beyond_the_old_500000_row_limit_loads_compactly() -> None:
    rows = 600_000
    raw = b"respondent,service,recommend\n" + b"1,5,9\n2,3,7\n" * (rows // 2)
    frame = load_data(raw, name="wave.csv").tables["data"]
    assert len(frame) == rows
    assert frame["service"].dtype == np.int8  # rating scales are stored in one byte per answer


def test_semicolon_csv_uses_the_fast_parser_with_detected_delimiter() -> None:
    frame = load_data(b"id;score;comment\n1;4;fine\n2;5;good, really\n", name="survey.csv").tables["data"]
    assert frame.columns.tolist() == ["id", "score", "comment"]
    assert frame["comment"].tolist() == ["fine", "good, really"]


def test_row_limit_message_names_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(survey_io, "MAX_TABLE_ROWS", 3)
    with pytest.raises(DataProblem, match="more than 3 rows"):
        load_data(b"a,b\n1,2\n3,4\n5,6\n7,8\n", name="survey.csv")


def test_one_byte_limit_covers_json_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(survey_io, "MAX_UPLOAD_BYTES", 64)
    monkeypatch.setattr(survey_io, "MAX_UPLOAD_MB", 1000)
    payload = json.dumps([{"a": index} for index in range(20)]).encode()
    with pytest.raises(DataProblem, match="configured 1,000 MB limit"):
        load_data(payload, name="survey.json")


def test_compaction_is_lossless() -> None:
    frame = pd.DataFrame({"likert": [1.0, np.nan, 7.0], "weight": [0.1, 0.2, 0.3], "id": [1, 2, 300]})
    compact_frame(frame)
    assert frame["likert"].dtype == np.float32
    assert frame["weight"].dtype == np.float64  # 0.1 is not exact in float32, so it is kept
    assert frame["id"].dtype == np.int16
    assert frame["weight"].tolist() == [0.1, 0.2, 0.3]


def test_large_alpha_bootstrap_uses_a_labelled_rescaled_subsample(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(8)
    base = rng.normal(size=6000)
    frame = pd.DataFrame({"a": base + rng.normal(0, 0.8, 6000), "b": base + rng.normal(0, 0.8, 6000)})
    full_low, full_high, full_rows = reliability.bootstrap_alpha_details(frame, repetitions=100, seed=3)
    assert full_rows == 6000
    monkeypatch.setattr(reliability, "BOOTSTRAP_CELL_BUDGET", 400_000)
    low, high, rows = reliability.bootstrap_alpha_details(frame, repetitions=100, seed=3)
    assert rows == reliability.MIN_BOOTSTRAP_SUBSAMPLE
    alpha = reliability.cronbach_alpha(frame)
    assert low < alpha < high
    assert (high - low) == pytest.approx(full_high - full_low, rel=0.35)
    result = reliability.analyze_reliability(frame, "Scale", bootstrap_repetitions=100)
    assert result.bootstrap_rows == reliability.MIN_BOOTSTRAP_SUBSAMPLE
    assert any("rescaled to the full sample" in warning for warning in result.warnings)


def test_driver_model_samples_above_its_row_limit_and_says_so() -> None:
    rng = np.random.default_rng(4)
    x = rng.normal(size=(1000, 2))
    frame = pd.DataFrame({"y": x @ [1.0, -0.5] + rng.normal(size=1000), "x1": x[:, 0], "x2": x[:, 1]})
    result = fit_driver_model(frame, "y", ["x1", "x2"], max_model_rows=400)
    metrics = result.metrics.set_index("metric")["value"]
    assert metrics["Usable respondents"] == 400
    assert metrics["Complete respondents available"] == 1000
    assert result.complete_rows == 1000
    assert len(result.fitted) == 400
    assert "seeded random sample of 400" in result.model_sample_note
    assert result.model_sample_note in result.warnings
    repeat = fit_driver_model(frame, "y", ["x1", "x2"], max_model_rows=400)
    pd.testing.assert_frame_equal(result.coefficients, repeat.coefficients)
    unsampled = fit_driver_model(frame, "y", ["x1", "x2"])
    assert unsampled.model_sample_note == ""


def test_influence_export_and_chart_keep_the_most_influential_rows() -> None:
    fitted = pd.DataFrame(
        {
            "source_row": np.arange(2, 12_002),
            "observed": 1.0,
            "fitted": 1.0,
            "residual": 0.0,
            "leverage": 0.01,
            "cooks_distance": np.linspace(0, 1, 12_000),
        }
    )
    exported = privacy_safe_influence(fitted, max_rows=100)
    assert len(exported) == 100
    assert exported["cooks_distance"].min() >= fitted["cooks_distance"].nlargest(100).min()
    assert influence_export_note(fitted, max_rows=100).startswith("The 100 model rows")
    points = fitted_points(fitted, max_points=1000)
    assert len(points) == 1000
    assert set(fitted["cooks_distance"].nlargest(FITTED_TOP_INFLUENCE).index) <= set(points.index)
