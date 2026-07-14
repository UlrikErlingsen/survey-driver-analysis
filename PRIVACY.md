# DriverSignal privacy notes

DriverSignal is designed to run locally. It includes no user accounts, advertising, product analytics, telemetry, external AI calls, or built-in survey database.

## When you run it on your computer

- Uploaded files are read into the Streamlit process running on that computer.
- Analysis happens in memory; DriverSignal does not intentionally send survey responses to the project maintainer or a third-party API.
- The source file is never modified.
- Excel, CSV ZIP, and JSON exports are created only when requested.
- Closing the process clears the in-memory session. The app itself does not persist the upload.

The launchers may contact Python package indexes on first use to install open-source dependencies. That installation traffic does not include uploaded survey data.

## Data minimization

DriverSignal does not need names, email addresses, telephone numbers, postal addresses, direct customer IDs, or open-text responses. Remove direct identifiers and unnecessary columns before upload. A pseudonymous key can still identify someone when combined with other data.

Ratings, demographics, service experiences, and recommendation responses may be confidential, personal, or sensitive depending on the survey. Small groups and unusual combinations can permit re-identification without a name. Apply the study's consent, access, purpose-limitation, retention, and deletion rules.

## Exports

Evidence packs contain analysis settings, a source fingerprint, row retention, aggregate outcome and scale statistics, item diagnostics, model results, and source row numbers with leverage/Cook's-distance flags. They deliberately exclude raw survey responses, observed outcomes, fitted values, residuals, and direct identifiers. Treat every export as potentially sensitive research or customer material.

## When someone hosts it

A hosted deployment changes the trust boundary: uploaded files travel to and are processed by the selected server. The deployment operator—not this source tree—controls and is responsible for authentication, authorization, TLS, network controls, logs, backups, retention, deletion, hosting jurisdiction, incident response, privacy notices, consent, contracts, and applicable law.

The DriverSignal code does not add persistent upload storage, but a host or its infrastructure may. Do not upload confidential, personal, or regulated data until the operator has documented those controls.

## Reporting a concern

Email [code.modular578@passmail.net](mailto:code.modular578@passmail.net) with the subject `[DriverSignal privacy]`. If private vulnerability reporting is enabled, the repository's [private security advisory form](https://github.com/UlrikErlingsen/survey-driver-analysis/security/advisories/new) is also suitable. Never put sensitive data or an exploitable report in a public issue.
