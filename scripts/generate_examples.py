"""Generate deterministic fictional survey data and starter templates."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(ROOT / "src"))

from driversignal.examples import (  # noqa: E402
    DEMO_FILENAME,
    TEMPLATE_CSV_FILENAME,
    TEMPLATE_XLSX_FILENAME,
    build_demo,
    build_template,
)


def main() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    demo = build_demo()
    survey, setup = build_template()
    demo.to_csv(EXAMPLES / DEMO_FILENAME, index=False)
    survey.to_csv(EXAMPLES / TEMPLATE_CSV_FILENAME, index=False)
    with pd.ExcelWriter(EXAMPLES / TEMPLATE_XLSX_FILENAME, engine="openpyxl") as writer:
        survey.to_excel(writer, sheet_name="Survey", index=False)
        setup.to_excel(writer, sheet_name="Item setup example", index=False)
    assert demo["recommend_0_10"].dropna().between(0, 10).all()
    assert demo.filter(regex=r"^(service|value|ease|trust)_").stack().between(1, 7).all()
    assert len(demo) == 520


if __name__ == "__main__":
    main()
