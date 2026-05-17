# Codex BRIEF review — I-sec-001 / GH #535: codex exec transcripts can capture .env secrets into committed .codex/ artifacts

HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

A **BRIEF review** (iter 3) — verify the problem analysis + the proposed fix
approach for GH #535 are correct and complete BEFORE the diff is written.
Acceptance criterion (c) of #535 routes the (a)-vs-(b) decision to you.

## 0.1 Iteration trail — all findings addressed

- iter-1 P1-1 (verdict block can still contain secrets) → §3.2 mandatory scan.
- iter-1 P1-2 (value-based CI backstop unsound) → §3.3 allowlist/denylist.
- iter-1 P2-1 (.gitignore doesn't untrack) → §3.4. iter-1 P2-2 (extractor must
  schema-validate) → §3.1.
- iter-2 P1-1 (CI gate scoped to ADDED only; M/R/C of an already-tracked
  transcript bypasses it) → §3.3: gate covers every changed `.codex/**` path
  with status A/M/R/C (all except D); only fully-unchanged historical files
  are grandfathered.
- iter-2 P1-2 (PR could no-op a PR-head-checked-out scanner) → §3.3: the CI
  path-gate + scanner run from the **trusted base ref** (sparse-checkout from
  `pull_request.base.ref`), exactly as `codex_verdict_check.yml` Phase C
  already does for `verdict_validator.py` / `scan_for_secrets.py` — OR the
  path-gate is inline immutable workflow YAML. PR-head code never gates itself.
