"""Privacy-preserving transformations for portable evidence packs."""

from __future__ import annotations

import pandas as pd

from .errors import DataProblem


INFLUENCE_EXPORT_COLUMNS = ["source_row", "leverage", "cooks_distance"]


def privacy_safe_influence(fitted: pd.DataFrame) -> pd.DataFrame:
    """Keep row-tracing influence diagnostics without exporting outcome values."""
    missing = [column for column in INFLUENCE_EXPORT_COLUMNS if column not in fitted.columns]
    if missing:
        raise DataProblem("Influence diagnostics are missing: " + ", ".join(missing) + ".")
    return fitted[INFLUENCE_EXPORT_COLUMNS].copy()
