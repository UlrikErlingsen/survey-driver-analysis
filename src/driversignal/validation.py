"""Column inference and survey configuration validation."""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from .errors import DataProblem


SPEC_COLUMNS = ["item", "label", "scale", "reverse_scored"]


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def pretty_label(value: object) -> str:
    """Turn a machine-style column name into a readable label."""
    text = re.sub(r"[_\-]+", " ", str(value).strip())
    text = re.sub(r"\s+", " ", text)
    return text[:1].upper() + text[1:] if text else "Unnamed item"


def infer_column(columns: list[str], tokens: tuple[str, ...], fallback: int = 0) -> str:
    """Choose the first column whose normalized name contains a useful token."""
    if not columns:
        raise DataProblem("This table has no columns.")
    normalized = {column: _slug(column) for column in columns}
    return next(
        (column for column in columns if any(token in normalized[column] for token in tokens)),
        columns[min(max(fallback, 0), len(columns) - 1)],
    )


def numeric_candidates(frame: pd.DataFrame, excluded: set[str] | None = None) -> list[str]:
    """Return columns whose non-empty values are overwhelmingly numeric."""
    excluded = excluded or set()
    candidates: list[str] = []
    for raw_column in frame.columns:
        column = str(raw_column)
        if column in excluded:
            continue
        source = frame[raw_column]
        nonmissing = source.notna()
        if int(nonmissing.sum()) < 2:
            continue
        converted = pd.to_numeric(source, errors="coerce")
        finite = converted.notna() & np.isfinite(converted.fillna(0.0))
        if float(finite.sum()) / float(nonmissing.sum()) >= 0.8:
            candidates.append(column)
    return candidates


def default_item_spec(items: list[str]) -> pd.DataFrame:
    """Create an editable scale proposal from common prefix-based item names."""
    prefixes = [_slug(item).split("_")[0] for item in items]
    counts = pd.Series(prefixes).value_counts().to_dict() if prefixes else {}
    generic = {"q", "q1", "q2", "item", "question", "rating", "score"}
    rows: list[dict[str, object]] = []
    for item, prefix in zip(items, prefixes, strict=True):
        inferred = pretty_label(prefix) if counts.get(prefix, 0) >= 2 and prefix not in generic else ""
        rows.append(
            {
                "item": item,
                "label": pretty_label(item),
                "scale": inferred,
                "reverse_scored": "reverse" in _slug(item) or _slug(item).endswith("_r"),
            }
        )
    return pd.DataFrame(rows, columns=SPEC_COLUMNS)


def _as_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "reverse", "reversed"}:
        return True
    if text in {"false", "0", "no", "n", "", "none", "nan"}:
        return False
    raise DataProblem("Reverse-scored flags must use true/false or yes/no.")


def prepare_item_spec(spec: pd.DataFrame, available_columns: list[str]) -> pd.DataFrame:
    """Normalize and validate the editable item-to-scale specification."""
    if spec is None or spec.empty:
        raise DataProblem("Select at least one survey item.")
    missing_fields = [column for column in SPEC_COLUMNS if column not in spec.columns]
    if missing_fields:
        raise DataProblem("The item setup is missing: " + ", ".join(missing_fields) + ".")
    work = spec[SPEC_COLUMNS].copy()
    work["item"] = work["item"].astype(str).str.strip()
    work["label"] = work["label"].fillna("").astype(str).str.strip()
    work["scale"] = work["scale"].fillna("").astype(str).str.strip()
    work["reverse_scored"] = work["reverse_scored"].map(_as_bool)

    if work["item"].eq("").any():
        raise DataProblem("Every selected row needs an item column.")
    if work["item"].duplicated().any():
        repeated = work.loc[work["item"].duplicated(keep=False), "item"].unique().tolist()
        raise DataProblem("Each item can appear only once: " + ", ".join(repeated[:5]) + ".")
    missing = [item for item in work["item"] if item not in available_columns]
    if missing:
        raise DataProblem("Selected items were not found: " + ", ".join(missing[:5]) + ".")
    work.loc[work["label"].eq(""), "label"] = work.loc[work["label"].eq(""), "item"].map(pretty_label)

    # Grouped items become one driver; ungrouped labels become standalone drivers.
    grouped_names = set(work.loc[work["scale"].ne(""), "scale"])
    standalone = work.loc[work["scale"].eq(""), "label"]
    repeated_standalone = standalone[standalone.duplicated(keep=False)].unique().tolist()
    conflicts = sorted(grouped_names.intersection(set(standalone)))
    if repeated_standalone or conflicts:
        names = [*repeated_standalone, *conflicts]
        raise DataProblem("Driver and scale labels must be unique: " + ", ".join(map(str, names[:5])) + ".")
    if len(work) > 30:
        raise DataProblem("Use at most 30 item columns in one analysis. Build focused constructs first.")
    return work.reset_index(drop=True)


def required_answers(n_items: int, minimum_fraction: float) -> int:
    """Translate a documented completion fraction into an item count."""
    if n_items < 1:
        raise DataProblem("A scale needs at least one item.")
    if not 0 < minimum_fraction <= 1:
        raise DataProblem("The required answered proportion must be above 0 and at most 1.")
    return max(1, int(math.ceil(n_items * minimum_fraction - 1e-12)))


def coerce_numeric(series: pd.Series, name: str) -> pd.Series:
    """Convert one selected field to finite numeric values, retaining missingness."""
    converted = pd.to_numeric(series, errors="coerce").astype(float)
    invalid = series.notna() & (converted.isna() | ~np.isfinite(converted))
    if invalid.any():
        raise DataProblem(f"'{name}' contains non-numeric or infinite values in selected rows.")
    return converted.where(np.isfinite(converted), np.nan)