- iter-2 P2 (local extraction can also use `.env` values) → §3.2.
- iter-3 P1-1 (a `pull_request` workflow reads its run-block from PR head, so
  the PR can edit the gate workflow to skip the scan — base-ref checkout of
  the *script* doesn't protect the *control plane*) → §3.3: the gate is a
  `pull_request_target`-triggered workflow (definition + steps sourced from
  the base ref), PR content checked out read-only as data, no PR-head code
  executed, no secrets handed to PR code.
- iter-3 P1-2 (filename allowlist doesn't prove content is slim — a raw
  transcript can be committed under an allowed name) → §3.3: CI also runs
  trusted content-validation that each allowed verdict/audit artifact is a
  schema-bounded slim block (no trailing transcript body, size-capped).
- iter-3 P2 (more raw-transcript filename variants) → §3.4.
- iter-4 P1 (CI gate must be an actually-*required* merge check; a
  `paths:`-filtered required check deadlocks non-`.codex` PRs because skipped
  required checks stay pending) → §3.3: the gate workflow runs on EVERY PR
  (no `paths:` filter; internal fast-pass no-op when the diff has no
  `.codex/**`) and its check name is registered in `polaris` branch-protection
  required checks + the protection-drift material.
- iter-4 P2 (bootstrap — the gate workflow cannot gate its own introducing
  PR) → §3.6.

## 1. The issue (GH #535 / I-sec-001)

`codex exec` review runs have repo read access and routinely `cat`/grep files
including `.env`. The full transcript is committed under `.codex/<issue_id>/`
per the §3.0 5-artifact convention. Credentials leak into git that way.
Acceptance: (a) pre-commit scrub OR (b) verdict-only; (c) decision to Codex;
(d) audit existing `.codex/**`.

## 2. Grounded findings

### 2.1 Criterion (d) — audit DONE
Tight audit (`*API_KEY|*SECRET|*KEY|*TOKEN|*PASSWORD` env vars vs
`git ls-files .codex/`, exact `.env`-value match, count-only): **16 live
credential hits** — 7 vendor API keys + `POLARIS_AUTH_SECRET` in
`.codex/I-carney-004` & `I-carney-005/codex_diff_audit_iter_2.txt`, plus
`POLARIS_AUTH_SECRET` in 6 `codex_brief_verdict*` files. The verdict files
themselves leaked — the slim verdict block is NOT secret-free by
construction. Operator reviewed and accepted the exposure (no rotation / no
history scrub) — `state/resolved_halt_20260517T124325Z_secret_exposure.md`.
This issue is forward-prevention only.

### 2.2 Existing infra
- `scripts/autoloop/scan_for_secrets.py` — pattern SCANNER; `SECRET_PATTERNS`
  misses the vendor keys that leaked (`jina_`, Firecrawl `fc-`, Fireworks
  `fw_`, Exa, Semantic-Scholar, Vast).
- It is wired into `codex_verdict_check.yml` only (Plan-v13 verdict-rerun),
  NOT the per-issue `.codex/<id>/` commit path. Critically, that workflow's
  Phase C **checks the validator + scanner out from the trusted base ref**
  (`sparse-checkout` from `pull_request.base.ref`) — the pattern #535's CI
  gate must reuse (iter-2 P1-2).
- `.git/hooks/{pre-commit,commit-msg}` stubbed (`exit 0`, per-clone) — not a
  gate; ship procedure uses `--no-verify`.
- `.codex/**` is tracked (only `.codex/round_*/std{out,err}.log` gitignored).
- `codex-required.yml` consumes only the LAST `verdict:` line of
  `codex_brief_verdict.txt` / `codex_diff_audit.txt`. No gate needs the full
  transcript body.

### 2.3 The leak path
Per-issue ship runs `codex exec ... > .codex/<id>/codex_*_iterN.txt`, then
`git add .codex/<id>/` commits the full multi-MB transcript including any
`cat .env` output. No scrub step exists.

## 3. Proposed fix — verdict-only base + mandatory scan + tamper-proof CI gate

Claude recommends **(b) verdict-only, hybridised with a mandatory scanner**
(iter-1's `remaining_blockers` direction). Codex: confirm or redirect.

### 3.1 Slim verdict is the only committed Codex artifact
`scripts/extract_codex_verdict.py` — given a raw `codex exec` transcript,
**parse and schema-validate** the final verdict block against the §8.3.9
field set (`verdict / novel_p0 / continuing_p0 / p1 / p2 / convergence_call /
remaining_blockers_for_execution`; reject malformed/truncated) and write the
slim `codex_brief_verdict.txt` / `codex_diff_audit.txt`. Parse+validate, not
regex-copy-through (iter-1 P2-2) — no trailing transcript text survives.

### 3.2 Mandatory scan of the slim verdict before commit AND in CI
The slim verdict can still quote a secret in finding prose (iter-1 P1-1):
- `extract_codex_verdict.py` runs `scan_for_secrets.py` on its own output and
  **additionally** exact-matches the output against local `.env` credential
  values when `.env` is present (iter-2 P2 — vendor-agnostic, catches secrets
  no regex/NAME-form would). Non-zero exit on any hit → ship procedure cannot
  commit; author redacts to `[REDACTED-SECRET]`.
- CI re-scans (pattern + NAME-form only — no `.env` dependency) as
  defence-in-depth.

### 3.3 CI backstop — base-sourced tamper-proof control plane
A dedicated workflow on PRs touching `.codex/**`. Tamper-resistance + scope
(iter-2 P1-1/P1-2, iter-3 P1-1/P1-2):
- **Base-sourced control plane, required without deadlock (iter-3 P1-1,
  iter-4 P1).** The gate is its own workflow triggered by
  **`pull_request_target`** — GitHub runs the workflow definition/run-block
  from the base `polaris` ref, not the PR head, so the PR cannot edit the
  gate's steps to skip it. PR content is `actions/checkout`'d **read-only as
  data** (`persist-credentials: false`, into a subdir), never executed; no
  repo secrets reach any step that touches PR content. The gate script +
  `scan_for_secrets.py` are the base-ref copies (present since the workflow
  runs from base). The workflow has **NO `paths:` filter — it runs on EVERY
  PR** and internally fast-exits PASS when
  `git diff --name-only origin/<base>...HEAD -- .codex/` is empty; this avoids
  the skipped-required-check deadlock (a `paths:`-filtered required check
  stays pending forever on non-`.codex` PRs). Its job/check name is **added to
  `polaris` branch-protection required status checks** and recorded in the
  protection-drift verification material (`verify_cage` / required-checks
  list) so the gate actually blocks merge and future drift is detectable.
- **Path gate over ALL changed `.codex/**` (status A/M/R/C — every status
  except D).** `git diff --name-status origin/<base>...HEAD -- .codex/`; each
  non-deletion path:
  - **Denylist:** fail on a raw-transcript pattern —
    `codex_*review*.txt`, `codex_*audit_iter*.txt`, `codex_brief_review*.txt`,
    `codex_diff_review*.txt`, `codex_*_iter[0-9]*.txt` (except the explicit
    `*_iter5_force_approve.txt`).
  - **Allowlist:** under `.codex/<id>/` only `brief.md`, `diff_brief.md`,
    `codex_brief_verdict.txt`, `codex_diff_audit.txt`, `codex_diff.patch`,
    `*_iter5_force_approve.txt`.
  - Fully-unchanged historical tracked files (not in the diff) grandfathered.
- **Content validation (iter-3 P1-2).** A filename on the allowlist does not
  prove slim content — a raw transcript could be committed as
  `codex_brief_verdict.txt`. So CI also runs the base-ref
  `extract_codex_verdict.py --validate` on each changed
  `codex_brief_verdict.txt` / `codex_diff_audit.txt` / `*_iter5_force_approve.txt`:
  it must parse as exactly a schema-bounded §8.3.9 verdict block, with no
  trailing transcript body, under a sane byte cap (e.g. 8 KB). Fail otherwise.
- **Secret scan:** extended `scan_for_secrets.py` (`--strict`) on the changed
  `.codex/**` files; pattern-based + `NAME=value`/`NAME: value` detection for
  a configured list of secret env-var NAMES (names only, no values).

### 3.4 Already-tracked raw transcripts + .gitignore
`.gitignore` does not untrack already-committed files (iter-1 P2-1). gitignore
the raw-transcript patterns going forward — covering the observed variants
(iter-3 P2): `codex_*review*.txt`, `codex_*_review_iter*.txt`,
`codex_diff_review*.txt`, `codex_brief_review*.txt`, `codex_brief_verdict_iter*.txt`,
`codex_diff_audit_iter*.txt` and no-underscore `iterN` forms — so local
staging fails early. The §3.3 CI gate is the real enforcement (covers M/R/C,
so a touched legacy transcript is caught). Existing fully-unchanged tracked
transcripts left as-is per operator decision — not tree-removed here.

### 3.5 Pattern coverage
Extend `scan_for_secrets.py` `SECRET_PATTERNS` with the missing vendor shapes
(`jina_`, Firecrawl `fc-`, Fireworks `fw_`, Exa, Semantic-Scholar, Vast) +
the configured-secret-NAME assignment check.

### 3.6 Bootstrap note (iter-4 P2)
The I-sec-001 PR introduces the `pull_request_target` gate workflow; that
workflow is not on the base ref until this PR merges, so it cannot gate its
own PR. The I-sec-001 PR is therefore committed manually under the new
discipline: only slim, schema-validated, secret-scanned (+ local `.env`-value
matched) verdict artifacts; raw transcripts gitignored and never committed;
any scan hit redacted to `[REDACTED-SECRET]` before commit.

## 4. Acceptance criteria for THIS brief
1. Problem analysis (§2) correct.
2. (a)/(b) decision (§3) — confirm verdict-only-hybrid, or redirect.
3. §3.1–3.5 mechanism sound + complete + tamper-resistant; CI has no
   `.env`-value dependency and does not execute PR-head gate code.
4. Scope call on already-committed transcripts (§3.4) sound.

## 5. Files I have ALSO checked and they're clean / accounted for
- `.github/workflows/codex-required.yml` — verdict-line parser only.
- `.github/workflows/codex_verdict_check.yml` — Phase-C base-ref sparse
  checkout is the trusted-gate pattern §3.3 reuses.
- `scripts/codex_loop_parse.py` — frontmatter→verdict parser; slim verdict
  stays parseable.
- `.git/hooks/{pre-commit,commit-msg}` — stubbed; not a gate.
- `.gitignore` — `.codex/` tracked except `round_*` logs.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
