# Security and privacy

## Supported deployment

This experimental 0.1.x application is intended for a single trusted user.
There is no client authentication, per-user authorization, or built-in TLS.
Anyone who can reach the backend can invoke its exposed operations, including
job creation and learning-data deletion. A job identifier is not a credential.

Keep the backend bound to `127.0.0.1` by default. Do not port-forward it or expose
it directly to the public internet. A private LAN is not an authentication
boundary: restrict firewall access to trusted clients. Any broader deployment
requires separately configured authentication, access control, and encryption.
Keep LM Studio private as well. Provider API keys authenticate outbound inference
requests; they do not protect this application's inbound API.

## Data handling

- The plug-in renders JPEG previews and sends image content and request metadata
  to the backend. Durable Auto Develop uses binary uploads; synchronous requests
  can use Base64. Do not assume preview metadata, including location, is stripped.
- With a local provider at a loopback address, inference is local. Configuring a
  remote provider sends data there. Selecting Gemini sends previews and prompts
  to Google's API; provider terms and retention policies apply. Prompts can
  include aggregate learning preferences.
- Backend job storage defaults to `data/jobs/` and retains previews, manifests,
  checkpoints, and results. Lightroom also retains local durable-job material
  under its configured job root, which can include catalog paths and filenames.
  Cancellation stops work; it is not data erasure. No automatic retention period
  is implemented. Stop the backend and ensure a job is no longer needed before
  manually removing its stored folder. Remove local plug-in copies separately.
- Optional learning stores edit/feedback information in
  `data/autodevelop_learning.sqlite3`. See the
  [learning documentation](docs/LEARNING_SYSTEM.md) for its fields and reset APIs.
- Logs, error responses, and optional invalid-response diagnostics can contain
  sensitive context. Diagnostics are disabled by default; redaction is best
  effort. Review all shared diagnostics manually.
- Files are not encrypted by this application. Protect storage, backups, and
  the Lightroom catalog with OS permissions and encryption where needed.

Keep secrets in environment variables or a machine-local `.env`. Never include
them in YAML examples, issues, screenshots, or committed history. Rotate any
credential that has been exposed; deleting it from the latest commit is not
sufficient. The repository's ignore rules do not erase earlier commits.

## Known dependency advisories

The preparation audit queried OSV and pip-audit on November 25, 2026. The pinned
snapshot in [requirements.txt](requirements.txt) includes affected versions:

| Package | Pinned version | Advisory information |
|---|---|---|
| Certifi | 2026.7.22 | [GHSA-6q48-6c7w-9gw2](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2), fixed in 2026.10.18 |
| Pillow | 12.3.0 | Multiple advisories, including [GHSA-22hg-r758-rrw9](https://osv.dev/vulnerability/GHSA-22hg-r758-rrw9) and [GHSA-24rc-8hj2-v98c](https://osv.dev/vulnerability/GHSA-24rc-8hj2-v98c), with fixes in 13.0.0 |

The maintainer requested that dependency versions remain unchanged during
repository preparation. The current Pillow range in
[pyproject.toml](pyproject.toml) excludes version 13. These findings remain
unresolved; publishing documentation or passing tests does not fix them or
establish that the application is security-cleared. Advisory applicability to
each application code path has not been fully assessed.

Editable installation resolves dependency ranges and can differ from the pinned
snapshot; a fresh environment can receive a newer Certifi. The tests workflow
checks functionality and dependency consistency, not vulnerability clearance.
Review dependency advisories again before deployment or processing untrusted
images. Dependency upgrades require separate compatibility testing.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** option on this repository's Security tab
if private vulnerability reporting is enabled. If unavailable, open an issue
requesting a private contact channel without including exploit details, secrets,
photos, or personal data. Do not publish sensitive reproduction material.

Include the affected commit/version, impact, and a sanitized reproduction over
the agreed private channel. This community project provides no guaranteed
response time. Security fixes target the current main branch; older snapshots
have no separate maintenance commitment.
