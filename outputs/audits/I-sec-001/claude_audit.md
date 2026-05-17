# Claude architect audit — I-sec-001 (#535)

**Issue:** GH #535 — `codex exec` transcripts can capture `.env` secrets into
committed `.codex/**` artifacts.
**Branch:** `bot/I-sec-001-codex-transcript-scrub`
**Commit 1 (code):** `1a002f1e`
**Brief:** `.codex/I-sec-001/brief.md` — Codex APPROVE iter 5 (P1 trajectory
2→2→2→1→0).

## 1. What shipped

Verdict-only commit policy + a tamper-proof CI gate, per the APPROVE'd brief.

| File | Role |
|---|---|
| `scripts/extract_codex_verdict.py` (new) | `extract`: parse + schema-validate the §8.3.9 verdict block out of a raw transcript, re-serialize canonically, secret-scan, refuse to write on a hit. `validate`: confirm a committed file is a schema-bounded slim block (8 KB cap, no trailing transcript). |
| `scripts/ci/codex_artifact_gate.py` (new) | CI gate logic — denylist raw-transcript filenames, allowlist slim artifacts, content-validate verdict files, secret-scan changed `.codex/**` (A/M/R/C), fast-pass on no `.codex/**` change. |
| `.github/workflows/codex_artifact_gate.yml` (new) | `pull_request_target` workflow — base-sourced control plane, runs every PR, PR content checked out read-only as data. |
| `scripts/autoloop/scan_for_secrets.py` (mod) | +`jina_`/`fc-`/`fw_` vendor patterns + a configured secret-env-NAME assignment pattern. |
| `.gitignore` (mod) | raw codex-transcript filename patterns. |
| `.codex/AUDIT_CYCLE_PROTOCOL.md` (mod) | verdict-only ship-procedure policy section. |
| `tests/test_extract_codex_verdict.py` (new) | 11 tests — extract/parse/serialize/validate + gate path rules. |

## 2. Per-finding verification (against the brief's 5 iterations)

- **VERIFIED — iter-1 P1-1** (verdict block can still hold a secret): `extract`
  runs `scan_for_leaks` on its *output* and exits 4 without writing on a hit;
  CI re-scans. Not relying on "structurally impossible".
- **VERIFIED — iter-1 P1-2 / iter-2 P1-2** (CI must not depend on `.env`
  values; PR-head scanner is tamper-able): `validate` has zero `.env`
  dependency; the gate workflow is `pull_request_target` so it runs from the
  base ref, and invokes `base/scripts/...` copies — never PR-head code.
- **VERIFIED — iter-2 P1-1** (gate scoped to ADDED only): `changed_codex_paths`
  takes `git diff --name-status` and processes every status except `D`.
- **VERIFIED — iter-3 P1-1** (workflow run-block tamper): trigger is
  `pull_request_target`; GitHub sources the workflow definition from base.
- **VERIFIED — iter-3 P1-2** (filename allowlist ≠ slim content): the gate
  runs `extract_codex_verdict.py validate` on verdict/audit artifacts; the
  8 KB cap + canonical round-trip check reject a raw transcript committed
  under an allowed name.
- **VERIFIED — iter-4 P1** (required-check deadlock): the workflow has no
  `paths:` filter, runs on every PR, and `codex_artifact_gate.py` fast-passes
  (exit 0) when no `.codex/**` changed — safe to be a required check.
- **VERIFIED — iter-4 P2 / brief §3.6 bootstrap**: this PR commits only the
  slim `codex_brief_verdict.txt` (134 bytes, re-extracted from the iter-5
  transcript); the raw `codex_brief_review_iter*.txt` are gitignored and not
  staged.

## 3. Test + smoke

`tests/test_extract_codex_verdict.py` — 11/11 pass offline. Covers: extract
drops trailing transcript prose; last-block-wins; secret-in-verdict → exit 4,
no file written; `validate` rejects oversized + trailing-transcript files;
gate denylist catches all raw-transcript shapes; allowlist permits the slim
set.

## 4. Scope + residuals

- The audit (#535 acceptance d) found 16 pre-existing committed `.env` values;
  the operator reviewed and accepted that exposure (no rotation / no history
  scrub) — `state/resolved_halt_20260517T124325Z_secret_exposure.md`. This PR
  is forward-prevention only; existing tracked transcripts are left as-is (the
  gate covers M/R/C so a future *touch* of one is caught).
- **Operator handoff:** `codex-artifact-gate` must be registered in the
  `polaris` branch-protection required-status-checks set to actually block
  merge. Until then it runs and reports but is advisory. Flagged in the issue
  comment.
- **Documented residual:** the CLAUDE.md §3.0 artifact-convention text should
  also state verdict-only; CLAUDE.md is canonical-pin-protected, so that edit
  is a separate pin-aware change, not in this PR.

## 5. Risk assessment

- No production code path touched — all new files are CI/tooling +
  scanner-pattern additions. Zero behaviour change to the pipeline.
- `scan_for_secrets.py`: only additive (new patterns); the configured-NAME
  pattern could in principle false-positive on a doc literally writing
  `JINA_API_KEY=<20+ chars>` — acceptable (it only `--strict`-fails the gate
  on `.codex/**`, where such a literal would itself be the leak).

## 6. Verdict

Implementation complete, faithful to the iter-5 brief, 11/11 tests green.
Ready for Codex diff review.
