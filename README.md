<p align="center">
  <img src="assets/driversignal-banner.svg" alt="DriverSignal — see what moves with satisfaction and what to test next" width="100%">
</p>

<p align="center">
  <a href="https://github.com/UlrikErlingsen/survey-driver-analysis/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/UlrikErlingsen/survey-driver-analysis/actions/workflows/tests.yml/badge.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-173C3A?logo=python&logoColor=white">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-app-D95B40?logo=streamlit&logoColor=white">
  <a href="LICENSE"><img alt="License: AGPL-3.0-or-later" src="https://img.shields.io/badge/License-AGPL--3.0--or--later-36534E"></a>
</p>

<p align="center"><strong>Open survey-driver analysis — respondent ratings in, reliable constructs and challengeable priorities out.</strong></p>

**DriverSignal** helps marketers and researchers understand which measured experiences are most strongly associated with satisfaction or a 0–10 recommendation score. It combines a plain-language priority view with scale-reliability checks, robust standardized regression, correlated-predictor importance, model diagnostics, and a reproducible evidence pack.

The app is built for two reading speeds: a marketer can start with the priority map and decision brief; an analyst can inspect item–total correlations, alpha-if-deleted, inter-item correlations, HC3 intervals, VIF, held-out performance, influence diagnostics, and every analysis setting. Everything runs locally with open-source Python packages. There is no account, telemetry, external AI call, or built-in data storage.

## Read this first

> **“Driver” is business shorthand for measured association—not proof of cause.** A cross-sectional survey can suggest what to investigate and test. It cannot by itself rule out respondent selection, common-method bias, omitted variables, reverse direction, post-treatment controls, or confounding.

DriverSignal therefore keeps two questions separate:

1. **Priority:** how much of the model's explained variance should each correlated predictor receive?
2. **Direction:** holding the other included predictors constant, is the measured association positive or negative, and how uncertain is it?

LMG/Shapley relative importance answers the first question. Standardized OLS coefficients with HC3 robust intervals address the second. Neither turns observational survey data into a causal design.

## Try it in three minutes

1. Start the app and load **Demo · customer experience** from the sidebar.
2. Keep `recommend_0_10` as the outcome. DriverSignal recognizes the four fictional constructs: Service, Value, Ease, and Trust.
3. Notice that `ease_reverse_effort` is explicitly reverse scored against the declared 1–7 endpoints.
4. Run the analysis. Review raw and standardized Cronbach's alpha, item diagnostics, and bootstrap intervals.
5. Open the driver model. Compare the nonnegative LMG/Shapley priority bars with the signed standardized-beta forest plot.
6. Inspect retention, VIF, held-out R², observed-versus-fitted results, Cook's-distance flags, and the exported evidence pack.

The demo is deterministic synthetic teaching data. It describes no real person, company, brand, or survey.

## Survey data

Use one row per respondent and one column per question or field. CSV, Excel, and JSON are supported.

| respondent_id | recommend_0_10 | service_speed | service_resolution | service_care | value_fair | value_quality | value_clear |
|---|---:|---:|---:|---:|---:|---:|---:|
| R001 | 9 | 7 | 6 | 7 | 5 | 6 | 6 |
| R002 | 6 | 3 | 4 | 4 | 4 | 5 | 3 |

The outcome and selected items must be numeric. IDs, region labels, free text, and other unused columns can remain in the source table, but DriverSignal does not model them. Remove direct identifiers and unnecessary sensitive fields before upload.

The built-in workflow:

- selects the original satisfaction or recommendation response;
- assigns items to constructs with an editable setup table;
- reverse scores only explicitly marked items against declared theoretical endpoints;
- creates construct means when the stated minimum answered proportion is met;
- removes structurally constant candidates, then uses one shared complete-case sample for the full driver model and every importance subset;
- reports starting rows, retained rows, row loss, and per-field missingness.

No silent median imputation is performed. See the [data guide](docs/data_guide.md) for role selection, missingness, reverse scoring, and privacy guidance.

## Scale reliability

For each multi-item construct, DriverSignal reports:

- raw Cronbach's alpha;
- deterministic respondent-bootstrap interval;
- standardized alpha and mean inter-item correlation;
- corrected item–total correlation;
- alpha if each item were deleted;
- complete respondents, item means, standard deviations, and missingness;
- inter-item correlations and structured warnings.

Reliability calculations use one listwise-complete sample within each scale. A one-item measure has no alpha. With two items, alpha is a transformation of their correlation. Negative alpha is preserved rather than clipped.

