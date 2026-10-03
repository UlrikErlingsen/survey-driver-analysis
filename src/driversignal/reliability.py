"""Cronbach reliability diagnostics and transparent scale scoring."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .errors import DataProblem


# Respondent-by-item cells one interactive bootstrap may resample. Above it, the bootstrap runs on a seeded random
# subsample and its interval is rescaled to the full sample size (see bootstrap_alpha_details).
BOOTSTRAP_CELL_BUDGET = 50_000_000
MIN_BOOTSTRAP_SUBSAMPLE = 2_000


@dataclass(frozen=True)
class ReliabilityResult:
    """Reliability summary and item-level diagnostics for one construct."""

    scale: str
    n_items: int
    n_complete: int
    alpha: float
    standardized_alpha: float
    mean_interitem_correlation: float
    ci_low: float
    ci_high: float
    items: pd.DataFrame
    correlations: pd.DataFrame
    warnings: tuple[str, ...]
    bootstrap_rows: int = 0


def reverse_score(series: pd.Series, minimum: float, maximum: float) -> pd.Series:
    """Reverse a numeric item around declared theoretical endpoints."""
    if not np.isfinite(minimum) or not np.isfinite(maximum) or minimum >= maximum:
        raise DataProblem("Reverse-scoring endpoints must be finite, with minimum below maximum.")
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    observed = numeric.dropna()
    if ((observed < minimum - 1e-12) | (observed > maximum + 1e-12)).any():
        raise DataProblem(
            f"A reverse-scored item contains values outside the declared {minimum:g}–{maximum:g} range."
        )
    return minimum + maximum - numeric


def cronbach_alpha(frame: pd.DataFrame) -> float:
    """Calculate raw alpha on the supplied complete-case item matrix."""
    if frame.shape[1] < 2 or frame.shape[0] < 2:
        return float("nan")
    values = frame.to_numpy(dtype=float)
    item_variances = np.var(values, axis=0, ddof=1)
    total_variance = float(np.var(values.sum(axis=1), ddof=1))
    if not np.isfinite(total_variance) or total_variance <= np.finfo(float).eps:
        return float("nan")
    k = values.shape[1]
    return float(k / (k - 1) * (1.0 - float(item_variances.sum()) / total_variance))


def standardized_alpha(frame: pd.DataFrame) -> tuple[float, float]:
    """Return standardized alpha and mean off-diagonal item correlation."""
    if frame.shape[1] < 2 or frame.shape[0] < 2:
        return float("nan"), float("nan")
    correlation = frame.corr()
    values = correlation.to_numpy(dtype=float)
    off_diagonal = values[np.triu_indices_from(values, k=1)]
    finite = off_diagonal[np.isfinite(off_diagonal)]
    if len(finite) != len(off_diagonal) or not len(finite):
        return float("nan"), float("nan")
    mean_r = float(finite.mean())
    k = frame.shape[1]
    denominator = 1.0 + (k - 1) * mean_r
    alpha = float(k * mean_r / denominator) if abs(denominator) > np.finfo(float).eps else float("nan")
    return alpha, mean_r


def bootstrap_alpha_details(
    complete: pd.DataFrame,
    repetitions: int = 400,
    seed: int = 2026,
) -> tuple[float, float, int]:
    """Deterministic respondent bootstrap interval for raw alpha, plus the number of rows it resampled.

    When ``repetitions × rows × items`` exceeds ``BOOTSTRAP_CELL_BUDGET``, the bootstrap resamples a seeded random
    subsample of ``m`` complete rows and the interval is rescaled to the full ``n``: alpha is root-n consistent, so
    ``alpha_n + sqrt(m / n) · (q - alpha_m)`` carries the subsample's bootstrap quantiles ``q`` over to the full
    sample. The returned row count tells callers to label that interval.
    """
    n = len(complete)
    k = complete.shape[1]
    if repetitions < 2 or n < 3 or k < 2:
        return float("nan"), float("nan"), 0
    rows = min(n, max(BOOTSTRAP_CELL_BUDGET // (repetitions * k), MIN_BOOTSTRAP_SUBSAMPLE))
    if repetitions * rows * k > BOOTSTRAP_CELL_BUDGET:
        raise DataProblem(
            "The requested alpha bootstrap is too large for an interactive run. Choose fewer repetitions or skip "
            "the bootstrap; the point estimate and item diagnostics remain available."
        )
    values = complete.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    if rows < n:
        values = values[np.sort(rng.choice(n, size=rows, replace=False))]
    estimates: list[float] = []
    for _ in range(repetitions):
        sampled = values[rng.integers(0, rows, size=rows)]
        estimate = cronbach_alpha(pd.DataFrame(sampled, columns=complete.columns))
        if np.isfinite(estimate):
            estimates.append(float(estimate))
    if len(estimates) < max(20, repetitions // 4):
        return float("nan"), float("nan"), rows
    low, high = (float(value) for value in np.percentile(estimates, [2.5, 97.5]))
    if rows < n:
        full = cronbach_alpha(complete)
        center = cronbach_alpha(pd.DataFrame(values, columns=complete.columns))
        if not (np.isfinite(full) and np.isfinite(center)):
            return float("nan"), float("nan"), rows
        shrink = math.sqrt(rows / n)
        low, high = full + shrink * (low - center), full + shrink * (high - center)
    return low, high, rows


def bootstrap_alpha(
    complete: pd.DataFrame,
    repetitions: int = 400,
    seed: int = 2026,
) -> tuple[float, float]:
    """Deterministic respondent bootstrap interval for raw alpha."""
    low, high, _ = bootstrap_alpha_details(complete, repetitions, seed)
    return low, high


def analyze_reliability(
    frame: pd.DataFrame,
    scale: str,
    reversed_items: set[str] | None = None,
    bootstrap_repetitions: int = 400,
    seed: int = 2026,
) -> ReliabilityResult:
    """Analyze one already-scored item set using a shared listwise sample."""
    reversed_items = reversed_items or set()
    if frame.shape[1] < 2:
        raise DataProblem(f"Scale '{scale}' needs at least two items for reliability analysis.")
    numeric = frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    complete = numeric.dropna(axis=0, how="any")
    warnings: list[str] = []
    if len(complete) < 2:
        warnings.append("Fewer than two respondents answered every item; alpha is undefined.")
    if frame.shape[1] == 2:
        warnings.append("With two items, alpha is a transformation of their correlation; inspect the correlation too.")
    if len(complete) < 50:
        warnings.append("Fewer than 50 complete responses make this reliability estimate especially uncertain.")

    zero_variance = [column for column in complete if complete[column].nunique(dropna=True) < 2]
    if zero_variance:
        warnings.append("Zero-variance item(s) limit reliability diagnostics: " + ", ".join(zero_variance) + ".")

    alpha = cronbach_alpha(complete)
    std_alpha, mean_r = standardized_alpha(complete)
    ci_low, ci_high, bootstrap_rows = bootstrap_alpha_details(complete, bootstrap_repetitions, seed)
    if 0 < bootstrap_rows < len(complete):
        warnings.append(
            f"Alpha interval: {bootstrap_repetitions:,} bootstrap resamples of a seeded random subsample of "
            f"{bootstrap_rows:,} of {len(complete):,} complete respondents, rescaled to the full sample by "
            f"sqrt({bootstrap_rows:,}/{len(complete):,}). The alpha point estimate uses every complete respondent."
        )
    if np.isfinite(alpha) and alpha < 0:
        warnings.append("Alpha is negative. Check item direction, wording, and whether these items belong in one construct.")
    if np.isfinite(alpha) and alpha > 0.95:
        warnings.append("Very high alpha can indicate redundant items; it does not prove a better measure.")

    diagnostics: list[dict[str, object]] = []
    # Corrected item-total correlations and alpha-if-deleted follow from one item covariance matrix, so a scale
    # with millions of respondents needs a single pass over the data instead of one per item.
    covariance = np.cov(complete.to_numpy(dtype=float), rowvar=False, ddof=1) if len(complete) >= 2 else None
    tolerance = np.finfo(float).eps
    for position, column in enumerate(numeric.columns):
        if covariance is not None:
            others = [index for index in range(covariance.shape[0]) if index != position]
            rest = covariance[np.ix_(others, others)]
            rest_variance = float(rest.sum())
            item_variance = float(covariance[position, position])
            item_total = (
                float(covariance[position, others].sum()) / float(np.sqrt(item_variance * rest_variance))
                if rest_variance > tolerance and item_variance > tolerance
                else float("nan")
            )
            remaining_items = len(others)
            alpha_deleted = (
                remaining_items / (remaining_items - 1) * (1.0 - float(np.trace(rest)) / rest_variance)
                if remaining_items >= 2 and rest_variance > tolerance
                else float("nan")
            )
        else:
            item_total = float("nan")
            alpha_deleted = float("nan")
        diagnostics.append(
            {
                "scale": scale,
                "item": column,
                "reverse_scored": column in reversed_items,
                "observed_n": int(numeric[column].notna().sum()),
                "missing_percent": float(numeric[column].isna().mean() * 100),
                "mean": float(numeric[column].mean()) if numeric[column].notna().any() else float("nan"),
                "sd": float(numeric[column].std(ddof=1)) if numeric[column].notna().sum() >= 2 else float("nan"),
                "corrected_item_total": float(item_total),
                "alpha_if_deleted": float(alpha_deleted),
            }
        )
        if np.isfinite(item_total) and item_total < 0:
            warnings.append(f"'{column}' has a negative corrected item–total correlation; check its keying and meaning.")

    correlation = complete.corr() if len(complete) >= 2 else pd.DataFrame(index=numeric.columns, columns=numeric.columns)
    long_correlations: list[dict[str, object]] = []
    for left_index, left in enumerate(numeric.columns):
        for right in numeric.columns[left_index + 1 :]:
            value = correlation.loc[left, right] if left in correlation.index and right in correlation.columns else np.nan
            long_correlations.append({"scale": scale, "item_a": left, "item_b": right, "correlation": value})

    return ReliabilityResult(
        scale=scale,
        n_items=int(frame.shape[1]),
        n_complete=int(len(complete)),
        alpha=float(alpha),
        standardized_alpha=float(std_alpha),
        mean_interitem_correlation=float(mean_r),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        items=pd.DataFrame(diagnostics),
        correlations=pd.DataFrame(long_correlations),
        warnings=tuple(dict.fromkeys(warnings)),
        bootstrap_rows=int(bootstrap_rows),
    )


def reliability_label(alpha: float) -> str:
    """A cautious contextual label, never a validity verdict."""
    if not np.isfinite(alpha):
        return "Not estimable"
    if alpha < 0:
        return "Contradictory item covariance"
    if alpha < 0.60:
        return "Low consistency"
    if alpha < 0.70:
        return "Tentative consistency"
    if alpha < 0.90:
        return "Useful consistency"
    if alpha <= 0.95:
        return "Very high consistency"
    return "Very high — check redundancy"
