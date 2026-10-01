from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from driversignal.examples import build_template, demo_csv_bytes, template_csv_bytes, template_xlsx_bytes


ROOT = Path(__file__).resolve().parents[1]


def test_demo_is_deterministic_shape_and_valid_ranges() -> None:
    frame = pd.read_csv(ROOT / "examples" / "demo_customer_experience_survey.csv")
    assert len(frame) == 520
    assert frame["respondent_id"].is_unique
    assert frame["recommend_0_10"].dropna().between(0, 10).all()
    item_columns = frame.filter(regex=r"^(service|value|ease|trust)_").columns
    assert frame[item_columns].stack().between(1, 7).all()


def test_demo_contains_missingness_to_exercise_retention_audit() -> None:
    frame = pd.read_csv(ROOT / "examples" / "demo_customer_experience_survey.csv")
    assert int(frame.isna().sum().sum()) > 0
    assert frame["recommend_0_10"].notna().all()


def test_csv_template_has_one_outcome_and_two_constructs() -> None:
    frame = pd.read_csv(ROOT / "examples" / "survey_template.csv")
    assert "satisfaction" in frame
    assert len([column for column in frame if column.startswith("service_")]) == 3
    assert len([column for column in frame if column.startswith("value_")]) == 3


def test_in_app_demo_and_templates_match_the_committed_examples() -> None:
    # The app generates these in memory (they must work from an installed package without examples/).
    assert demo_csv_bytes() == (ROOT / "examples" / "demo_customer_experience_survey.csv").read_bytes()
    assert template_csv_bytes() == (ROOT / "examples" / "survey_template.csv").read_bytes()
    survey, setup = build_template()
    workbook = pd.read_excel(BytesIO(template_xlsx_bytes()), sheet_name=None)
    assert list(workbook) == ["Survey", "Item setup example"]
    pd.testing.assert_frame_equal(workbook["Survey"], survey, check_dtype=False)
    committed = pd.read_excel(ROOT / "examples" / "survey_template.xlsx", sheet_name=None)
    for sheet, frame in workbook.items():
        pd.testing.assert_frame_equal(frame, committed[sheet])
