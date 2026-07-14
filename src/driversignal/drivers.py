"""Standardized survey-driver regression and correlated-predictor importance."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .errors import DataProblem


@dataclass(frozen=True)
class DriverResult:
    """Portable outputs from one complete-case driver model."""

    coefficients: pd.DataFrame
    importance: pd.DataFrame
    metrics: pd.DataFrame
    vif: pd.DataFrame
    correlations: pd.DataFrame
    fitted: pd.DataFrame
    warnings: tuple[str, ...]
    importance_method: str
    inference_valid: bool


def _design(values: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(values)), values])


def _r_squared(y: np.ndarray, values: np.ndarray) -> float:
    centered_total = float(np.sum((y - y.mean()) ** 2))
    if centered_total <= np.finfo(float).eps:
        return float("nan")
    if values.shape[1] == 0:
        return 0.0
    design = _design(values)
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coefficients
    result = 1.0 - float(residuals @ residuals) / centered_total
    return float(min(1.0, max(0.0, result)))


def lmg_importance(
    predictors: pd.DataFrame,
    outcome: pd.Series,
    exact_limit: int = 10,
    permutations: int = 2000,
    seed: int = 2026,
) -> tuple[pd.DataFrame, str]:
    """Decompose model R² using exact or deterministic permutation Shapley values."""
    x = predictors.to_numpy(dtype=float)
    y = outcome.to_numpy(dtype=float)
    names = list(predictors.columns)
    p = len(names)
    if p < 1:
        raise DataProblem("Select at least one usable driver.")
    centered_x = x - x.mean(axis=0)
    centered_y = y - y.mean()
    gram = centered_x.T @ centered_x
    cross = centered_x.T @ centered_y
    total = float(centered_y @ centered_y)
    if total <= np.finfo(float).eps:
        raise DataProblem("The outcome does not vary enough for relative importance.")

    @lru_cache(maxsize=None)
    def subset_r2(mask: int) -> float:
        columns = [index for index in range(p) if mask & (1 << index)]
        if not columns:
            return 0.0
        subset_gram = gram[np.ix_(columns, columns)]
        subset_cross = cross[columns]
        coefficients, *_ = np.linalg.lstsq(subset_gram, subset_cross, rcond=None)
        explained = float(subset_cross @ coefficients)
        return float(min(1.0, max(0.0, explained / total)))

    full_r2 = subset_r2((1 << p) - 1)

    contributions = np.zeros(p, dtype=float)
    if p <= exact_limit:
        factorial = [math.factorial(value) for value in range(p + 1)]
        denominator = factorial[p]
        for driver in range(p):
            bit = 1 << driver
            for mask in range(1 << p):
                if mask & bit:
                    continue
                size = int(mask.bit_count())
                weight = factorial[size] * factorial[p - size - 1] / denominator
                contributions[driver] += weight * (subset_r2(mask | bit) - subset_r2(mask))
        method = f"Exact LMG/Shapley over all {1 << p:,} predictor subsets"
    else:
        if permutations < 1:
            raise DataProblem("Approximate importance needs at least one permutation.")
        rng = np.random.default_rng(seed)
        for _ in range(permutations):
            mask = 0
            previous = 0.0
            for driver in rng.permutation(p):
                mask |= 1 << int(driver)
                current = subset_r2(mask)
                contributions[int(driver)] += current - previous
                previous = current
        contributions /= float(permutations)
        method = f"Approximate LMG/Shapley over {permutations:,} deterministic permutations (seed {seed})"

    contributions[np.abs(contributions) < 1e-12] = 0.0
    contributions = np.maximum(contributions, 0.0)
    total = float(contributions.sum())
    if np.isfinite(full_r2) and full_r2 > 0 and total > 0:
        contributions *= full_r2 / total
    shares = contributions / full_r2 * 100.0 if np.isfinite(full_r2) and full_r2 > 0 else np.zeros(p)
    table = pd.DataFrame(
        {
            "driver": names,
            "r2_contribution": contributions,
            "share_of_explained_percent": shares,
            "full_model_r2": full_r2,
        }
    )
    table["importance_rank"] = table["r2_contribution"].rank(method="min", ascending=False).astype(int)
    return table.sort_values(["r2_contribution", "driver"], ascending=[False, True]).reset_index(drop=True), method


def _vif_table(predictors: pd.DataFrame) -> pd.DataFrame:
    values = predictors.to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for index, name in enumerate(predictors.columns):
        if values.shape[1] == 1:
            vif = 1.0
        else:
            others = np.delete(values, index, axis=1)
            r2 = _r_squared(values[:, index], others)
            vif = float("inf") if not np.isfinite(r2) or r2 >= 1.0 - 1e-12 else 1.0 / (1.0 - r2)
        if not np.isfinite(vif):
            level = "Not identifiable"
        elif vif >= 10:
            level = "Severe overlap"
        elif vif >= 5:
            level = "High overlap"
        elif vif >= 3:
            level = "Moderate overlap"
        else:
            level = "Limited overlap"
        rows.append({"driver": name, "vif": vif, "diagnostic": level})
    return pd.DataFrame(rows).sort_values("vif", ascending=False).reset_index(drop=True)


def _cross_validated_metrics(
    predictors: np.ndarray,
    outcome: np.ndarray,
    folds: int = 5,
    seed: int = 2026,
) -> tuple[float, float]:
    n = len(outcome)
    if n < max(30, predictors.shape[1] * 5) or folds < 2:
        return float("nan"), float("nan")
    folds = min(folds, n)
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    assignments = np.empty(n, dtype=int)
    assignments[order] = np.arange(n) % folds
    predictions = np.full(n, np.nan)
    for fold in range(folds):
        test = assignments == fold
        train = ~test
        coefficients, *_ = np.linalg.lstsq(_design(predictors[train]), outcome[train], rcond=None)
        predictions[test] = _design(predictors[test]) @ coefficients
    residuals = outcome - predictions
    total = float(np.sum((outcome - outcome.mean()) ** 2))
    cv_r2 = 1.0 - float(residuals @ residuals) / total if total > np.finfo(float).eps else float("nan")
    cv_rmse = float(np.sqrt(np.mean(residuals**2)))
    return float(cv_r2), cv_rmse


def fit_driver_model(
    model_frame: pd.DataFrame,
    outcome_column: str,
    predictor_columns: list[str],
    confidence: float = 0.95,
    exact_importance_limit: int = 10,
    importance_permutations: int = 2000,
    seed: int = 2026,
) -> DriverResult:
    """Fit standardized OLS with HC3 uncertainty and LMG relative importance."""
    if outcome_column not in model_frame:
        raise DataProblem("The selected outcome was not found in the analysis table.")
    if not predictor_columns:
        raise DataProblem("Select at least one driver.")
    if outcome_column in predictor_columns or len(set(predictor_columns)) != len(predictor_columns):
        raise DataProblem("The outcome and drivers must be distinct, with no repeated drivers.")
    missing = [column for column in predictor_columns if column not in model_frame]
    if missing:
        raise DataProblem("Driver columns were not found: " + ", ".join(missing[:5]) + ".")

    numeric = model_frame[[outcome_column, *predictor_columns]].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.replace([np.inf, -np.inf], np.nan)
    if numeric[outcome_column].dropna().nunique() < 2:
        raise DataProblem("The outcome does not vary in the usable source rows.")
    warnings: list[str] = []
    usable: list[str] = []
    dropped: list[str] = []
    for column in predictor_columns:
        paired = numeric[[outcome_column, column]].dropna(axis=0, how="any")[column]
        if paired.nunique() < 2 or float(paired.std(ddof=0)) <= np.finfo(float).eps:
            dropped.append(column)
        else:
            usable.append(column)
    if not usable:
        raise DataProblem("None of the selected drivers varies alongside a usable outcome.")

    # A predictor can become constant only after the joint missing-data rule is applied. Remove one at a time and
    # rebuild the sample so another predictor is not discarded merely because the first blocked informative rows.
    while True:
        selected = numeric[[outcome_column, *usable]].dropna(axis=0, how="any")
        constant = next(
            (
                column
                for column in usable
                if selected[column].nunique() < 2
                or float(selected[column].std(ddof=0)) <= np.finfo(float).eps
            ),
            None,
        )
        if constant is None:
            break
        usable.remove(constant)
        dropped.append(constant)
        if not usable:
            raise DataProblem("None of the selected drivers varies in the retained rows.")

    if dropped:
        warnings.append("Constant driver(s) were removed before the final complete-case sample: " + ", ".join(dropped) + ".")
    if len(usable) > 20:
        raise DataProblem("Use at most 20 scored drivers in one model so importance remains auditable.")

    y = selected[outcome_column].astype(float)
    if y.nunique() < 2:
        raise DataProblem("The outcome does not vary in the retained rows.")
    x = selected[usable].astype(float)
    n = len(selected)
    p = len(usable)
    if n <= p + 1:
        raise DataProblem(f"This model has {p} drivers but only {n} complete rows. It needs more rows than parameters.")
    stability_target = max(50, 10 * (p + 1))
    if n < stability_target:
        warnings.append(
            f"Only {n:,} complete rows remain; {stability_target:,} is a useful stability check for this model size, not a theorem."
        )

    x_mean = x.mean(axis=0)
    x_sd = x.std(axis=0, ddof=0)
    y_mean = float(y.mean())
    y_sd = float(y.std(ddof=0))
    x_standardized = (x - x_mean) / x_sd
    y_standardized = (y - y_mean) / y_sd
    internal_names = [f"__driver_{index}" for index in range(p)]
    standardized_model = x_standardized.copy()
    standardized_model.columns = internal_names
    raw_model = x.copy()
    raw_model.columns = internal_names

    standardized_design = sm.add_constant(standardized_model, has_constant="add")
    standard_fit = sm.OLS(y_standardized, standardized_design).fit(cov_type="HC3")
    raw_design = sm.add_constant(raw_model, has_constant="add")
    raw_fit = sm.OLS(y, raw_design).fit(cov_type="HC3")
    base_fit = sm.OLS(y, raw_design).fit()

    design_rank = int(np.linalg.matrix_rank(standardized_design.to_numpy(dtype=float)))
    expected_rank = p + 1
    inference_valid = design_rank == expected_rank
    if not inference_valid:
        warnings.append(
            "The driver matrix is rank-deficient. Individual coefficients are not uniquely identified; interpret only the shared model fit and grouped importance with caution."
        )

    alpha = 1.0 - confidence
    standard_ci = standard_fit.conf_int(alpha=alpha)
    raw_ci = raw_fit.conf_int(alpha=alpha)
    coefficient_rows: list[dict[str, object]] = []
    for name, internal_name in zip(usable, internal_names, strict=True):
        beta = float(standard_fit.params[internal_name])
        reported_beta = beta if inference_valid else float("nan")
        coefficient_rows.append(
            {
                "driver": name,
                "standardized_beta": reported_beta,
                "ci_low": float(standard_ci.loc[internal_name, 0]) if inference_valid else float("nan"),
                "ci_high": float(standard_ci.loc[internal_name, 1]) if inference_valid else float("nan"),
                "p_value_exploratory": float(standard_fit.pvalues[internal_name]) if inference_valid else float("nan"),
                "raw_coefficient": float(raw_fit.params[internal_name]) if inference_valid else float("nan"),
                "raw_ci_low": float(raw_ci.loc[internal_name, 0]) if inference_valid else float("nan"),
                "raw_ci_high": float(raw_ci.loc[internal_name, 1]) if inference_valid else float("nan"),
                "direction": (
                    "Not identified"
                    if not inference_valid
                    else "Positive"
                    if beta > 1e-12
                    else "Negative"
                    if beta < -1e-12
                    else "Near zero"
                ),
                "hc3_inference_status": "Available" if inference_valid else "Not uniquely identified",
            }
        )
    coefficients = pd.DataFrame(coefficient_rows)

    importance, importance_method = lmg_importance(
        x,
        y,
        exact_limit=exact_importance_limit,
        permutations=importance_permutations,
        seed=seed,
    )
    importance = importance.merge(
        coefficients[["driver", "standardized_beta", "direction"]], on="driver", how="left", validate="one_to_one"
    )
    vif = _vif_table(x)
    if np.isinf(vif["vif"]).any() or (vif["vif"] >= 10).any():
        warnings.append("At least one VIF is 10 or higher; separate coefficient estimates may be unstable.")
    elif (vif["vif"] >= 5).any():
        warnings.append("At least one VIF is 5 or higher; inspect overlap before separating driver effects.")

    fitted_values = np.asarray(base_fit.fittedvalues, dtype=float)
    residuals = np.asarray(base_fit.resid, dtype=float)
    rmse = float(np.sqrt(np.mean(residuals**2)))
    mae = float(np.mean(np.abs(residuals)))
    cv_r2, cv_rmse = _cross_validated_metrics(x.to_numpy(dtype=float), y.to_numpy(dtype=float), seed=seed)
    if not np.isfinite(cv_r2):
        warnings.append("The retained sample is too small for the built-in deterministic five-fold check.")
    elif cv_r2 < 0:
        warnings.append("Cross-validated R² is below zero; this model predicts held-out rows worse than their mean.")

    condition_number = float(np.linalg.cond(standardized_design.to_numpy(dtype=float)))
    influence = base_fit.get_influence()
    leverage = np.asarray(influence.hat_matrix_diag, dtype=float)
    cooks = np.asarray(influence.cooks_distance[0], dtype=float)
    source_rows = selected.index.to_series().map(lambda value: int(value) + 2 if isinstance(value, (int, np.integer)) else str(value))
    fitted = pd.DataFrame(
        {
            "source_row": source_rows.to_numpy(),
            "observed": y.to_numpy(dtype=float),
            "fitted": fitted_values,
            "residual": residuals,
            "leverage": leverage,
            "cooks_distance": cooks,
        }
    )
    influential = int((cooks > 4.0 / n).sum())
    high_leverage = int((leverage > 2.0 * (p + 1) / n).sum())
    if influential:
        warnings.append(f"{influential:,} row(s) exceed the Cook's-distance screen of 4/n; inspect sensitivity.")

    metrics = pd.DataFrame(
        [
            {"metric": "Usable respondents", "value": n, "note": "One shared complete-case sample"},
            {"metric": "Drivers", "value": p, "note": "After constant columns were removed"},
            {"metric": "R-squared", "value": float(base_fit.rsquared), "note": "In-sample variance explained"},
            {"metric": "Adjusted R-squared", "value": float(base_fit.rsquared_adj), "note": "Penalizes model size"},
            {"metric": "RMSE", "value": rmse, "note": "Outcome units, in sample"},
            {"metric": "MAE", "value": mae, "note": "Outcome units, in sample"},
            {"metric": "Five-fold CV R-squared", "value": cv_r2, "note": "Deterministic held-out check"},
            {"metric": "Five-fold CV RMSE", "value": cv_rmse, "note": "Outcome units, held out"},
            {"metric": "Design rank", "value": design_rank, "note": f"Expected {expected_rank}"},
            {"metric": "Condition number", "value": condition_number, "note": "Standardized design"},
            {"metric": "Cook's-distance flags", "value": influential, "note": "Threshold 4/n"},
            {"metric": "High-leverage flags", "value": high_leverage, "note": "Threshold 2(p+1)/n"},
        ]
    )

    correlations = x.corr().rename_axis("driver").reset_index()
    return DriverResult(
        coefficients=coefficients.sort_values("standardized_beta", ascending=False).reset_index(drop=True),
        importance=importance,
        metrics=metrics,
        vif=vif,
        correlations=correlations,
        fitted=fitted,
        warnings=tuple(dict.fromkeys(warnings)),
        importance_method=importance_method,
        inference_valid=inference_valid,
    )
