# Security policy

## Supported versions

Security fixes are targeted at the latest published ContextSpindle release and the current `main` branch. Older releases, including the historical DiffHound `v0.2.0` release, are not maintained as ContextSpindle versions. This is a maintenance policy, not a guarantee of a fix or response time.

## Report a vulnerability privately

Use GitHub's [private vulnerability reporting](https://github.com/reacherwu/ContextSpindle/security/advisories/new) for suspected vulnerabilities in ContextSpindle. Do not open a public issue or pull request containing exploit details, private task records, credentials, or other sensitive data. If the private-reporting form is unavailable, email the project maintainer at `reacherwu@gmail.com` with a minimal description and request a secure follow-up channel before sending sensitive material.

Useful initial details include the affected version and platform, impact, a minimal reproduction using synthetic data, and any proposed mitigation. We will assess the report and coordinate disclosure with the reporter. No specific response or resolution deadline is promised.

The local task ledger may contain sensitive project context. Protect workspace permissions and backups. Checksums detect accidental corruption; they are not a defense against a writer with filesystem access. See the [operations runbook](docs/OPERATIONS.md) for the current security boundary.
