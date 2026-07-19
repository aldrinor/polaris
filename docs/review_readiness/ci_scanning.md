# CI Supply-Chain / Hygiene Scanning (report-only)

**Status:** Phase 3B. All scans below run in the **report-only** `python-ci` workflow
(`.github/workflows/python_ci.yml`) under a job-level `continue-on-error: true` and per-step
`|| true`. They are **informational** and do **NOT** block merges. CI stays report-only until
the flakiness bar (`flakiness_policy.md` §1) is met.

## Baseline before this change
Per the 3B setup audit, **none** of the required scan classes existed:
- No dependency-hash check (no `pip --require-hashes` / hashed requirements).
- No license scan (no `pip-licenses` / `licensecheck` / `cyclonedx` / SBOM).
- No secret scan (no `gitleaks` / `detect-secrets`).
- No SAST / vuln scan (no `bandit` / `pip-audit` / `safety` / `semgrep` / `trivy`).

The only pre-existing supply-chain hygiene was: GitHub Actions SHA-pinned in every workflow,
and `web_ci.yml`'s `verify_pip_resolution` job (`pip install --dry-run`). The `sha256sum` usage
in the codex workflows is review-artifact diff-binding, **not** dependency-hash pinning.

## Scans added (report-only)

All steps live in the `supply_chain_scan` job of `python_ci.yml`. They are referenced by
their step `name:` (the workflow does not assign step `id:`s).

| Scan class | Tool | Step name in `python_ci.yml` | What it reports |
|-----------|------|------------------------------|-----------------|
| Dependency integrity | `pip check` | `Dependency integrity — pip check (report-only)` | Broken/inconsistent installed dependency tree |
| Dependency vuln scan | `pip-audit` | `Dependency vuln scan — pip-audit (report-only)` | Known CVEs against the resolved requirements |
| License scan | `pip-licenses` | `License scan — pip-licenses (report-only)` | License of every installed dependency (flags copyleft manually) |
| Secret scan | `detect-secrets` | `Secret scan — detect-secrets (report-only)` | Hard-coded secrets / high-entropy strings in the tree |

## Honesty notes
- The scanning tools are **not** committed as installed results. Each step installs the tool in
  CI (`pip install pip-audit pip-licenses detect-secrets`) where it is available, then runs it.
  **No scan output is fabricated in this repo** — results are produced by the CI runner only.
- These steps are report-only. Promotion to required checks is gated on the same ratchet as the
  test suite (see `flakiness_policy.md` §1); do not remove `continue-on-error` / `|| true` until
  that bar is met.
- A future hardening step (out of 3B scope) is dependency **hash pinning** via
  `pip-compile --generate-hashes` + `pip install --require-hashes`; `pip check` here is the
  report-only integrity precursor, not the enforced hash gate.

## Reading the output locally
```
pip check
pip install pip-audit pip-licenses detect-secrets
pip-audit -r requirements.txt || true
pip-licenses --format=markdown || true
detect-secrets scan > .secrets.report.json || true
```
