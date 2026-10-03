"""Privacy-preserving transformations for portable evidence packs."""

from __future__ import annotations

import pandas as pd

from .errors import DataProblem


INFLUENCE_EXPORT_COLUMNS = ["source_row", "leverage", "cooks_distance"]
# Rows of the per-respondent influence table an evidence pack carries. Larger models export the most influential
# rows (highest Cook's distance) so the Excel sheet stays openable and the pack stays small; the manifest says so.
INFLUENCE_EXPORT_MAX_ROWS = 50_000


def privacy_safe_influence(fitted: pd.DataFrame, max_rows: int = INFLUENCE_EXPORT_MAX_ROWS) -> pd.DataFrame:
    """Keep row-tracing influence diagnostics without exporting outcome values."""
    missing = [column for column in INFLUENCE_EXPORT_COLUMNS if column not in fitted.columns]
    if missing:
        raise DataProblem("Influence diagnostics are missing: " + ", ".join(missing) + ".")
    table = fitted[INFLUENCE_EXPORT_COLUMNS]
    if len(table) > max_rows:
        table = table.nlargest(max_rows, "cooks_distance").sort_index()
    return table.copy()


def influence_export_note(fitted: pd.DataFrame, max_rows: int = INFLUENCE_EXPORT_MAX_ROWS) -> str:
    """Describe which influence rows an evidence pack carries."""
    if len(fitted) <= max_rows:
        return f"All {len(fitted):,} model rows"
    return f"The {max_rows:,} model rows with the highest Cook's distance, of {len(fitted):,}"
