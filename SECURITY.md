# Security policy

## Supported version

Security fixes are applied to the latest version on the `main` branch. Older release branches are not currently maintained.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability involving file handling, code execution, dependency compromise, formula injection, or disclosure of uploaded survey data. Email [code.modular578@passmail.net](mailto:code.modular578@passmail.net) with the subject `[Driver Signal security]`. If GitHub private vulnerability reporting is enabled, use the [private security advisory form](https://github.com/UlrikErlingsen/survey-driver-analysis/security/advisories/new).

Please include the affected version or commit, clear reproduction steps using synthetic data, expected impact, and a suggested mitigation if available. Reports are reviewed on a best-effort basis; this volunteer project does not promise a formal response-time SLA. Never attach real respondent data, credentials, or secrets.

## Scope and deployment responsibility

Driver Signal reads tabular CSV, Excel, and JSON. It does not accept serialized Python models or intentionally execute spreadsheet macros. The loader limits file size, expanded workbook size, row count, and total cells; spreadsheet exports neutralize formula-like text. The Docker image runs as an unprivileged user. These controls reduce risk but do not make an internet deployment safe by themselves.

Anyone exposing the app over a network remains responsible for authentication, TLS, network isolation, dependency updates, logging, secrets, backups, upload limits, retention, and incident response. Read [PRIVACY.md](PRIVACY.md) before accepting uploads.
