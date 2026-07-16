# Changelog

All notable changes to DriverSignal are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
