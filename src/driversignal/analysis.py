"""End-to-end survey scoring, reliability, and driver-analysis orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .drivers import DriverResult, fit_driver_model
from .errors import DataProblem
from .reliability import ReliabilityResult, analyze_reliability, reliability_label, reverse_score
from .validation import coerce_numeric, prepare_item_spec, required_answers


@dataclass(frozen=True)
class SurveyAnalysis:
    """All auditable outputs generated from one survey setup."""

    outcome_column: str
    outcome_kind: str
    predictor_columns: tuple[str, ...]
    model_frame: pd.DataFrame
    driver_result: DriverResult
    scale_summary: pd.DataFrame
    item_diagnostics: pd.DataFrame
    interitem_correlations: pd.DataFrame
    outcome_summary: pd.DataFrame
    nps_composition: pd.DataFrame
    retention: pd.DataFrame
    missingness: pd.DataFrame
    scale_definitions: pd.DataFrame
    warnings: tuple[str, ...]
    minimum_answered_fraction: float
    scale_minimum: float
    scale_maximum: float


def nps_summary(
    values: pd.Series,
    bootstrap_repetitions: int = 5000,
    seed: int = 2026,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return aggregate NPS metrics and 0–10 category composition."""
    numeric = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if numeric.empty:
        raise DataProblem("No usable NPS scores remain.")
    if ((numeric < 0) | (numeric > 10) | (np.abs(numeric - np.round(numeric)) > 1e-9)).any():
        raise DataProblem("Standard NPS responses must be whole numbers from 0 through 10.")
    detractors = int((numeric <= 6).sum())
    passives = int(((numeric >= 7) & (numeric <= 8)).sum())
    promoters = int((numeric >= 9).sum())
    counts = np.array([detractors, passives, promoters], dtype=int)
    n = int(len(numeric))
    percentages = counts / n * 100.0
    nps = float(percentages[2] - percentages[0])

    ci_low = float("nan")
    ci_high = float("nan")
    if bootstrap_repetitions >= 2 and n >= 2:
        rng = np.random.default_rng(seed)
        draws = rng.multinomial(n, counts / n, size=bootstrap_repetitions)
        boot = (draws[:, 2] - draws[:, 0]) / n * 100.0
        ci_low, ci_high = (float(value) for value in np.percentile(boot, [2.5, 97.5]))

    metrics = pd.DataFrame(
        [
            {"metric": "Respondents with NPS score", "value": n, "note": "Non-missing whole-number responses"},
            {"metric": "Mean recommendation score", "value": float(numeric.mean()), "note": "Modeled on the original 0–10 score"},
            {"metric": "Median recommendation score", "value": float(numeric.median()), "note": "Original 0–10 scale"},
            {"metric": "NPS", "value": nps, "note": "Promoter % minus detractor %"},
            {"metric": "NPS bootstrap 95% low", "value": ci_low, "note": f"{bootstrap_repetitions:,} deterministic resamples"},
            {"metric": "NPS bootstrap 95% high", "value": ci_high, "note": f"{bootstrap_repetitions:,} deterministic resamples"},
        ]
    )
    composition = pd.DataFrame(
        {
            "category": ["Detractors (0–6)", "Passives (7–8)", "Promoters (9–10)"],
            "respondents": counts,
            "percent": percentages,
        }
    )
    return metrics, composition


def satisfaction_summary(values: pd.Series) -> pd.DataFrame:
    """Summarize a general numeric satisfaction outcome without inventing cutoffs."""
    numeric = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if len(numeric) < 2 or numeric.nunique() < 2:
        raise DataProblem("The satisfaction outcome needs at least two usable, varying responses.")
    return pd.DataFrame(
        [
            {"metric": "Respondents with outcome", "value": len(numeric), "note": "Non-missing numeric responses"},
            {"metric": "Mean", "value": float(numeric.mean()), "note": "Original outcome units"},
            {"metric": "Median", "value": float(numeric.median()), "note": "Original outcome units"},
            {"metric": "Standard deviation", "value": float(numeric.std(ddof=1)), "note": "Original outcome units"},
            {"metric": "Minimum", "value": float(numeric.min()), "note": "Observed, not theoretical"},
            {"metric": "Maximum", "value": float(numeric.max()), "note": "Observed, not theoretical"},
        ]
    )


