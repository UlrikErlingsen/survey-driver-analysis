from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from driversignal.errors import DataProblem
from driversignal.reliability import (
    analyze_reliability,
    bootstrap_alpha,
    cronbach_alpha,
    reliability_label,
    reverse_score,
    standardized_alpha,
)


def test_perfect_parallel_items_have_alpha_one() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 2, 3, 4], "c": [1, 2, 3, 4]})
    assert cronbach_alpha(frame) == pytest.approx(1.0)


def test_standardized_two_item_alpha_matches_spearman_brown_form() -> None:
    frame = pd.DataFrame({"a": [1, 2, 4, 5, 7], "b": [2, 1, 5, 4, 8]})
    alpha, mean_r = standardized_alpha(frame)
    assert alpha == pytest.approx(2 * mean_r / (1 + mean_r))


def test_reverse_scoring_uses_declared_endpoints() -> None:
    result = reverse_score(pd.Series([1.0, 3.0, 7.0, np.nan]), 1, 7)
    assert result.iloc[:3].tolist() == [7.0, 5.0, 1.0]
    assert np.isnan(result.iloc[3])


def test_reverse_scoring_rejects_out_of_range_values() -> None:
    with pytest.raises(DataProblem, match="outside"):
        reverse_score(pd.Series([0, 4, 7]), 1, 7)


def test_negative_alpha_is_preserved_and_warned() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [5, 4, 3, 2, 1], "c": [1, 1, 2, 2, 3]})
    result = analyze_reliability(frame, "Conflict", bootstrap_repetitions=20)
    assert result.alpha < 0
    assert any("negative" in warning.lower() for warning in result.warnings)


def test_corrected_item_total_excludes_the_focal_item() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [1, 1, 3, 4, 5], "c": [2, 2, 2, 4, 5]})
    result = analyze_reliability(frame, "Scale", bootstrap_repetitions=20)
    observed = result.items.set_index("item").loc["a", "corrected_item_total"]
    expected = frame["a"].corr(frame[["b", "c"]].sum(axis=1))
    assert observed == pytest.approx(expected)


def test_alpha_if_deleted_matches_direct_recalculation() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [1, 2, 4, 4, 5], "c": [2, 2, 3, 5, 5]})
    result = analyze_reliability(frame, "Scale", bootstrap_repetitions=20)
    observed = result.items.set_index("item").loc["b", "alpha_if_deleted"]
    assert observed == pytest.approx(cronbach_alpha(frame[["a", "c"]]))


def test_reliability_uses_one_listwise_complete_sample() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, np.nan], "b": [1, 2, np.nan, 4], "c": [1, 2, 3, 4]})
    result = analyze_reliability(frame, "Scale", bootstrap_repetitions=20)
    assert result.n_complete == 2


def test_one_item_scale_is_rejected_by_reliability_function() -> None:
    with pytest.raises(DataProblem, match="at least two"):
        analyze_reliability(pd.DataFrame({"a": [1, 2, 3]}), "Single")


def test_zero_total_variance_returns_structured_not_estimable_result() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [4, 3, 2, 1]})
    result = analyze_reliability(frame, "Zero total", bootstrap_repetitions=20)
    assert np.isnan(result.alpha)
    assert reliability_label(result.alpha) == "Not estimable"


def test_bootstrap_interval_is_deterministic() -> None:
    rng = np.random.default_rng(3)
    base = rng.normal(size=80)
    frame = pd.DataFrame({"a": base + rng.normal(0, 0.4, 80), "b": base + rng.normal(0, 0.4, 80)})
    first = bootstrap_alpha(frame, repetitions=80, seed=19)
    second = bootstrap_alpha(frame, repetitions=80, seed=19)
    assert first == pytest.approx(second)


def test_oversized_bootstrap_is_blocked_instead_of_silently_reduced() -> None:
    frame = pd.DataFrame({"a": np.arange(1000), "b": np.arange(1000)})
    with pytest.raises(DataProblem, match="too large"):
        bootstrap_alpha(frame, repetitions=30_000)


@pytest.mark.parametrize(
    ("alpha", "label"),
    [(-0.2, "Contradictory"), (0.55, "Low"), (0.75, "Useful"), (0.97, "redundancy")],
)
def test_reliability_labels_are_contextual(alpha: float, label: str) -> None:
    assert label.lower() in reliability_label(alpha).lower()
