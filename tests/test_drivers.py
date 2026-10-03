from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from driversignal.drivers import fit_driver_model, lmg_importance
from driversignal.errors import DataProblem


def _synthetic(seed: int = 4, n: int = 320) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    x3 = 0.45 * x1 + rng.normal(size=n)
    y = 2.2 * x1 - 1.1 * x2 + 0.25 * x3 + rng.normal(0, 0.65, size=n)
    return pd.DataFrame({"y": y, "x1": x1, "x2": x2, "x3": x3})


def test_model_recovers_known_signs_and_priority() -> None:
    frame = _synthetic()
    result = fit_driver_model(frame, "y", ["x1", "x2", "x3"])
    coefficients = result.coefficients.set_index("driver")
    assert coefficients.loc["x1", "standardized_beta"] > 0
    assert coefficients.loc["x2", "standardized_beta"] < 0
    assert result.importance.iloc[0]["driver"] == "x1"


def test_standardized_betas_are_invariant_to_affine_rescaling() -> None:
    frame = _synthetic()
    first = fit_driver_model(frame, "y", ["x1", "x2", "x3"])
    scaled = frame.assign(y=frame["y"] * 17 + 9, x1=frame["x1"] * 4 - 2)
    second = fit_driver_model(scaled, "y", ["x1", "x2", "x3"])
    left = first.coefficients.set_index("driver")["standardized_beta"].sort_index()
    right = second.coefficients.set_index("driver")["standardized_beta"].sort_index()
    assert left.to_numpy() == pytest.approx(right.to_numpy())


def test_exact_lmg_contributions_sum_to_full_model_r2() -> None:
    frame = _synthetic()
    table, method = lmg_importance(frame[["x1", "x2", "x3"]], frame["y"])
    assert table["r2_contribution"].sum() == pytest.approx(table["full_model_r2"].iloc[0])
    assert (table["r2_contribution"] >= 0).all()
    assert "Exact" in method


def test_identical_predictors_split_importance_equally_and_flag_rank() -> None:
    rng = np.random.default_rng(8)
    x = rng.normal(size=100)
    frame = pd.DataFrame({"y": x + rng.normal(0, 0.2, 100), "a": x, "b": x})
    result = fit_driver_model(frame, "y", ["a", "b"])
    importance = result.importance.set_index("driver")["r2_contribution"]
    assert importance["a"] == pytest.approx(importance["b"])
    assert not result.inference_valid
    assert np.isinf(result.vif["vif"]).all()
    assert result.coefficients["standardized_beta"].isna().all()
    assert result.coefficients["raw_coefficient"].isna().all()
    assert result.coefficients["direction"].eq("Not identified").all()
    assert result.importance["standardized_beta"].isna().all()


def test_correlated_predictors_surface_vif_warning() -> None:
    rng = np.random.default_rng(9)
    a = rng.normal(size=180)
    b = a + rng.normal(0, 0.05, 180)
    frame = pd.DataFrame({"y": a + rng.normal(size=180), "a": a, "b": b})
    result = fit_driver_model(frame, "y", ["a", "b"])
    assert result.vif["vif"].max() > 10
    assert any("VIF" in warning for warning in result.warnings)


def test_approximate_importance_is_reproducible_and_close_to_exact() -> None:
    frame = _synthetic(n=180)
    exact, _ = lmg_importance(frame[["x1", "x2", "x3"]], frame["y"], exact_limit=10)
    first, _ = lmg_importance(
        frame[["x1", "x2", "x3"]], frame["y"], exact_limit=1, permutations=3000, seed=31
    )
    second, _ = lmg_importance(
        frame[["x1", "x2", "x3"]], frame["y"], exact_limit=1, permutations=3000, seed=31
    )
    exact_values = exact.set_index("driver")["r2_contribution"].sort_index()
    first_values = first.set_index("driver")["r2_contribution"].sort_index()
    second_values = second.set_index("driver")["r2_contribution"].sort_index()
    assert first_values.to_numpy() == pytest.approx(second_values.to_numpy())
    assert first_values.to_numpy() == pytest.approx(exact_values.to_numpy(), abs=0.015)