Alpha does **not** establish unidimensionality, construct validity, temporal stability, good wording, or measurement equivalence across groups. The familiar .70 convention is context, not a universal pass/fail law; values above .95 can indicate redundancy. DriverSignal never auto-reverses or auto-deletes an item to improve alpha.

## Driver model

The primary model standardizes the outcome and scored drivers, fits multiple linear regression, and reports HC3 heteroskedasticity-robust intervals. The 0–10 recommendation response is modeled directly; aggregate NPS is reported separately because NPS has no respondent-level value.

Outputs include:

- standardized and raw coefficients, robust intervals, and explicitly exploratory p-values;
- in-sample R², adjusted R², RMSE, and MAE;
- deterministic five-fold cross-validated R² and RMSE when the sample is large enough;
- VIF and standardized-design condition diagnostics;
- fitted values, residuals, leverage, and Cook's distance;
- constant-column removal and rank-deficiency safeguards that withhold non-identifiable coefficient claims.

For correlated predictors, standardized beta is not a stable importance ranking. DriverSignal therefore decomposes the full model's R² with LMG/Shapley importance. Up to ten drivers use all subsets exactly. Larger models use a fixed-seed permutation approximation and label it clearly. Each nonnegative contribution sums to full-model R²; beta supplies direction.

See [methods](docs/methods.md) for formulas, conventions, diagnostics, and limits.

## NPS handling

Standard NPS responses must be whole numbers from 0 through 10:

- detractors: 0–6;
- passives: 7–8;
- promoters: 9–10;
- `NPS = promoter % − detractor %`.

DriverSignal reports group shares, aggregate NPS, and a deterministic respondent-bootstrap 95% interval. The driver model retains the original 0–10 outcome because collapsing it to promoter/non-promoter would discard information. OLS still treats this bounded ordinal score as approximately interval-scaled; that assumption is visible in the evidence pack.

## Evidence pack

The export page creates equivalent Excel, CSV-ZIP, and JSON outputs containing:

- source filename, worksheet, and SHA-256 fingerprint;
- outcome role, scale definitions, reverse scoring, completion rule, and fixed seed;
- software versions and causal-status statement;
- outcome/NPS summary, retention, and missingness;
- reliability summary, item diagnostics, and inter-item correlations;
- coefficients, LMG/Shapley importance, VIF, correlations, model metrics, privacy-safe influence diagnostics, and warnings.

Raw survey responses, observed outcomes, fitted values, residuals, and direct identifiers are deliberately excluded from the evidence pack. The influence table retains only source row number, leverage, and Cook's distance so an authorized local analyst can trace a flagged row in the source.

## Run locally

You need Python 3.10 or newer and a local copy of this project folder.

**macOS:** double-click `run_app.command`.

**Windows:** double-click `run_app.bat`.

The first launch creates a private `.venv` and downloads the open-source dependencies. Later launches reuse it. Or use a terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

DriverSignal uses the reserved local port `8594`. The launchers accept `DRIVERSIGNAL_PORT`, `DRIVERSIGNAL_MAX_UPLOAD_MB`, `DRIVERSIGNAL_NO_BROWSER`, and `DRIVERSIGNAL_DEBUG` environment variables.

### Docker

```bash
docker build -t driversignal .
docker run --rm -p 8594:8594 driversignal
```

Then open `http://127.0.0.1:8594`. The container runs as a non-root user. This repository does not promise a hosted public instance.

## No install? Give this file to an AI

Don't want to install anything? [AI_ANALYST.md](AI_ANALYST.md) is a single copy-paste file that turns a capable AI assistant (Claude, ChatGPT, Gemini, …) into this analysis. Copy the file into a chat, add your data, and the AI follows the same published methods and honesty rules as the app. The app is still the more private option: local mode keeps your data on your computer, while a cloud AI sees whatever you paste.

## Tests and development checks

```bash
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
python -m build
```

The test suite covers analytical reliability fixtures, reverse scoring, missing-data samples, deterministic bootstraps, synthetic coefficient recovery, affine invariance, exact and approximate Shapley allocation, collinearity and rank deficiency, NPS boundaries, secure exports, generated examples, and full Streamlit workflows. Statistical changes should be checked against analytical values or independently generated synthetic data.

## A disciplined decision workflow

