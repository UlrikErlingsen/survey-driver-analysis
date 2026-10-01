# Contributing to Driver Signal

Contributions that make Driver Signal clearer, safer, statistically sounder, or easier for marketers are welcome.

## Development setup

Python 3.10 or newer is required. From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
python -m build
python -m streamlit run app.py
```

## Project structure

```text
app.py                    Thin standalone Streamlit entry point (page config + render())
src/driversignal/         Scoring, reliability, modeling, validation, examples, and export logic
src/driversignal/ui/      Streamlit workflow, Plotly figures, and the synced Signal theme (Signal Hub entry point)
tests/                    Analytical, synthetic-recovery, I/O, and app tests
docs/                     Data contract, method details, and decision guidance
examples/                 Deterministic fictional demo and starter templates
```

Computation under `src/driversignal/` (outside `ui/`) must remain importable without Streamlit, Plotly, session state, or UI side effects. Only `src/driversignal/ui/` may import Streamlit or Plotly; `ui/signal_theme.py` and `ui/assets/marks/` are synced from Signal Hub and are not edited here.

## Method and data rules

- Preserve the distinction between observational association and causal effect.
- Use the respondent's original 0–10 recommendation score for the driver model; never invent respondent-level NPS.
- Never silently reverse, delete, impute, standardize, or group an item.
- Keep raw alpha, standardized alpha, item–total correlation, and alpha-if-deleted conceptually distinct.
- Use one complete respondent sample within each reliability analysis.
- Keep LMG/Shapley importance nonnegative and beta direction separate.
- Ensure every subset model uses the same complete-case sample as the full model.
- Suppress or qualify coefficient inference when the design is rank deficient.
- Treat VIF, cross-validation, leverage, and Cook's distance as diagnostics—not automatic decisions.
- Add an analytically derived or independently generated synthetic test for every statistical behavior change.
- Update `docs/methods.md` and cite primary literature when changing a convention.

## Product and safety rules

- Explain technical terms at first use and keep expert diagnostics close to the decision view.
- Keep spreadsheet-formula neutralization, local file limits, and source/audit metadata intact.
- Never add telemetry, external AI calls, or persistent upload storage without explicit public design discussion.
- Use only synthetic, public, or properly anonymized data in tests, examples, issues, and screenshots.
- Do not include real survey responses, identifiers, credentials, or confidential business results in a report.

## Pull requests

Keep pull requests focused. Explain the user problem, methodological effect, validation, assumptions, limitations, privacy impact, exports, and visible UI changes. Run the full test, lint, build, and visual checks before requesting review. Security and privacy concerns belong in the private channels in [SECURITY.md](SECURITY.md).
