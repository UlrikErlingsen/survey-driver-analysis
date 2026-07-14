from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pytest

from driversignal.errors import DataProblem
from driversignal.io import load_data, results_to_excel, results_to_json, safe_for_spreadsheet, tables_to_csv_zip
from driversignal.reporting import privacy_safe_influence
from driversignal.validation import default_item_spec, numeric_candidates, prepare_item_spec, required_answers


def test_load_csv_bytes() -> None:
    loaded = load_data(b"a,b\n1,2\n3,4\n", name="survey.csv")
    assert loaded.tables["data"].shape == (2, 2)


def test_load_json_list() -> None:
    loaded = load_data(json.dumps([{"a": 1}, {"a": 2}]).encode(), name="survey.json")
    assert loaded.tables["data"]["a"].tolist() == [1, 2]


def test_load_column_oriented_json_object() -> None:
    payload = json.dumps({"outcome": [4, 5], "driver": [2, 3]}).encode()
    loaded = load_data(payload, name="survey.json")
    assert loaded.tables["data"].to_dict(orient="list") == {"outcome": [4, 5], "driver": [2, 3]}


def test_load_excel_with_multiple_sheets() -> None:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Survey", index=False)
        pd.DataFrame({"item": ["a"]}).to_excel(writer, sheet_name="Setup", index=False)
    loaded = load_data(output.getvalue(), name="survey.xlsx")
    assert list(loaded.tables) == ["Survey", "Setup"]


def test_unsupported_and_empty_files_are_rejected() -> None:
    with pytest.raises(DataProblem, match="CSV"):
        load_data(b"hello", name="survey.txt")
    with pytest.raises(DataProblem, match="empty"):
        load_data(b"", name="survey.csv")


def test_spreadsheet_formula_injection_is_neutralized() -> None:
    frame = pd.DataFrame({"=unsafe_header": ["=SUM(A1:A2)", " +cmd", "normal", "@mention"]})
    safe = safe_for_spreadsheet(frame)
    assert safe.columns[0].startswith("'")
    assert safe.iloc[0, 0].startswith("'")
    assert safe.iloc[1, 0].startswith("'")
    assert safe.iloc[2, 0] == "normal"
    assert safe.iloc[3, 0].startswith("'")


def test_excel_export_contains_named_sheet() -> None:
    data = results_to_excel({"Driver results": pd.DataFrame({"driver": ["Service"], "beta": [0.4]})})
    workbook = pd.ExcelFile(BytesIO(data))
    assert workbook.sheet_names == ["Driver results"]


def test_json_export_replaces_nonfinite_values_with_null() -> None:
    data = results_to_json({"metrics": pd.DataFrame({"value": [np.nan, np.inf, 1.0]})}, {"warning": np.nan})
    decoded = json.loads(data)
    assert decoded["metrics"][0]["value"] is None
    assert decoded["metrics"][1]["value"] is None
    assert decoded["analysis_metadata"]["warning"] is None


def test_csv_zip_contains_equivalent_table() -> None:
    data = tables_to_csv_zip({"Driver results": pd.DataFrame({"driver": ["Service"]})})
    with zipfile.ZipFile(BytesIO(data)) as archive:
        assert archive.namelist() == ["Driver_results.csv"]
        assert "Service" in archive.read("Driver_results.csv").decode()


def test_numeric_candidates_accept_numeric_strings_and_reject_text() -> None:
    frame = pd.DataFrame({"numeric": ["1", "2", None], "mixed": ["1", "bad", "3"], "text": ["a", "b", "c"]})
    assert numeric_candidates(frame) == ["numeric"]


def test_default_item_spec_infers_construct_and_reverse_hint() -> None:
    spec = default_item_spec(["ease_setup", "ease_reverse_effort", "price"])
    assert spec.loc[0, "scale"] == "Ease"
    assert bool(spec.loc[1, "reverse_scored"])
    assert spec.loc[2, "scale"] == ""


def test_item_spec_rejects_duplicate_items_and_name_conflicts() -> None:
    duplicate = pd.DataFrame(
        {"item": ["a", "a"], "label": ["A", "A2"], "scale": ["", ""], "reverse_scored": [False, False]}
    )
    with pytest.raises(DataProblem, match="only once"):
        prepare_item_spec(duplicate, ["a"])
    conflict = pd.DataFrame(
        {
            "item": ["a", "b"],
            "label": ["A", "Service"],
            "scale": ["Service", ""],
            "reverse_scored": [False, False],
        }
    )
    with pytest.raises(DataProblem, match="unique"):
        prepare_item_spec(conflict, ["a", "b"])


@pytest.mark.parametrize(("items", "fraction", "expected"), [(3, 1.0, 3), (3, 0.8, 3), (3, 2 / 3, 2), (5, 0.8, 4)])
def test_required_answers_rounds_up(items: int, fraction: float, expected: int) -> None:
    assert required_answers(items, fraction) == expected


def test_generated_excel_template_is_readable() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "survey_template.xlsx"
    loaded = load_data(path)
    assert {"Survey", "Item setup example"} == set(loaded.tables)


def test_portable_influence_table_excludes_reconstructable_outcome_values() -> None:
    fitted = pd.DataFrame(
        {
            "source_row": [2],
            "observed": [9.0],
            "fitted": [8.2],
            "residual": [0.8],
            "leverage": [0.03],
            "cooks_distance": [0.01],
        }
    )
    exported = privacy_safe_influence(fitted)
    assert exported.columns.tolist() == ["source_row", "leverage", "cooks_distance"]
    assert {"observed", "fitted", "residual"}.isdisjoint(exported.columns)