1. Write the decision and population before opening the model.
2. Check survey wording, sampling, response rate, timing, and whether any predictor is measured after the outcome.
3. Define constructs from theory; do not group items merely because alpha rises.
4. Read retention and missingness before comparing estimates.
5. Compare LMG/Shapley priority, beta direction, robust interval, VIF, and held-out performance.
6. Combine the survey evidence with feasibility, reach, cost, qualitative evidence, and customer harm.
7. Pre-register a bounded experiment or staged change where possible.
8. Measure the intended outcome and side effects, then update the model rather than freezing the first ranking.

See the [decision guide](docs/decision_guide.md) for a practical interpretation checklist.

## Privacy and responsible use

Local mode reads uploads into the Python process on that computer. DriverSignal adds no accounts, advertising, telemetry, external AI calls, or built-in persistence. Exports are created only when requested and source files are never modified.

Respondent-level surveys can be sensitive even without names. Remove contact details, direct customer identifiers, free text, precise locations, protected characteristics not needed for the analysis, and small-group combinations. A hosted deployment changes the trust boundary; read [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md).

## Relationship to the Signal suite

These apps share a visual language but answer different questions:

- **[WorthSignal](https://github.com/UlrikErlingsen/customer-value-analytics)** asks what customers and relationships are worth.
- **[SegmentSignal](https://github.com/UlrikErlingsen/customer-segmentation)** asks whether customers form stable, useful groups.
- **[ChoiceSignal](https://github.com/UlrikErlingsen/conjoint-analysis)** asks how product attributes drive choice.
- **[AdoptSignal](https://github.com/UlrikErlingsen/adoption-forecasting)** asks when a new product gets adopted.
- **[PositionSignal](https://github.com/UlrikErlingsen/brand-positioning)** asks where brands sit relative to competitors.
- **[AllocSignal](https://github.com/UlrikErlingsen/marketing-mix-allocation)** asks where the next marketing budget should go.
- **[GateSignal](https://github.com/UlrikErlingsen/launch-decision-gate)** asks whether a concept should receive the next bounded investment.
- **[ExperimentSignal](https://github.com/UlrikErlingsen/experiment-analysis)** asks whether a randomized treatment caused a change worth acting on — the natural next step when DriverSignal flags a driver that deserves a causal test.
- **[MeasureSignal](https://github.com/UlrikErlingsen/measurement-validation)** asks whether a multi-item score measures what you think it does — worth running before DriverSignal when a model depends on composite scores.
- **[TextSignal](https://github.com/UlrikErlingsen/open-text-analysis)** asks what recurring language patterns appear in open-ended responses.
- **[TagSignal](https://github.com/UlrikErlingsen/pricing-analysis)** asks what price range is supported and how contribution moves, from assigned-price, historical, or willingness-to-pay evidence.
- **[RecommendSignal](https://github.com/UlrikErlingsen/recommender-evaluation)** asks which recommendation policy performs under temporal replay.
- **[TraceSignal](https://github.com/UlrikErlingsen/journey-path-analysis)** asks how logged customer journeys actually unfold: transitions, path support, drop-off, and Markov removal sensitivity, with no causal channel credit.
- **[TrackSignal](https://github.com/UlrikErlingsen/brand-tracking)** asks whether brand measures moved across tracking waves by more than a declared practical threshold.
- **DriverSignal** asks which measured experiences are associated with satisfaction or recommendation, whether their scales cohere, and what deserves a causal test.

See the maintained suite overview at [ulrikerlingsen.com](https://ulrikerlingsen.com).

## Method references

- Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. *Psychometrika, 16*, 297–334.
- White, H. (1980). A heteroskedasticity-consistent covariance matrix estimator. *Econometrica, 48*, 817–838.
- MacKinnon, J. G., & White, H. (1985). Some heteroskedasticity-consistent covariance matrix estimators with improved finite sample properties. *Journal of Econometrics, 29*, 305–325.
- Lindeman, R. H., Merenda, P. F., & Gold, R. Z. (1980). *Introduction to Bivariate and Multivariate Analysis*. Scott Foresman.
- Grömping, U. (2007). Estimators of relative importance in linear regression based on variance decomposition. *The American Statistician, 61*(2), 139–147.

If DriverSignal supports research or teaching, cite the software metadata in [CITATION.cff](CITATION.cff) and the primary source appropriate to the selected method.

## License

DriverSignal is free software under **AGPL-3.0-or-later**. Commercial use is allowed; distribution and modified network services carry the source-sharing obligations in [LICENSE](LICENSE). The license covers this project's code and documentation, not ownership of the published methods it implements.

This application was developed with AI coding assistance and checked through source review, analytical fixtures, synthetic recovery tests, automated app tests, and visual inspection. Verify material decisions independently; no warranty is provided.
