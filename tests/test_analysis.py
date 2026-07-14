from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from driversignal.analysis import analyze_survey, nps_summary
from driversignal.errors import DataProblem
from driversignal.validation import default_item_spec


ROOT = Path(__file__).resolve().parents[1]


def _demo() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_csv(ROOT / "examples" / "demo_customer_experience_survey.csv")
    items = [column for column in frame if column.split("_")[0] in {"service", "value", "ease", "trust"}]
    return frame, default_item_spec(items)


def test_demo_runs_complete_nps_workflow() -> None:
    frame, spec = _demo()
    analysis = analyze_survey(
        frame,
        "recommend_0_10",
        spec,
        minimum_answered_fraction=2 / 3,
        reliability_bootstrap_repetitions=30,
        nps_bootstrap_repetitions=200,
    )
    assert analysis.predictor_columns == ("Service", "Value", "Ease", "Trust")
    assert analysis.driver_result.importance.iloc[0]["driver"] == "Service"
    assert len(analysis.scale_summary) == 4
    assert analysis.scale_summary["cronbach_alpha"].between(0.75, 0.9).all()
    assert "NPS" in analysis.outcome_summary["metric"].tolist()


def test_nps_boundaries_are_classified_exactly() -> None:
    metrics, composition = nps_summary(pd.Series([0, 6, 7, 8, 9, 10]), bootstrap_repetitions=20)
    counts = composition.set_index("category")["respondents"]
    assert counts["Detractors (0–6)"] == 2
    assert counts["Passives (7–8)"] == 2
    assert counts["Promoters (9–10)"] == 2
    assert metrics.set_index("metric").loc["NPS", "value"] == pytest.approx(0.0)


def test_nps_known_fixture_matches_formula() -> None:
    metrics, _ = nps_summary(pd.Series([10, 9, 8, 6]), bootstrap_repetitions=20)
    assert metrics.set_index("metric").loc["NPS", "value"] == pytest.approx(25.0)


@pytest.mark.parametrize("values", [[-1, 5, 9], [2, 7, 11], [1.5, 8, 9]])
def test_invalid_nps_scores_are_rejected(values: list[float]) -> None:
    with pytest.raises(DataProblem, match="whole numbers"):
        nps_summary(pd.Series(values))


def test_nps_bootstrap_is_deterministic() -> None:
    values = pd.Series([0, 3, 6, 7, 8, 9, 10] * 12)
    first, _ = nps_summary(values, bootstrap_repetitions=200, seed=18)
    second, _ = nps_summary(values, bootstrap_repetitions=200, seed=18)
    first_values = first.set_index("metric")["value"]
    second_values = second.set_index("metric")["value"]
    assert first_values["NPS bootstrap 95% low"] == pytest.approx(second_values["NPS bootstrap 95% low"])
    assert first_values["NPS bootstrap 95% high"] == pytest.approx(second_values["NPS bootstrap 95% high"])


def test_reverse_scored_item_enters_construct_in_correct_direction() -> None:
    frame = pd.DataFrame(
        {
            "outcome": [1, 2, 3, 4, 5, 6] * 4,
            "ease_good": [1, 2, 3, 4, 5, 6] * 4,
            "ease_reverse_bad": [7, 6, 5, 4, 3, 2] * 4,
        }
    )
    spec = pd.DataFrame(
        {
            "item": ["ease_good", "ease_reverse_bad"],
            "label": ["Good", "Bad"],
            "scale": ["Ease", "Ease"],
            "reverse_scored": [False, True],
        }
    )
    analysis = analyze_survey(
        frame,
        "outcome",
        spec,
        outcome_kind="Satisfaction / other numeric rating",
        reliability_bootstrap_repetitions=20,
    )
    assert analysis.scale_summary.iloc[0]["cronbach_alpha"] == pytest.approx(1.0)
    assert analysis.driver_result.coefficients.iloc[0]["standardized_beta"] > 0.99


def test_outcome_cannot_be_its_own_driver() -> None:
    frame = pd.DataFrame({"outcome": np.arange(20), "x": np.arange(20)})
    spec = default_item_spec(["outcome"])
    with pytest.raises(DataProblem, match="own drivers"):
        analyze_survey(frame, "outcome", spec, outcome_kind="Satisfaction")


