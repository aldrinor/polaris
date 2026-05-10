# Codex Diff Review — I-bug-108 (verifier-driven repair loop + synthesis [N] scrub) — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools.
```

## Iter 2 changes addressing iter-1 P0 + P1

Iter 1 returned REQUEST_CHANGES with:
- **P0**: `_scrub_invalid_n_markers` regex `\[(\d+)\]` doesn't catch `[-N]`, `[ N ]`, `[01]`. The downstream PT12 parser may treat any of these as invalid and abort regardless.
- **P1**: `repair_sentence` returned `(None, 0, 0)` for both API failures and empty-token NULL_DROP responses; orchestrator inferred classification from token counts → unreliable telemetry.

**Iter 2 fixes:**

| iter-1 issue | iter-2 fix |
|---|---|
| P0 — scrub regex doesn't catch malformed | Added `_MALFORMED_MARKER_RE = re.compile(r"\[\s*(-?\d+)\s*\]")`; matched + raw-form check rejects `[-1]`, `[ 5 ]`, `[01]`, etc. Test asserts `[-1]` and `[ 5 ]` and `[01]` are scrubbed. |
| P1 — telemetry conflated API failure / NULL_DROP | `repair_sentence` now returns `(outcome, text, in_tok, out_tok)` where outcome ∈ {"text", "null_drop", "api_failure", "skipped"}. Orchestrator switches on outcome instead of inferring from token counts. New test pins distinguish-by-signal (50/10 token NULL_DROP and 200/50 token API_FAILURE both classified correctly). |

3 new tests + updated test fakes to use the new 4-tuple shape. **51/51 tests pass.**

## Pre-flight

- Brief APPROVE'd iter 1 (recovery_rate_floor=0.30, max_retries=1, max_per_section=10, full strict_verify rerun).
- Diff iter 1: APPROVE w/ REQUEST_CHANGES (1 P0, 1 P1, 1 P2)
- Diff iter 2: `.codex/I-bug-108/codex_diff.patch` (canonical-diff-sha256: `e92f927a6381b347ee9b66fb677d17afd4dbb6caad5a4d4feff118e23da0283d`)
- 5 files / 970 lines: 2 src modules + 1 generator integration + 2 test files (28 new tests; all 48 passing across the suite).
- Production validation: status=success, release_allowed=TRUE, recovery_rate=35.3%, 0 token-set violations.

## What this PR ships

1. **`sentence_repair.py`** — verifier-driven repair loop module (Codex iter-1 path B). When strict_verify drops a sentence due to drift failures (entailment/numbers/trial-name/content overlap), feed (sentence, cited spans, judge reason) back to the generator for one rewrite. Repaired sentences must pass full `verify_sentence_provenance` re-run including entailment.

2. **`multi_section_generator.py` integration** — calls `repair_dropped_section_sentences` between strict_verify and M-41c filter. Augmented kept[] flows through downstream filters as if the repaired sentences had passed first time.

3. **PT12 root-cause fix in `analyst_synthesis.py`** — added `_scrub_invalid_n_markers` runtime guardrail because the production v2 sweep aborted at PT12 (`max_marker=19, biblio_size=17`). Diagnosed: synthesis LLM hallucinates [N] markers beyond bibliography size. The scrub fires after the existing `_scrub_ev_tokens` call. Empirically caught 6 invalid markers in v3 sweep.

## All 3 Codex iter-1 brief P0s addressed

| Codex iter-1 directive | Implementation |
|---|---|
| Token-set preservation: repaired output must carry exactly the original [#ev:...] markers | `_extract_token_signature` + post-repair check in orchestrator. Verified: 0 violations across 47 first-run + 17 v3 attempts. |
| Drop accounting honest: recovered MOVE from dropped to kept | `final_dropped` list excludes recovered SVs; `new_kept` appends. No double-counting. |
| Deterministic order | Walk dropped[] in original input order; MAX_PER_SECTION cap on attempt count. |

Plus PT12 safety filter (added after first-run abort): repaired sentence's evidence_ids must be a subset of the pre-repair kept set's evidence_ids — prevents introducing new ev_ids that the section bibliography won't include.

## Production-validated empirical result (v3 sweep)

```
status: success
release_allowed: TRUE   (PT12 abort fixed)
total_words: 1457   (+50% vs 974 baseline)
verified_words: 368
analyst_synth_words: 1089

Repair loop per-section:
  Efficacy:           0/1 = 0%
  Mechanism:          3/6 = 50%
  Comparative:        2/6 = 33%
  Long-term Outcomes: 1/4 = 25%
  Aggregate:          6/17 = 35.3%   ← above Codex's 0.30 floor
  Token-set violations: 0

Synthesis [N] scrub fired:
  "scrubbed 6 invalid [N] markers (N > biblio_size=8)"
```

The first-run aggregate hit 40.4% (47 attempts, 19 successes); v3 hit 35.3% (17 attempts, 6 successes). Both above the floor. Recovery rate variance is from per-run variation in which dropped reasons are repairable.

## Tests pinned (28 new)

- 8 `is_repairable` classifier tests
- 4 token-signature extraction tests
- 8 repair-loop orchestrator tests (off-mode skip, unrepairable-skip, recovery, NULL_DROP, token-violation, MAX_PER_SECTION cap, deterministic order, telemetry)
- 2 PT12 safety filter tests (skip when ev_id not in kept; allow when in kept)
- 6 invalid-[N]-marker scrub tests (drop out-of-range, preserve in-range, drop zero/negative, log on dirty, no-log on clean, real-world hallucination case)

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Any P0/P1 you find** — please be exhaustive iter 1.
3. The PT12 root cause is in I-bug-105 (synthesis `[N]` hallucination); I included the scrub fix in this PR rather than carving it into I-bug-109. Codex has reviewed: bundle or split?
4. Recovery rate variance (40.4% v1, 35.3% v3) — accept as stochastic? Or do you want me to run a third validation sweep before merge?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
