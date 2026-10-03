"""Data limits: none locally, demo caps only with SIGNAL_PUBLIC=1, and large inputs handled without refusing."""

from __future__ import annotations

from io import BytesIO
import json

import numpy as np
import pandas as pd
import pytest

from driversignal import io as survey_io
from driversignal import limits, reliability
from driversignal.errors import DataProblem, friendly_message
from driversignal.io import compact_frame, load_data, results_to_excel
from driversignal.ui.plotting import FITTED_TOP_INFLUENCE, fitted_points
from driversignal.validation import prepare_item_spec


def _csv(rows: int) -> bytes:
    return b"respondent,service,recommend\n" + b"1,5,9\n2,3,7\n" * (rows // 2)


def _spec(items: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"item": items, "label": items, "scale": "", "reverse_scored": False})


def test_local_mode_accepts_input_beyond_the_demo_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNAL_PUBLIC", raising=False)
    rows = limits.DEMO_MAX_ROWS + 2
    frame = load_data(_csv(rows), name="wave.csv").tables["data"]
    assert len(frame) == rows
    assert frame["service"].dtype == np.int8  # rating scales are stored in one byte per answer
    items = [f"q{index}" for index in range(limits.DEMO_MAX_ITEMS + 5)]
    assert len(prepare_item_spec(_spec(items), items)) == limits.DEMO_MAX_ITEMS + 5
    payload = json.dumps([{"a": index, "b": "x" * 40} for index in range(5)]).encode()
    monkeypatch.setattr(limits, "DEMO_MAX_JSON_MB", 0)  # irrelevant locally
    assert len(load_data(payload, name="survey.json").tables["data"]) == 5


def test_public_demo_enforces_its_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNAL_PUBLIC", "1")
    with pytest.raises(DataProblem, match="public demo"):
        load_data(_csv(limits.DEMO_MAX_ROWS + 2), name="wave.csv")
    items = [f"q{index}" for index in range(limits.DEMO_MAX_ITEMS + 1)]
    with pytest.raises(DataProblem, match="downloaded app has no built-in limit"):
        prepare_item_spec(_spec(items), items)
    monkeypatch.setattr(limits, "DEMO_MAX_JSON_MB", 0)
    with pytest.raises(DataProblem, match="JSON uploads are limited"):
        load_data(json.dumps([{"a": 1}]).encode(), name="survey.json")
    with pytest.raises(DataProblem, match="at most 20 scored drivers"):
        limits.check_drivers(limits.DEMO_MAX_DRIVERS + 1)


def test_memory_errors_become_a_plain_message() -> None:
    assert "not enough memory" in friendly_message(MemoryError())


def test_semicolon_csv_uses_the_fast_parser_with_detected_delimiter() -> None:
    frame = load_data(b"id;score;comment\n1;4;fine\n2;5;good, really\n", name="survey.csv").tables["data"]
    assert frame.columns.tolist() == ["id", "score", "comment"]
    assert frame["comment"].tolist() == ["fine", "good, really"]


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


def test_excel_export_notes_its_row_limit_while_csv_keeps_every_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(survey_io, "EXCEL_MAX_DATA_ROWS", 10)
    table = pd.DataFrame({"source_row": range(25)})
    workbook = pd.ExcelFile(BytesIO(results_to_excel({"Influence diagnostics": table})))
    assert len(workbook.parse("Influence diagnostics")) == 10
    note = workbook.parse("Excel row limit")
    assert note.loc[0, "rows_in_table"] == 25


def test_residual_chart_draws_a_labelled_subset_of_many_rows() -> None:
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
    points = fitted_points(fitted, max_points=1000)
    assert len(points) == 1000
    assert set(fitted["cooks_distance"].nlargest(FITTED_TOP_INFLUENCE).index) <= set(points.index)


@pytest.mark.parametrize("duplicate", [False, True])
def test_chunked_model_path_matches_the_statsmodels_path(monkeypatch: pytest.MonkeyPatch, duplicate: bool) -> None:
    from driversignal import drivers

    rng = np.random.default_rng(5)
    x = rng.normal(size=(600, 3))
    y = x @ [1.0, -0.5, 0.2] + rng.normal(size=600) * (1 + np.abs(x[:, 0]))
    frame = pd.DataFrame({"y": y, "a": x[:, 0], "b": x[:, 1] * 3 + 2, "c": x[:, 2]})
    frame.loc[[3, 7], "a"] = np.nan
    columns = ["a", "b", "c"]
    if duplicate:
        frame["d"] = frame["a"] * 2 + 1
        columns.append("d")
    standard = drivers.fit_driver_model(frame, "y", columns)
    monkeypatch.setattr(drivers, "LARGE_MODEL_ROWS", 10)
    monkeypatch.setattr(drivers, "MODEL_CHUNK_ROWS", 37)
    chunked = drivers.fit_driver_model(frame, "y", columns)
    assert chunked.inference_valid == standard.inference_valid == (not duplicate)
    pd.testing.assert_frame_equal(chunked.coefficients, standard.coefficients, rtol=1e-8)
    pd.testing.assert_frame_equal(chunked.fitted, standard.fitted, rtol=1e-8, atol=1e-10)
    metrics = ["R-squared", "Adjusted R-squared", "Five-fold CV R-squared", "Design rank", "Cook's-distance flags"]
    left = chunked.metrics.set_index("metric").loc[metrics, "value"]
    right = standard.metrics.set_index("metric").loc[metrics, "value"]
    assert left.to_numpy() == pytest.approx(right.to_numpy(), rel=1e-8)


def test_large_tables_stream_into_json_with_the_same_values(monkeypatch: pytest.MonkeyPatch) -> None:
    table = pd.DataFrame({"source_row": [2, 3, 4], "leverage": [0.1, np.inf, np.nan], "label": ["a", "b", "c"]})
    small = json.loads(survey_io.results_to_json({"Influence": table}, {"note": 1}))
    monkeypatch.setattr(survey_io, "JSON_STREAM_ROWS", 1)
    streamed = json.loads(survey_io.results_to_json({"Influence": table}, {"note": 1}))
    assert streamed == small
    assert streamed["Influence"][1]["leverage"] is None