def test_grouped_item_outside_declared_scale_is_rejected() -> None:
    frame = pd.DataFrame({"outcome": np.arange(20), "scale_a": [1] * 19 + [8], "scale_b": [2] * 20})
    spec = default_item_spec(["scale_a", "scale_b"])
    with pytest.raises(DataProblem, match="outside the declared"):
        analyze_survey(frame, "outcome", spec, outcome_kind="Satisfaction", scale_minimum=1, scale_maximum=7)


def test_driver_label_cannot_duplicate_outcome_column_name() -> None:
    frame = pd.DataFrame({"outcome": np.arange(30), "item": np.arange(30)})
    spec = pd.DataFrame(
        {"item": ["item"], "label": ["outcome"], "scale": [""], "reverse_scored": [False]}
    )
    with pytest.raises(DataProblem, match="same name"):
        analyze_survey(frame, "outcome", spec, outcome_kind="Satisfaction")


def test_listwise_retention_is_reported() -> None:
    frame, spec = _demo()
    analysis = analyze_survey(
        frame,
        "recommend_0_10",
        spec,
        minimum_answered_fraction=1.0,
        reliability_bootstrap_repetitions=20,
        nps_bootstrap_repetitions=20,
    )
    retained = analysis.retention.set_index("stage").loc["Rows complete for full model", "rows"]
    assert retained < len(frame)
    assert retained == len(analysis.driver_result.fitted)


def test_partial_construct_rule_can_retain_a_row() -> None:
    rng = np.random.default_rng(13)
    n = 80
    base = rng.uniform(2, 6, size=n)
    frame = pd.DataFrame(
        {
            "outcome": base + rng.normal(0, 0.2, n),
            "service_a": base,
            "service_b": np.clip(base + rng.normal(0, 0.2, n), 1, 7),
            "service_c": np.clip(base + rng.normal(0, 0.2, n), 1, 7),
        }
    )
    frame.loc[0, "service_a"] = np.nan
    spec = default_item_spec(["service_a", "service_b", "service_c"])
    strict = analyze_survey(
        frame, "outcome", spec, outcome_kind="Satisfaction", reliability_bootstrap_repetitions=20
    )
    partial = analyze_survey(
        frame,
        "outcome",
        spec,
        outcome_kind="Satisfaction",
        minimum_answered_fraction=2 / 3,
        reliability_bootstrap_repetitions=20,
    )
    assert len(partial.driver_result.fitted) == len(strict.driver_result.fitted) + 1


def test_construct_and_source_items_do_not_both_enter_model() -> None:
    frame, spec = _demo()
    analysis = analyze_survey(
        frame,
        "recommend_0_10",
        spec,
        minimum_answered_fraction=2 / 3,
        reliability_bootstrap_repetitions=20,
        nps_bootstrap_repetitions=20,
    )
    assert not set(spec["item"]).intersection(set(analysis.predictor_columns))


def test_retention_uses_only_nonconstant_model_drivers() -> None:
    rng = np.random.default_rng(44)
    x = rng.normal(size=100)
    frame = pd.DataFrame(
        {
            "outcome": 2 * x + rng.normal(0, 0.3, size=100),
            "signal": x,
            "constant_with_missing": 4.0,
        }
    )
    frame.loc[50:, "constant_with_missing"] = np.nan
    spec = pd.DataFrame(
        {
            "item": ["signal", "constant_with_missing"],
            "label": ["Signal", "Constant"],
            "scale": ["", ""],
            "reverse_scored": [False, False],
        }
    )
    analysis = analyze_survey(
        frame,
        "outcome",
        spec,
        outcome_kind="Satisfaction / other numeric rating",
        reliability_bootstrap_repetitions=20,
    )
    retained = analysis.retention.set_index("stage").loc["Rows complete for full model", "rows"]
    assert retained == 100
    assert retained == len(analysis.driver_result.fitted)
    assert analysis.predictor_columns == ("Signal",)
    assert analysis.missingness.set_index("field").loc["Constant", "missing_rows"] == 50
