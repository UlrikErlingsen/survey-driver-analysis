"""Deterministic fictional survey data and starter templates (no UI dependency).

The in-app demo, the downloadable templates and the committed files in ``examples/`` all come from these
functions, so they contain identical data. ``scripts/generate_examples.py`` writes the committed copies.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pandas as pd


DEMO_FILENAME = "demo_customer_experience_survey.csv"
TEMPLATE_CSV_FILENAME = "survey_template.csv"
TEMPLATE_XLSX_FILENAME = "survey_template.xlsx"

SEED = 260714


def _likert(rng: np.random.Generator, latent: np.ndarray, noise: float = 0.72) -> np.ndarray:
    values = 4.0 + 1.05 * latent + rng.normal(0.0, noise, size=len(latent))
    return np.clip(np.rint(values), 1, 7).astype(float)


def build_demo(n: int = 520) -> pd.DataFrame:
    """Create four correlated constructs with a known, non-causal outcome pattern."""
    rng = np.random.default_rng(SEED)
    correlation = np.array(
        [
            [1.00, 0.42, 0.34, 0.38],
            [0.42, 1.00, 0.31, 0.36],
            [0.34, 0.31, 1.00, 0.29],
            [0.38, 0.36, 0.29, 1.00],
        ]
    )
    service, value, ease, trust = rng.multivariate_normal(np.zeros(4), correlation, size=n).T
    frame = pd.DataFrame(
        {
            "respondent_id": [f"R{index:04d}" for index in range(1, n + 1)],
            "region": rng.choice(["North", "South", "East", "West"], size=n, p=[0.24, 0.26, 0.27, 0.23]),
            "customer_tenure_months": np.maximum(1, np.rint(rng.gamma(2.4, 12.0, size=n))).astype(int),
            "service_speed": _likert(rng, service),
            "service_resolution": _likert(rng, service),
            "service_care": _likert(rng, service),
            "value_fair": _likert(rng, value),
            "value_quality": _likert(rng, value),
            "value_clear": _likert(rng, value),
            "ease_setup": _likert(rng, ease),
            "ease_use": _likert(rng, ease),
            "ease_reverse_effort": 8.0 - _likert(rng, ease),
            "trust_reliable": _likert(rng, trust),
            "trust_honest": _likert(rng, trust),
            "trust_secure": _likert(rng, trust),
        }
    )
    satisfaction_latent = 0.58 * service + 0.38 * value + 0.18 * ease + 0.12 * trust + rng.normal(0, 0.82, n)
    recommendation_latent = 0.66 * service + 0.47 * value + 0.21 * ease + 0.13 * trust + rng.normal(0, 1.05, n)
    frame.insert(3, "satisfaction_1_7", np.clip(np.rint(4.1 + 1.05 * satisfaction_latent), 1, 7).astype(float))
    frame.insert(4, "recommend_0_10", np.clip(np.rint(6.3 + 1.22 * recommendation_latent), 0, 10).astype(float))

    item_columns = [column for column in frame.columns if column.split("_")[0] in {"service", "value", "ease", "trust"}]
    for column in item_columns:
        frame.loc[rng.random(n) < 0.018, column] = np.nan
    frame.loc[rng.random(n) < 0.008, "satisfaction_1_7"] = np.nan
    return frame


def build_template() -> tuple[pd.DataFrame, pd.DataFrame]:
    survey = pd.DataFrame(
        {
            "respondent_id": ["R001", "R002", "R003"],
            "satisfaction": [6, 4, 5],
            "service_speed": [7, 3, 5],
            "service_helpful": [6, 4, 5],
            "service_resolution": [7, 3, 6],
            "value_fair": [5, 4, 6],
            "value_quality": [6, 5, 6],
            "value_clear": [6, 3, 5],
        }
    )
    setup = pd.DataFrame(
        {
            "item": [
                "service_speed",
                "service_helpful",
                "service_resolution",
                "value_fair",
                "value_quality",
                "value_clear",
            ],
            "label": ["Service speed", "Helpful service", "Resolution", "Fair price", "Quality for price", "Clear price"],
            "scale": ["Service", "Service", "Service", "Value", "Value", "Value"],
            "reverse_scored": [False, False, False, False, False, False],
        }
    )
    return survey, setup


def demo_csv_bytes() -> bytes:
    """The fictional demo survey as CSV bytes, byte-identical to ``examples/demo_customer_experience_survey.csv``."""
    return build_demo().to_csv(index=False).encode("utf-8")


def template_csv_bytes() -> bytes:
    """The starter survey template as CSV bytes."""
    survey, _ = build_template()
    return survey.to_csv(index=False).encode("utf-8")


def template_xlsx_bytes() -> bytes:
    """The starter survey template plus an item-setup example as an Excel workbook."""
    survey, setup = build_template()
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        survey.to_excel(writer, sheet_name="Survey", index=False)
        setup.to_excel(writer, sheet_name="Item setup example", index=False)
    return buffer.getvalue()