def analyze_survey(
    frame: pd.DataFrame,
    outcome_column: str,
    item_spec: pd.DataFrame,
    outcome_kind: str = "NPS (0–10 recommendation)",
    scale_minimum: float = 1.0,
    scale_maximum: float = 7.0,
    minimum_answered_fraction: float = 1.0,
    confidence: float = 0.95,
    reliability_bootstrap_repetitions: int = 400,
    nps_bootstrap_repetitions: int = 5000,
    importance_permutations: int = 2000,
    seed: int = 2026,
) -> SurveyAnalysis:
    """Create scale scores and fit one consistent complete-case driver model."""
    if frame is None or frame.empty:
        raise DataProblem("Load respondent-level survey data first.")
    if outcome_column not in frame.columns:
        raise DataProblem("The selected outcome was not found in this table.")
    spec = prepare_item_spec(item_spec, [str(column) for column in frame.columns])
    if outcome_column in set(spec["item"]):
        raise DataProblem("The outcome cannot also be one of its own drivers.")
    if not 0.80 <= confidence < 1.0:
        raise DataProblem("Confidence level must be at least 80% and below 100%.")
    if not np.isfinite(scale_minimum) or not np.isfinite(scale_maximum) or scale_minimum >= scale_maximum:
        raise DataProblem("Scale endpoints must be finite, with minimum below maximum.")

    outcome = coerce_numeric(frame[outcome_column], outcome_column)
    scored_items = pd.DataFrame(index=frame.index)
    for row in spec.itertuples(index=False):
        numeric = coerce_numeric(frame[row.item], row.item)
        observed = numeric.dropna()
        if row.scale and ((observed < scale_minimum - 1e-12) | (observed > scale_maximum + 1e-12)).any():
            raise DataProblem(
                f"'{row.item}' contains values outside the declared {scale_minimum:g}–{scale_maximum:g} "
                "item range used for construct scoring."
            )
        scored_items[row.item] = reverse_score(numeric, scale_minimum, scale_maximum) if row.reverse_scored else numeric

    reliability_results: list[ReliabilityResult] = []
    scale_rows: list[dict[str, object]] = []
    warnings: list[str] = []
    drivers = pd.DataFrame(index=frame.index)

    grouped = spec.loc[spec["scale"].ne("")]
    for scale, rows in grouped.groupby("scale", sort=False):
        items = rows["item"].tolist()
        required = required_answers(len(items), minimum_answered_fraction)
        available = scored_items[items].notna().sum(axis=1)
        score = scored_items[items].mean(axis=1, skipna=True).where(available >= required)
        drivers[str(scale)] = score
        result: ReliabilityResult | None = None
        if len(items) >= 2:
            result = analyze_reliability(
                scored_items[items],
                str(scale),
                reversed_items=set(rows.loc[rows["reverse_scored"], "item"]),
                bootstrap_repetitions=reliability_bootstrap_repetitions,
                seed=seed + len(reliability_results),
            )
            reliability_results.append(result)
            warnings.extend(f"{scale}: {warning}" for warning in result.warnings)
        else:
            warnings.append(f"{scale}: one-item driver; internal-consistency reliability is not defined.")
        scale_rows.append(
            {
                "scale": str(scale),
                "items": len(items),
                "required_answers": required,
                "scored_respondents": int(score.notna().sum()),
                "complete_for_alpha": result.n_complete if result else np.nan,
                "cronbach_alpha": result.alpha if result else np.nan,
                "alpha_ci_low": result.ci_low if result else np.nan,
                "alpha_ci_high": result.ci_high if result else np.nan,
                "standardized_alpha": result.standardized_alpha if result else np.nan,
                "mean_interitem_correlation": result.mean_interitem_correlation if result else np.nan,
                "contextual_read": reliability_label(result.alpha) if result else "One item — alpha not defined",
            }
        )

    for row in spec.loc[spec["scale"].eq("")].itertuples(index=False):
        drivers[row.label] = scored_items[row.item]

    if drivers.shape[1] < 1:
        raise DataProblem("No driver scores could be created from this setup.")
    if not drivers.columns.is_unique:
        duplicates = drivers.columns[drivers.columns.duplicated()].unique().tolist()
        raise DataProblem("Scored driver names must be unique: " + ", ".join(map(str, duplicates)) + ".")
    if outcome_column in drivers.columns:
        raise DataProblem("A scale or driver label cannot have the same name as the outcome column.")
    if drivers.shape[1] > 20:
        raise DataProblem("This setup creates more than 20 drivers. Group related items into constructs first.")

    model_frame = pd.concat([outcome.rename(outcome_column), drivers], axis=1)
    missingness_rows = [
        {"field": outcome_column, "role": "Outcome", "missing_rows": int(outcome.isna().sum()), "missing_percent": float(outcome.isna().mean() * 100)}
    ]
    for column in drivers:
        missingness_rows.append(
            {
                "field": column,
                "role": "Scored driver",
                "missing_rows": int(drivers[column].isna().sum()),
                "missing_percent": float(drivers[column].isna().mean() * 100),
            }
        )
    missingness = pd.DataFrame(missingness_rows).sort_values("missing_percent", ascending=False).reset_index(drop=True)

    result = fit_driver_model(
        model_frame,
        outcome_column,
        list(drivers.columns),
        confidence=confidence,
        importance_permutations=importance_permutations,
        seed=seed,
    )
    retained_names = set(result.coefficients["driver"])
    model_predictors = [column for column in drivers.columns if column in retained_names]
    complete = model_frame[[outcome_column, *model_predictors]].dropna(axis=0, how="any")
    starting_rows = int(len(frame))
    retained_rows = int(len(complete))
    retention_percent = retained_rows / starting_rows * 100.0 if starting_rows else 0.0
    retention = pd.DataFrame(
        [
            {"stage": "Rows in source table", "rows": starting_rows, "percent_of_source": 100.0},
            {
                "stage": "Rows with outcome",
                "rows": int(outcome.notna().sum()),
                "percent_of_source": float(outcome.notna().mean() * 100),
            },
            {
                "stage": "Rows complete for full model",
                "rows": retained_rows,
                "percent_of_source": retention_percent,
            },
            {
                "stage": "Rows excluded by listwise rule",
                "rows": starting_rows - retained_rows,
                "percent_of_source": 100.0 - retention_percent,
            },
        ]
    )
    if retention_percent < 80:
        warnings.append(
            f"Only {retention_percent:.1f}% of source rows are complete for the full model; missingness may change the result."
        )

    normalized_kind = outcome_kind.lower()
    if "nps" in normalized_kind or "recommend" in normalized_kind:
        outcome_summary, composition = nps_summary(outcome, nps_bootstrap_repetitions, seed)
        warnings.append(
            "The driver model uses the original 0–10 recommendation score. Aggregate NPS is not a respondent-level outcome."
        )
    else:
        outcome_summary = satisfaction_summary(outcome)
        composition = pd.DataFrame(columns=["category", "respondents", "percent"])

    warnings.extend(result.warnings)
    warnings.append(
        "Cross-sectional survey associations are not causal effects; respondent selection, common-method bias, omitted variables, and reverse direction can matter."
    )

    item_diagnostics = (
        pd.concat([result.items for result in reliability_results], ignore_index=True)
        if reliability_results
        else pd.DataFrame(
            columns=[
                "scale",
                "item",
                "reverse_scored",
                "observed_n",
                "missing_percent",
                "mean",
                "sd",
                "corrected_item_total",
                "alpha_if_deleted",
            ]
        )
    )
    correlations = (
        pd.concat([result.correlations for result in reliability_results], ignore_index=True)
        if reliability_results
        else pd.DataFrame(columns=["scale", "item_a", "item_b", "correlation"])
    )
    scale_summary = pd.DataFrame(scale_rows)

    definitions = spec.copy()
    definitions["model_driver"] = definitions.apply(
        lambda row: row["scale"] if row["scale"] else row["label"], axis=1
    )
    definitions["scoring"] = definitions.apply(
        lambda row: (
            f"Reverse {scale_minimum:g}–{scale_maximum:g}, then construct mean"
            if row["reverse_scored"] and row["scale"]
            else f"Reverse {scale_minimum:g}–{scale_maximum:g}"
            if row["reverse_scored"]
            else "Construct mean"
            if row["scale"]
            else "Original numeric response"
        ),
        axis=1,
    )

    return SurveyAnalysis(
        outcome_column=outcome_column,
        outcome_kind=outcome_kind,
        predictor_columns=tuple(model_predictors),
        model_frame=model_frame,
        driver_result=result,
        scale_summary=scale_summary,
        item_diagnostics=item_diagnostics,
        interitem_correlations=correlations,
        outcome_summary=outcome_summary,
        nps_composition=composition,
        retention=retention,
        missingness=missingness,
        scale_definitions=definitions,
        warnings=tuple(dict.fromkeys(warnings)),
        minimum_answered_fraction=float(minimum_answered_fraction),
        scale_minimum=float(scale_minimum),
        scale_maximum=float(scale_maximum),
    )
