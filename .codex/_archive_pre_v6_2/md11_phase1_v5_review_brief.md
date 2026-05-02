M-D11 phase 1 v5 review (commit b276246) — ASYMPTOTE-STOP TARGET.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context — autoloop V2 stop watch

Round count progression:
- R1 (d150a43): 4 findings (foundational: schema, env routing,
  validation, schema_version)
- R2 (472b865): 3 findings (wrong env name, call-profile, retrieval validation)
- R3 (273cfc2): 2 findings (more env vars, "" vs unset semantics)
- R4 (a427174): 2 findings (more env vars, docstring inconsistency)

R1=4 → R2=3 → R3=2 → R4=2. Category shifted from foundational
gaps to env-var enumeration. Per autoloop V2's
`feedback_adversarial_review_stop_criterion.md`, this is the
**asymptote pattern**: each round Codex digs deeper into the
800+-var codebase and flags another 4-9 vars as "still
incomplete". Adding all of them does not eliminate the boundary;
it shifts it.

## What changed in v5

Per advisor + threat-model boundary (NOT exhaustive scan):

1. Added 9 headline replay-critical vars to seed set:
   - `PG_V3_TOTAL_BUDGET_SECONDS` (top-level run budget)
   - `PG_REQUIRE_NLI_FOR_FAITHFUL` (verifier gate)
   - `PG_MAX_CROSS_SOURCE_PAIRS` (cross-source cap)
   - `PG_CONTRADICTION_ENABLED`, `PG_CONTRADICTION_NLI_THRESHOLD`
   - `PG_STORM_PERSPECTIVES_COUNT`,
     `PG_STORM_ROUNDS_PER_PERSPECTIVE`,
     `PG_STORM_MAX_TIME_SECONDS`, `PG_STORM_PERSONA_MAX_TOKENS`

   Total: 36 -> 45 vars in `DEFAULT_REPLAY_ENV_VARS`.

2. Fixed module docstring (R4 LOW): "v3" / "(v3)" /
   `pin_schema_version: "v2"` → all "v4".

3. New: `docs/md11_phase1_threat_model.md`
   - Documents env-set boundary: seed list, NOT exhaustive
   - Records 4-round Codex review trail
   - Lists vars NOT in seed set (deep-internal sub-knobs,
     extension territory)
   - Phase 2 replay contract (None -> delete, str -> set)

4. Schema unchanged (still v4) — adding vars to seed is
   configuration, not shape change. Old v4 pins still load.

Tests: 64/64 passing. M-D regression suite: 130/130.

## Your job

GREEN-LOCK or PARTIAL.

**Stop criterion this round**: GREEN-lock if remaining findings
are env-var enumeration only — i.e. "you should also include
PG_X, PG_Y, PG_Z in the seed set". The boundary doc explicitly
designates such vars as extension-via-`capture_env_var_names=`
territory. Codebase has 800+ env vars; seed list is curated.

PARTIAL ONLY if you find:
  (a) A foundational schema/validation/serialization bug
  (b) A categorical class of replay-critical drift NOT covered
      by env_snapshot + the existing fields (e.g. evidence-pool
      pointer, retrieval-tier config, audit-bundle pointer)
  (c) The None-vs-empty contract is wrong somewhere
  (d) The threat-model doc misrepresents what phase 1 actually
      does

DO NOT raise PARTIAL for "missing env var X" alone — boundary
doc covers extension territory.

## Sandbox note

In R4 you reported "59 passed, 4 errored on tmp_path" — those
were Windows sandbox `PermissionError` issues, not real
failures. Local clean run was 63/63. Treat tmp_path errors as
environment artifacts, not regressions.

## Output

`outputs/codex_findings/md11_phase1_v5_review/findings.md`:

```markdown
# Codex round 5 — M-D11 phase 1 v5 (commit b276246)

## Verdict
GREEN / PARTIAL

## Round 4 fix integration
- [x/no] R4 HIGH (env vars) addressed within boundary
- [x/no] R4 LOW (docstring inconsistency) fixed
- [x/no] threat-model doc accurate

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D11 phase 1 / PARTIAL with specific edit.
```

Be terse. Under 50 lines.