def test_model_uses_one_complete_case_sample() -> None:
    frame = _synthetic(n=100)
    frame.loc[[0, 1], "x1"] = np.nan
    frame.loc[[2, 3, 4], "x2"] = np.nan
    result = fit_driver_model(frame, "y", ["x1", "x2", "x3"])
    usable = result.metrics.set_index("metric").loc["Usable respondents", "value"]
    assert usable == 95
    assert len(result.fitted) == 95


def test_constant_outcome_is_blocked() -> None:
    frame = pd.DataFrame({"y": [1.0] * 20, "x": np.arange(20)})
    with pytest.raises(DataProblem, match="does not vary"):
        fit_driver_model(frame, "y", ["x"])


def test_constant_predictor_is_removed_with_warning() -> None:
    frame = _synthetic(n=100).assign(constant=4.0)
    result = fit_driver_model(frame, "y", ["x1", "constant"])
    assert result.coefficients["driver"].tolist() == ["x1"]
    assert any("Constant driver" in warning for warning in result.warnings)


def test_missing_constant_predictor_does_not_discard_usable_rows() -> None:
    frame = _synthetic(n=100).assign(constant=4.0)
    frame.loc[50:, "constant"] = np.nan
    result = fit_driver_model(frame, "y", ["x1", "constant"])
    usable = result.metrics.set_index("metric").loc["Usable respondents", "value"]
    assert usable == 100
    assert result.coefficients["driver"].tolist() == ["x1"]


def test_too_few_rows_for_parameters_is_blocked() -> None:
    frame = pd.DataFrame({"y": [1, 2, 3], "a": [1, 3, 2], "b": [2, 1, 3]})
    with pytest.raises(DataProblem, match="more rows than parameters"):
        fit_driver_model(frame, "y", ["a", "b"])


def test_duplicate_predictor_selection_is_blocked() -> None:
    frame = _synthetic(n=40)
    with pytest.raises(DataProblem, match="distinct"):
        fit_driver_model(frame, "y", ["x1", "x1"])


def test_driver_named_const_is_safe() -> None:
    frame = _synthetic(n=80).rename(columns={"x1": "const"})
    result = fit_driver_model(frame, "y", ["const", "x2"])
    assert set(result.coefficients["driver"]) == {"const", "x2"}


def test_cross_validation_is_deterministic() -> None:
    frame = _synthetic(n=160)
    first = fit_driver_model(frame, "y", ["x1", "x2", "x3"], seed=17)
    second = fit_driver_model(frame, "y", ["x1", "x2", "x3"], seed=17)
    first_metrics = first.metrics.set_index("metric")["value"]
    second_metrics = second.metrics.set_index("metric")["value"]
    assert first_metrics["Five-fold CV R-squared"] == pytest.approx(second_metrics["Five-fold CV R-squared"])
    assert first_metrics["Five-fold CV RMSE"] == pytest.approx(second_metrics["Five-fold CV RMSE"])


def test_more_than_twenty_drivers_runs_locally_and_is_capped_in_the_public_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(2)
    frame = pd.DataFrame(rng.normal(size=(300, 22)), columns=["y", *[f"x{i}" for i in range(21)]])
    monkeypatch.delenv("SIGNAL_PUBLIC", raising=False)
    result = fit_driver_model(frame, "y", [f"x{i}" for i in range(21)], importance_permutations=200)
    assert len(result.importance) == 21
    assert "Approximate LMG/Shapley" in result.importance_method
    monkeypatch.setenv("SIGNAL_PUBLIC", "1")
    with pytest.raises(DataProblem, match="at most 20"):
        fit_driver_model(frame, "y", [f"x{i}" for i in range(21)])
