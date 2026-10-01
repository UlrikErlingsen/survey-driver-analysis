# Changelog

All notable changes to Driver Signal are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-10-02

Signal brand refresh and Signal Hub entry point. The analysis, statistics, data contract and evidence-pack contents are unchanged.

### Brand

- Display name written **Driver Signal** (with a space) in the app, README, docs, launchers, policies, issue templates and metadata (including the evidence-pack `product` field). Package, file, Docker and environment-variable names stay `driversignal` / `DRIVERSIGNAL_*`.
- The app uses the shared `signal_theme` module (Organic Signal design, Research family colour `#a06f1f`, Figtree): sidebar lockup, masthead, hero, cards, notes, footer and the mark as favicon replace the pasted styles.
- Every chart uses the Driver Signal Plotly template and the shared chart roles (importance and alpha estimates in the family colour, intervals and reference lines in neutral tones, positive and negative associations at the two ends of the diverging palette) and is shown through `sig.chart`. The observed-versus-fitted chart now keeps its "Observed outcome" axis title.
- New banner, social preview and marks in `assets/`; the old banner SVG is removed. `.streamlit/config.toml` uses the family colours and keeps the 200 MB upload limit.
- README follows the Signal template; bug-report, feature-request and config issue templates added.

### Signal Hub contract

- `driversignal.ui` exposes `APP_INFO` and `render()`, so Signal Hub can embed the app; `app.py` is now a thin standalone entry point.
- All session-state and widget keys are namespaced `driver:` (including the page selector).
- The Plotly figures moved from `driversignal.plotting` to `driversignal.ui.plotting`. `streamlit` and `plotly` moved to a `ui` extra (also in `test`); the analysis core installs without them. `requirements.txt` still lists everything.
- The demo survey and starter templates are generated in code (`driversignal.examples`, byte-identical to `examples/`), so the demo also works from an installed package; `scripts/generate_examples.py` reuses the same functions.
- New tests: no Streamlit/Plotly import outside `driversignal.ui`, `render()` runs from a script (and from an installed copy of the package) without a page config, every widget key is namespaced, and the README follows the Signal template.

## [1.0.1] - 2026-07-16

### Security

- Survey column names are now HTML-escaped before they are rendered in the priority callout and insight cards.
- The Docker image keeps application code root-owned and read-only, and defusedxml hardens workbook XML parsing.

## [1.0.0] - 2026-07-14

### Added

- Local-first Streamlit workflow for respondent-level satisfaction and NPS driver analysis.
- Editable multi-item construct setup with explicit reverse scoring and documented completion rules.
- Raw and standardized Cronbach's alpha, deterministic bootstrap intervals, corrected item–total correlation, alpha-if-deleted, and inter-item correlations.
- Standardized and raw OLS coefficients with HC3 robust intervals and explicitly exploratory p-values.
- Exact LMG/Shapley R² decomposition through ten drivers and deterministic permutation approximation for larger models.
- R², adjusted R², RMSE, MAE, five-fold validation, VIF, rank, condition, leverage, Cook's-distance, retention, and missingness diagnostics.
- Correct aggregate NPS composition and deterministic bootstrap interval while retaining the original 0–10 score for modeling.
- Excel, CSV ZIP, and JSON evidence packs with source fingerprint, reproducibility settings, software versions, diagnostics, and warnings.
- Deterministic fictional customer-experience demo, CSV/Excel templates, data/method/decision documentation, and automated tests.
- Signal-family branding, reserved port 8594, local launchers, non-root Docker runtime, CI, security/privacy policies, citation metadata, and AGPL-3.0-or-later licensing.
