# Driver Signal data guide

## Unit of analysis

Use one row per respondent. Driver Signal does not aggregate repeated rows, detect duplicate people, or infer which response to keep. If the same person appears more than once, decide whether the records are independent, repeated measures, or duplicates before analysis. Ordinary HC3 regression does not account for respondent, team, store, or market clustering.

## Required roles

Select:

- one numeric outcome: a satisfaction rating or the original 0–10 recommendation response;
- one or more numeric survey items;
- an optional construct name for items intended to form a multi-item scale;
- an explicit reverse-scored flag when question wording requires it.

The outcome cannot also be a driver. A construct score replaces its source items in the model, so Driver Signal never includes both the composite and its components together.

## Recommended table shape

| respondent_id | satisfaction | service_speed | service_helpful | service_resolution | value_fair | value_quality | value_clear |
|---|---:|---:|---:|---:|---:|---:|---:|
| R001 | 6 | 7 | 6 | 7 | 5 | 6 | 6 |
| R002 | 4 | 3 | 4 | 3 | 4 | 5 | 3 |

CSV, XLSX, XLS, XLSM, and JSON are supported. For Excel workbooks, choose the survey worksheet in the sidebar. The first row must contain column names. Duplicate or blank column names are made unique on import.

## Numeric conversion

Numeric strings such as `"7"` are accepted. Selected fields containing non-numeric text or infinity are rejected rather than silently recoded. Missing cells remain missing.

Do not encode categorical labels as arbitrary integers and interpret their coefficient as a continuous driver. Convert ordered categories only when an interval-style interpretation is defensible. Categorical control variables are outside the current release.

## Construct names

Items with the same non-empty construct name become one row-mean score. Items with a blank construct name remain standalone predictors. Driver and construct names must be unique.

Group items because theory and wording support a common construct—not because an algorithm found a higher alpha. Reliability is checked after grouping; it does not invent the group.

## Reverse scoring

Reverse scoring uses declared theoretical endpoints:

`reversed value = scale minimum + scale maximum − original value`

For a 1–7 item, `1 → 7`, `2 → 6`, and `4 → 4`. Values outside the declared endpoints are rejected. Driver Signal preserves the source column and reverses only an analysis copy. It never automatically reverses an item because of a negative correlation.

## Construct completion rule

Choose one documented rule:

- **All items:** strict and easiest to defend.
- **At least 80%:** allows limited item-level missingness.
- **At least two-thirds:** more permissive; useful only when content coverage remains acceptable.

The required number rounds upward. A three-item scale therefore requires three answers under 80%, and two under the two-thirds rule. The construct mean stays on the original response scale.

Structurally constant candidates are removed first. The final driver model then applies listwise deletion across the outcome and every retained predictor. Every coefficient and LMG/Shapley subset uses this same retained sample.

## Missingness review

Driver Signal reports source rows, rows with the outcome, rows complete for the full model, exclusions, and per-field missingness. Retention below 80% triggers a warning. This is a review threshold, not a proof that missingness is ignorable above 80%.

Complete-case analysis can be biased when missingness depends on the unobserved response or variables related to the outcome. Driver Signal does not silently impute. If multiple imputation is appropriate, perform it in a validated workflow and pool estimates under the relevant rules; do not treat one filled-in table as certain data.

## Standard NPS

For NPS mode, responses must be whole numbers from 0 through 10. Driver Signal classifies:

- 0–6 as detractors;
- 7–8 as passives;
- 9–10 as promoters.

The aggregate NPS is promoter percentage minus detractor percentage. The regression uses the original 0–10 response because aggregate NPS has no respondent-level value.

## Sample size

The model needs more complete rows than estimated parameters. Driver Signal also warns below `max(50, 10 × (drivers + 1))`. This is a stability heuristic, not a theorem or power calculation. Reliability estimates with fewer than 50 complete responses receive a separate caution.

Plan sample size from the intended decision, expected effect sizes, number of parameters, reliability, design effects, missingness, subgroup needs, and uncertainty target. A large convenience sample can still be systematically biased.

## Privacy checklist

Before upload, remove or generalize:

- names, email addresses, phone numbers, and direct customer IDs;
- open-text comments and support transcripts;
- exact addresses, fine-grained locations, and precise timestamps;
- sensitive attributes not required for the stated analysis;
- rare combinations that make an individual recognizable.

Use pseudonymous keys only when row tracing is genuinely necessary. Driver Signal exports source row numbers with leverage and Cook's distance so an authorized analyst can trace influence flags, but it does not export raw responses, observed outcomes, fitted values, residuals, or IDs.

## Safety limits

The local loader limits file size, rows, total cells, expanded Excel size, and JSON size. These controls reduce accidental resource exhaustion; they are not a substitute for a trusted deployment. Uploaded formulas are never executed. Exported strings beginning with spreadsheet formula characters are neutralized.
