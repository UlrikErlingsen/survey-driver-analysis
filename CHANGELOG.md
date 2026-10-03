# Changelog

All notable changes to Driver Signal are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.0] - 2026-10-03

### Larger datasets

- Larger datasets: run locally, Driver Signal has no built-in limit on file size, respondents, cells, items or drivers (was 200 MB with an in-code ceiling of 500 MB, 500,000 rows, 8,000,000 cells, 30 MB JSON, 30 items and 20 drivers); memory is the limit, and running out of memory gives a plain message. A public demo (`SIGNAL_PUBLIC=1`) keeps those old values as demo limits, all in the new `driversignal.limits` module, with messages that say the downloaded app has none.
- CSV files are read by pandas' fast C parser with a detected delimiter, in 250,000-row chunks, and numbers are stored in the smallest lossless type (rating scales in one byte): a 5,000,000-respondent, 223 MB survey loads in about 5 seconds and holds about 120 MB. Loaded frames are no longer copied once more after reading.
- Every respondent enters every calculation. Above 200,000 complete respondents the regression, HC3 covariance, leverage, Cook's distance and cross-validation are accumulated in row chunks from a QR factor and cross-products instead of three statsmodels fits (same estimates; 16 drivers × 4.85 million respondents need about 4 GB instead of 11 GB). Item-total correlations and alpha-if-deleted come from one covariance matrix, VIF from the predictors' cross-product matrix. More than 20 drivers use the existing fixed-seed permutation approximation of LMG/Shapley.
- An alpha bootstrap that would resample more than 50,000,000 cells no longer stops the analysis: it resamples a seeded subsample of at least 2,000 complete rows and rescales the interval to the full sample by sqrt(m/n). The scale summary (`alpha_bootstrap_rows`), a scale warning and the manifest (`alpha_bootstrap_basis`) label it.
- Exports keep every row: the influence table holds all model rows in CSV and JSON (large tables stream straight from pandas into the JSON file), and an Excel sheet longer than Excel's 1,048,576 rows is cut there with an "Excel row limit" note sheet. With Streamlit versions that support it, each file is built only when its download button is clicked. The residual chart draws at most 5,000 points (the 500 with the highest Cook's distance plus a seeded sample) and says so. The data page's column profile is computed once per loaded table.
- Launchers default `DRIVERSIGNAL_MAX_UPLOAD_MB` to 10000 and the Docker image sets `STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10000`. Signal Hub mode (`SIGNAL_HUB=1`) is unchanged.

### Suite

- Suite: Rival, Reach, Learn and Blueprint Signal added to the suite table (README) and to the theme copy's app list; `.streamlit/config.toml` carries Signal Hub's 10,000 MB upload cap.

## [1.1.0] - 2026-10-02

Signal brand refresh and Signal Hub entry point. The analysis, statistics, data contract and evidence-pack contents are unchanged.

### Brand

- Display name written **Driver Signal** (with a space) in the app, README, docs, launchers, policies, issue templates and metadata (including the evidence-pack `product` field). Package, file, Docker and environment-variable names stay `driversignal` / `DRIVERSIGNAL_*`.
- The app uses the shared `signal_theme` module (Organic Signal design, Research family colour `#a06f1f`, Figtree): sidebar lockup, masthead, hero, cards, notes, footer and the mark as favicon replace the pasted styles.
- Every chart uses the Driver Signal Plotly template and the shared chart roles (importance and alpha estimates in the family colour, intervals and reference lines in neutral tones, positive and negative associations at the two ends of the diverging palette) and is shown through `sig.chart`. The observed-versus-fitted chart now keeps its "Observed outcome" axis title.
- New banner, social preview and marks in `assets/`; the old banner SVG is removed. `.streamlit/config.toml` uses the family colours and keeps the 200 MB upload limit.
- README follows the Signal template; bug-report, feature-request and config issue templates added.
- Embedded Figtree font, no Google Fonts request: the re-synced `signal_theme` loads Figtree from the new `signal_font` module, and the chart colorway uses the per-family contrast order.

### Signal Hub contract

- `driversignal.ui` exposes `APP_INFO` and `render()`, so Signal Hub can embed the app; `app.py` is now a thin standalone entry point.
- All session-state and widget keys are namespaced `driver:` (including the page selector).
- The Plotly figures moved from `driversignal.plotting` to `driversignal.ui.plotting`. `streamlit` and `plotly` moved to a `ui` extra (also in `test`); the analysis core installs without them. `requirements.txt` still lists everything.
- The demo survey and starter templates are generated in code (`driversignal.examples`, byte-identical to `examples/`), so the demo also works from an installed package; `scripts/generate_examples.py` reuses the same functions.
- Opens with the fictional demo preloaded: the demo survey loads on first run when the session has no data (also inside Signal Hub). The demo buttons restore it, an upload replaces it, and **Clear survey** leaves the session empty.- New tests: no Streamlit/Plotly import outside `driversignal.ui`, `render()` runs from a script (and from an installed copy of the package) without a page config, every widget key is namespaced, and the README follows the Signal template.

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
