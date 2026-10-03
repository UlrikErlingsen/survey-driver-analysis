"""Standardized survey-driver regression and correlated-predictor importance."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

from .errors import DataProblem
from .limits import check_drivers


# Above this many complete respondents the regression, HC3 covariance, leverage, Cook's distance and cross-validation
# are computed in row chunks from a QR factor and cross-products instead of statsmodels' full design copies. The
# estimates are the same (one fit replaces three, standardized and raw results are exact rescalings of each other);
# memory stays near one copy of the predictors, so every respondent can enter the model.
LARGE_MODEL_ROWS = 200_000
MODEL_CHUNK_ROWS = 250_000


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


def _is_constant(values: np.ndarray) -> bool:
    """True when finite values cannot identify a slope: fewer than two distinct values or no spread."""
    return len(values) == 0 or values.min() == values.max() or float(np.std(values)) <= np.finfo(float).eps


def _design(values: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(values)), values])


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


def _gram_r_squared(gram: np.ndarray, target: int) -> float:
    """R² of one centered column regressed on the others, from the centered cross-product matrix."""
    total = float(gram[target, target])
    if total <= np.finfo(float).eps:
        return float("nan")
    others = [index for index in range(gram.shape[0]) if index != target]
    coefficients, *_ = np.linalg.lstsq(gram[np.ix_(others, others)], gram[others, target], rcond=None)
    return float(min(1.0, max(0.0, float(gram[target, others] @ coefficients) / total)))


def _vif_table(predictors: pd.DataFrame) -> pd.DataFrame:
    values = predictors.to_numpy(dtype=float)
    # Each auxiliary regression uses the p×p cross-product matrix, so VIF costs one pass over the rows.
    centered = values - values.mean(axis=0)
    gram = centered.T @ centered
    del centered
    rows: list[dict[str, object]] = []
    for index, name in enumerate(predictors.columns):
        if values.shape[1] == 1:
            vif = 1.0
        else:
            r2 = _gram_r_squared(gram, index)
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


def _chunks(n: int):
    for start in range(0, n, MODEL_CHUNK_ROWS):
        yield slice(start, min(start + MODEL_CHUNK_ROWS, n))


def _ols_large(x: np.ndarray, y: np.ndarray, confidence: float) -> dict[str, object]:
    """Standardized OLS with HC3 covariance, leverage and Cook's distance, accumulated over row chunks."""
    n, p = x.shape
    k = p + 1
    x_mean = x.mean(axis=0)
    x_sd = x.std(axis=0, ddof=0)
    y_mean = float(y.mean())
    y_sd = float(y.std(ddof=0))

    def design(rows: slice) -> np.ndarray:
        return np.column_stack([np.ones(rows.stop - rows.start), (x[rows] - x_mean) / x_sd])

    # A running QR factor of the standardized design gives its singular values (rank, condition number) as stably as
    # an SVD of the full matrix would, without materializing it.
    r_factor = np.zeros((0, k))
    cross = np.zeros(k)
    for rows in _chunks(n):
        block = design(rows)
        r_factor = np.linalg.qr(np.vstack([r_factor, block]), mode="r")
        cross += block.T @ ((y[rows] - y_mean) / y_sd)
    singular = np.linalg.svd(r_factor, compute_uv=False)
    tolerance = singular.max() * max(n, k) * np.finfo(float).eps
    design_rank = int((singular > tolerance).sum())
    condition_number = float(singular.max() / singular.min()) if singular.min() > 0 else float("inf")
    r_pinv = np.linalg.pinv(r_factor)
    gram_inverse = r_pinv @ r_pinv.T
    beta = gram_inverse @ cross

    residual_std = np.empty(n)
    leverage = np.empty(n)
    meat = np.zeros((k, k))
    for rows in _chunks(n):
        block = design(rows)
        residual_std[rows] = (y[rows] - y_mean) / y_sd - block @ beta
        leverage[rows] = np.einsum("ij,jk,ik->i", block, gram_inverse, block)
        with np.errstate(divide="ignore", invalid="ignore"):
            weights = (residual_std[rows] / (1.0 - leverage[rows])) ** 2
        meat += (block * weights[:, None]).T @ block
    covariance = gram_inverse @ meat @ gram_inverse
    with np.errstate(invalid="ignore"):
        standard_error = np.sqrt(np.diag(covariance))
    critical = float(stats.norm.ppf(1.0 - (1.0 - confidence) / 2.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        p_values = 2.0 * stats.norm.sf(np.abs(beta / standard_error))
    residuals = residual_std * y_sd
    ssr = float(residuals @ residuals)
    total = float(n * y_sd**2)
    df_resid = n - design_rank
    rsquared = 1.0 - ssr / total if total > 0 else float("nan")
    scale = ssr / df_resid if df_resid > 0 else float("nan")
    with np.errstate(divide="ignore", invalid="ignore"):
        cooks = residuals**2 * leverage / ((1.0 - leverage) ** 2 * scale * k)
    slope_scale = y_sd / x_sd
    return {
        "standardized_beta": beta[1:],
        "standardized_ci_low": beta[1:] - critical * standard_error[1:],
        "standardized_ci_high": beta[1:] + critical * standard_error[1:],
        "p_value": p_values[1:],
        "raw_coefficient": beta[1:] * slope_scale,
        "raw_ci_low": (beta[1:] - critical * standard_error[1:]) * slope_scale,
        "raw_ci_high": (beta[1:] + critical * standard_error[1:]) * slope_scale,
        "design_rank": design_rank,
        "condition_number": condition_number,
        "fitted": y - residuals,
        "residuals": residuals,
        "rsquared": rsquared,
        "rsquared_adj": 1.0 - (n - 1) / df_resid * (1.0 - rsquared) if df_resid > 0 else float("nan"),
        "leverage": leverage,
        "cooks": cooks,
    }


def _ols_statsmodels(x: pd.DataFrame, y: pd.Series, confidence: float) -> dict[str, object]:
    """The original statsmodels path: standardized and raw HC3 fits plus influence diagnostics."""
    p = x.shape[1]
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
    alpha = 1.0 - confidence
    standard_ci = standard_fit.conf_int(alpha=alpha)
    raw_ci = raw_fit.conf_int(alpha=alpha)
    influence = base_fit.get_influence()
    return {
        "standardized_beta": standard_fit.params[internal_names].to_numpy(dtype=float),
        "standardized_ci_low": standard_ci.loc[internal_names, 0].to_numpy(dtype=float),
        "standardized_ci_high": standard_ci.loc[internal_names, 1].to_numpy(dtype=float),
        "p_value": standard_fit.pvalues[internal_names].to_numpy(dtype=float),
        "raw_coefficient": raw_fit.params[internal_names].to_numpy(dtype=float),
        "raw_ci_low": raw_ci.loc[internal_names, 0].to_numpy(dtype=float),
        "raw_ci_high": raw_ci.loc[internal_names, 1].to_numpy(dtype=float),
        "design_rank": int(np.linalg.matrix_rank(standardized_design.to_numpy(dtype=float))),
        "condition_number": float(np.linalg.cond(standardized_design.to_numpy(dtype=float))),
        "fitted": np.asarray(base_fit.fittedvalues, dtype=float),
        "residuals": np.asarray(base_fit.resid, dtype=float),
        "rsquared": float(base_fit.rsquared),
        "rsquared_adj": float(base_fit.rsquared_adj),
        "leverage": np.asarray(influence.hat_matrix_diag, dtype=float),
        "cooks": np.asarray(influence.cooks_distance[0], dtype=float),
    }


def _cross_validated_metrics_large(
    predictors: np.ndarray,
    outcome: np.ndarray,
    folds: int = 5,
    seed: int = 2026,
) -> tuple[float, float]:
    """The five-fold check from per-fold cross-products: each training fit is the total minus one fold."""
    n, p = predictors.shape
    if n < max(30, p * 5) or folds < 2:
        return float("nan"), float("nan")
    folds = min(folds, n)
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    assignments = np.empty(n, dtype=int)
    assignments[order] = np.arange(n) % folds
    grams = np.zeros((folds, p + 1, p + 1))
    crosses = np.zeros((folds, p + 1))
    for rows in _chunks(n):
        block = _design(predictors[rows])
        for fold in range(folds):
            mask = assignments[rows] == fold
            grams[fold] += block[mask].T @ block[mask]
            crosses[fold] += block[mask].T @ outcome[rows][mask]
    coefficients = [
        np.linalg.lstsq(grams.sum(axis=0) - grams[fold], crosses.sum(axis=0) - crosses[fold], rcond=None)[0]
        for fold in range(folds)
    ]
    squared_error = 0.0
    for rows in _chunks(n):
        block = _design(predictors[rows])
        fold_rows = assignments[rows]
        predictions = np.einsum("ij,ij->i", block, np.asarray(coefficients)[fold_rows])
        squared_error += float(((outcome[rows] - predictions) ** 2).sum())
    total = float(np.sum((outcome - outcome.mean()) ** 2))
    cv_r2 = 1.0 - squared_error / total if total > np.finfo(float).eps else float("nan")
    return float(cv_r2), float(np.sqrt(squared_error / n))


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

    # One float copy of the model columns; complete-case rules use boolean masks rather than further copies, so
    # millions of respondents stay affordable.
    numeric = pd.concat(
        {
            column: pd.to_numeric(model_frame[column], errors="coerce").astype(float)
            for column in [outcome_column, *predictor_columns]
        },
        axis=1,
    )
    numeric = numeric.where(np.isfinite(numeric))
    if numeric[outcome_column].dropna().nunique() < 2:
        raise DataProblem("The outcome does not vary in the usable source rows.")
    outcome_present = numeric[outcome_column].notna().to_numpy()
    warnings: list[str] = []
    usable: list[str] = []
    dropped: list[str] = []
    for column in predictor_columns:
        values = numeric[column].to_numpy()
        if _is_constant(values[outcome_present & ~np.isnan(values)]):
            dropped.append(column)
        else:
            usable.append(column)
    if not usable:
        raise DataProblem("None of the selected drivers varies alongside a usable outcome.")

    # A predictor can become constant only after the joint missing-data rule is applied. Remove one at a time and
    # rebuild the sample so another predictor is not discarded merely because the first blocked informative rows.
    while True:
        complete = numeric[[outcome_column, *usable]].notna().all(axis=1).to_numpy()
        constant = next((column for column in usable if _is_constant(numeric[column].to_numpy()[complete])), None)
        if constant is None:
            break
        usable.remove(constant)
        dropped.append(constant)
        if not usable:
            raise DataProblem("None of the selected drivers varies in the retained rows.")

    if dropped:
        warnings.append("Constant driver(s) were removed before the final complete-case sample: " + ", ".join(dropped) + ".")
    check_drivers(len(usable))

    selected = numeric[[outcome_column, *usable]].iloc[np.flatnonzero(complete)]
    del numeric

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

    large = n > LARGE_MODEL_ROWS
    fit = (
        _ols_large(x.to_numpy(dtype=float), y.to_numpy(dtype=float), confidence)
        if large
        else _ols_statsmodels(x, y, confidence)
    )
    design_rank = int(fit["design_rank"])
    expected_rank = p + 1
    inference_valid = design_rank == expected_rank
    if not inference_valid:
        warnings.append(
            "The driver matrix is rank-deficient. Individual coefficients are not uniquely identified; interpret only the shared model fit and grouped importance with caution."
        )

    coefficient_rows: list[dict[str, object]] = []
    for index, name in enumerate(usable):
        beta = float(fit["standardized_beta"][index])
        reported_beta = beta if inference_valid else float("nan")

        def identified(key: str, position: int = index) -> float:
            return float(fit[key][position]) if inference_valid else float("nan")

        coefficient_rows.append(
            {
                "driver": name,
                "standardized_beta": reported_beta,
                "ci_low": identified("standardized_ci_low"),
                "ci_high": identified("standardized_ci_high"),
                "p_value_exploratory": identified("p_value"),
                "raw_coefficient": identified("raw_coefficient"),
                "raw_ci_low": identified("raw_ci_low"),
                "raw_ci_high": identified("raw_ci_high"),
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

    fitted_values = fit["fitted"]
    residuals = fit["residuals"]
    rmse = float(np.sqrt(np.mean(residuals**2)))
    mae = float(np.mean(np.abs(residuals)))
    cross_validate = _cross_validated_metrics_large if large else _cross_validated_metrics
    cv_r2, cv_rmse = cross_validate(x.to_numpy(dtype=float), y.to_numpy(dtype=float), seed=seed)
    if not np.isfinite(cv_r2):
        warnings.append("The retained sample is too small for the built-in deterministic five-fold check.")
    elif cv_r2 < 0:
        warnings.append("Cross-validated R² is below zero; this model predicts held-out rows worse than their mean.")

    condition_number = float(fit["condition_number"])
    leverage = fit["leverage"]
    cooks = fit["cooks"]
    if pd.api.types.is_integer_dtype(selected.index):
        source_rows = selected.index.to_numpy(dtype=np.int64) + 2
    else:
        source_rows = selected.index.to_series().map(
            lambda value: int(value) + 2 if isinstance(value, (int, np.integer)) else str(value)
        ).to_numpy()
    fitted = pd.DataFrame(
        {
            "source_row": source_rows,
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
            {"metric": "R-squared", "value": float(fit["rsquared"]), "note": "In-sample variance explained"},
            {"metric": "Adjusted R-squared", "value": float(fit["rsquared_adj"]), "note": "Penalizes model size"},
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
