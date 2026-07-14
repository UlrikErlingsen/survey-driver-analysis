# DriverSignal decision guide

## Start with the decision, not the ranking

Write down:

- the population and survey field period;
- the satisfaction or recommendation outcome;
- the business decision and planning horizon;
- which experiences can realistically be changed;
- possible customer or employee harms;
- the evidence that would justify action.

A technically strong model can still answer the wrong decision.

## Read the output in this order

### 1. Retention and sampling

Check source rows, outcome availability, full-model complete cases, and missingness. Ask who never entered the survey, who abandoned it, and whether missingness is related to experience or outcome. A precise estimate on a selected sample is still selected.

### 2. Construct meaning

Read each item and its reverse-scoring rule. Confirm that the construct is coherent in meaning, timing, and response scale. Do not use alpha to rescue a construct that has weak content validity.

### 3. Reliability diagnostics

Read raw alpha, its bootstrap interval, standardized alpha, mean inter-item correlation, corrected item–total correlation, and alpha-if-deleted together. Investigate negative item–total correlations and very high alpha. Do not auto-delete.

### 4. Model strength

Compare in-sample and cross-validated R². Large deterioration indicates instability or overfit. Check RMSE in the outcome's original units. A model can rank drivers while explaining little overall variance; keep full-model R² beside every importance share.

### 5. Priority and direction

LMG/Shapley R² contribution is the primary priority ranking when predictors overlap. Standardized beta gives conditional direction. A large importance contribution with a small or unstable beta can occur when predictors share signal. A negative beta can reflect suppression, scoring problems, post-treatment conditioning, or a real negative relationship.

If the model is rank deficient, stop before interpreting separate directions or building an action brief. DriverSignal withholds those claims; remove or combine duplicate and perfectly overlapping drivers, then analyze again.

### 6. Overlap and influence

High VIF means separate betas are sensitive to small data or specification changes. Cook's-distance and leverage flags identify rows worth a sensitivity check, not rows to delete automatically. Refit with and without justified influential cases only as a documented sensitivity analysis.

## Add the business layer

For each leading measured priority, add:

| Question | What to document |
|---|---|
| Reach | How many people experience the issue? |
| Feasibility | Can the organization change it in the planning window? |
| Cost | What resources and opportunity cost are required? |
| Risk | What customer, employee, legal, or brand harms could follow? |
| Evidence | Which qualitative, operational, behavioral, or experimental data agree? |
| Measurement | What outcome and side effects will be tracked? |

A lower-ranked driver can be a better intervention if it has greater reach, lower cost, less risk, or stronger causal evidence.

## Design the next test

Prefer a bounded, reversible change. Pre-specify:

- target population and assignment unit;
- intervention and comparison condition;
- primary outcome and minimum meaningful effect;
- timing and exposure window;
- sample-size or precision plan;
- guardrail outcomes and stopping rules;
- analysis and missing-data rules.

Where randomization is unavailable, state the identification assumptions of the quasi-experimental or staged design. Do not describe a before/after correlation as incremental impact without a credible counterfactual.

## Communicate with calibrated language

Prefer:

- “Service receives 0.18 of model R² and has a positive conditional association.”
- “The model explains 42% in sample and 39% in five-fold validation.”
- “Value and Ease overlap strongly; separate beta estimates are less stable.”
- “This priority becomes a hypothesis for a targeted test.”

Avoid:

- “Service causes NPS.”
- “Improving Service by one point will increase NPS by exactly this coefficient.”
- “Alpha above .70 proves the scale is valid.”
- “The p-value shows this is the right investment.”

## Revisit after action

Track implementation fidelity, exposure, the original outcome, operational behavior, and guardrails. Re-field the survey when appropriate. Compare construct reliability, sample composition, outcome distribution, model fit, and priority stability. Treat the model as a revisable measurement system, not a permanent league table.
