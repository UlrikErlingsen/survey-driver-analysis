# Driver Signal methods

## Analysis contract

Driver Signal is an observational survey-prioritization tool. It scores declared constructs, checks internal consistency, estimates conditional linear associations, allocates explained variance among correlated predictors, and reports model diagnostics. It does not estimate a causal treatment effect.

## Construct scoring

For item `x` declared reverse keyed on theoretical endpoints `L` and `U`:

`x* = L + U − x`

A construct score is the row mean of its scored items when the respondent meets the selected minimum answered proportion. This retains the original item scale. No item is reversed, deleted, or assigned to a construct automatically after analysis begins.

## Raw Cronbach's alpha

For `k` items and one listwise-complete respondent sample:

`alpha = k/(k−1) × (1 − sum(item variances) / total-score variance)`

Sample variances use `ddof=1`. If there are fewer than two items, fewer than two complete respondents, or zero total-score variance, raw alpha is not estimable. Negative values are preserved.

The bootstrap interval resamples complete respondent rows with replacement under a fixed seed and takes the 2.5th and 97.5th percentiles of finite alpha estimates.

## Standardized alpha and item diagnostics

Standardized alpha uses the mean off-diagonal Pearson item correlation `r̄`:

`standardized alpha = k × r̄ / (1 + (k−1) × r̄)`

It is not estimable when the complete correlation matrix contains undefined item correlations. The corrected item–total correlation correlates the focal item with the sum of all other items, excluding the focal item. Alpha-if-deleted recalculates raw alpha on the same complete respondent sample after removing that item.

These statistics are diagnostics. Deleting an item solely to maximize alpha capitalizes on the sample and can damage content validity. Alpha also assumes roughly tau-equivalent items and is not a test of unidimensionality.

## Standardized driver regression

On one complete-case sample, Driver Signal estimates:

`z(y) = beta_1 z(x_1) + ... + beta_p z(x_p) + error`

The standardized beta is the conditional standard-deviation difference in the outcome associated with a one-standard-deviation difference in the predictor, holding other included predictors constant. A second raw-scale fit reports coefficients in outcome units.

Intervals and exploratory p-values use HC3 heteroskedasticity-robust covariance. HC3 improves finite-sample behavior under heteroskedasticity but does not address clustering, repeated observations, omitted variables, functional-form error, measurement error, sampling bias, or endogeneity.

Constant predictors are removed with a warning before the final complete-case sample is formed. If the design is rank deficient, Driver Signal suppresses individual coefficients, intervals, directions, and action prompts as not uniquely identified. It does not pretend a generalized-inverse solution identifies separate effects.

## LMG/Shapley relative importance

With correlated predictors, beta magnitude is not a fair allocation of shared explained variance. Driver Signal uses the LMG/Shapley decomposition:

`phi_j = sum over S not containing j of [ |S|!(p−|S|−1)! / p! ] × [R²(S+j) − R²(S)]`

Every subset uses the same complete-case sample. Up to ten predictors, all `2^p` subsets are evaluated exactly. Above ten predictors, fixed-seed random predictor orderings approximate the average marginal R² contribution. The evidence pack records the exact or approximate method, number of orderings, and seed.

Contributions are nonnegative except for negligible floating-point noise, sum to the full-model R², and are displayed both as absolute R² contribution and percentage of explained variance. A 40% share is not 40% of total outcome variance unless full-model R² equals one. Beta direction is reported separately.

LMG/Shapley fairly allocates statistical overlap. It cannot determine which correlated construct is causal, manipulable, or economically attractive.

## Fit and validation metrics

Driver Signal reports:

- R² and adjusted R²;
- RMSE and MAE in original outcome units;
- deterministic five-fold cross-validated R² and RMSE when sample size permits;
- matrix rank and standardized-design condition number;
- VIF for each predictor;
- leverage and Cook's distance.

Cross-validation assigns respondents to folds with a fixed seed, estimates ordinary least squares on four folds, and predicts the held-out fold. All held-out predictions are combined before R² and RMSE are calculated. A negative CV R² means the model predicts held-out rows worse than the held-out sample's overall mean benchmark.

For predictor `j`, VIF is `1/(1−R²_j)`, where `R²_j` comes from regressing that predictor on all other predictors. Infinite VIF marks perfect linear dependence. Cook's-distance and leverage thresholds are screening rules (`4/n` and `2(p+1)/n`), not automatic deletion criteria.

## NPS

Standard categories are detractors 0–6, passives 7–8, and promoters 9–10:

`NPS = 100 × (promoter proportion − detractor proportion)`

The confidence interval uses a fixed-seed multinomial respondent bootstrap over the three observed category shares. The primary driver model uses the original 0–10 response. This retains information but assumes the bounded score can be treated approximately as interval-scaled in a linear model.

## Missing data

Reliability uses listwise completion within each scale. Construct means may use the declared partial-completion rule. Structurally constant candidates are removed, then the final driver model uses listwise completion across the outcome and every retained driver. No median imputation or pairwise covariance construction is performed.

Pairwise item covariance can be internally inconsistent; one shared reliability sample makes raw alpha, standardized alpha, item–total correlations, and alpha-if-deleted directly comparable. One shared driver sample likewise makes coefficients and all LMG/Shapley subset R² values comparable.

## Causal interpretation

A strong association can arise because the predictor causes the outcome, the outcome changes the predictor rating, a third variable affects both, survey wording creates common-method covariance, respondents self-select, or the model conditions on the wrong variables. Cross-sectional precision does not distinguish these stories.

Translate priority into a causal test when feasible: randomized product or service changes, encouragement designs, staged rollouts, matched-market designs, or defensible quasi-experiments. Pre-specify the outcome, exposure, population, timing, and side effects.

## References

- Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. *Psychometrika, 16*, 297–334.
- White, H. (1980). A heteroskedasticity-consistent covariance matrix estimator. *Econometrica, 48*, 817–838.
- MacKinnon, J. G., & White, H. (1985). Some heteroskedasticity-consistent covariance matrix estimators with improved finite sample properties. *Journal of Econometrics, 29*, 305–325.
- Lindeman, R. H., Merenda, P. F., & Gold, R. Z. (1980). *Introduction to Bivariate and Multivariate Analysis*. Scott Foresman.
- Grömping, U. (2007). Estimators of relative importance in linear regression based on variance decomposition. *The American Statistician, 61*(2), 139–147.
