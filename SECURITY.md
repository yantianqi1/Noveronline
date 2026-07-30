# Security Policy

## Supported Versions

This project is in active pre-1.0 development. Security fixes target the default branch unless maintainers publish release branches.

## Reporting a Vulnerability

Please do not open a public issue for vulnerabilities involving credentials, private manuscripts, user data, database files, LLM traces, authentication bypass, or remote code execution.

Use the repository's private vulnerability reporting page when it is enabled.
If it is unavailable, contact the repository owner privately through the
contact method listed on their GitHub profile. Do not include exploit details
in a public issue.

## Sensitive Data Rules

- Never commit `.env`, API keys, private LLM channel credentials, local databases, upload artifacts, or logs.
- Treat prompt / response traces as sensitive because they may include user manuscript content.
- Revoke and rotate any key that was accidentally committed.
- Prefer minimal reproduction cases over full user documents when reporting issues.

## Runtime Exposure

The default development server is intended for local use. Do not expose it directly to the public internet without adding production-grade authentication, transport security, rate limiting, logging policy, and data retention controls.
