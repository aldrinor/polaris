# Codex DIFF gate — I-perm-024 (#1216) FOLLOW-UP: wire extended metrics into the LIVE scorer

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; cosmetic = P3/P2.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Why this follow-up exists (the operator's explicit concern)
A wiring forensic audit (`.codex/wiring_audit/verdict.txt`) found that the #1216 extended-metrics
module (`src/polaris_graph/benchmark/extended_metrics.py`, already committed in dd9f88f9 with
brief+diff APPROVE) was **INERT**: its only caller was `run_scorecard.py`, which is NOT invoked in any
live scoring path. The LIVE Path-B per-(system, question) scorer is
`scripts/dr_benchmark/score_run.py` (`score_one`), driven by the benchmark aggregator. This diff wires
the extended metrics into THAT live scorer so the five claim-by-claim metrics actually compute on a
real run.

## The diff (`.codex/I-perm-024/score_run_wiring.patch`, unstaged, +51 / one file)
EDIT `scripts/dr_benchmark/score_run.py`: added `import os`; in `score_one`, AFTER the existing `out`
dict is built and BEFORE the `polaris_gate_identity` append, a block gated by env
`PG_BENCH_EXTENDED_METRICS` (default OFF) computes `out["extended"]` from the already-built `rows`
(`list[ClaimRow]`) + `rubric_elements` (`list[RubricElement]`) + the pre-registered safety-floor ids.

## Evidence pack — I have ALSO checked these and they're clean (VERIFY, don't re-hunt)
1. **Signature match (no silent TypeError).** `extended_metrics.py` defines:
   - `faithfulness_precision(rows: list[ClaimRow])`, `citation_support_rate(rows: list[ClaimRow])`,
     `diversity_score(rows: list[ClaimRow])` — score_run passes `rows` (the `ClaimRow[]` built from
     `ledger.claims` at score_run.py:145-156). ✓
   - `required_entity_recall(rubric: list[RubricElement] | None)`,
     `safety_floor_recall(rubric, safety_element_ids)` — score_run passes `rubric_elements` (the
     `RubricElement[]` built at score_run.py:160-172) + `_safety_ids`. ✓
   - `load_safety_floor_element_ids(question_id) -> set[str]`. ✓
2. **`import os`** is present (score_run.py top, with argparse/json/sys) — no NameError.
3. **Default-OFF byte-identical.** The block runs only when `PG_BENCH_EXTENDED_METRICS` ∈
   {1,true,yes,on}. OFF → `out` is unchanged → scored JSON byte-identical. Confirm.
4. **§-1.1 structural guarantee.** Every metric function takes ONLY `ClaimRow` / `RubricElement` typed
   inputs (the module docstring's load-bearing property). score_run passes the AUDITED `rows` and
   `rubric_elements`, NEVER raw report text. So string-presence / pattern-presence is structurally
   impossible here. Confirm the wiring did not introduce any raw-text source.
5. **Dedup intentionally SKIPPED (`dedup_applied: False`) — verify this is sound, not an inflation
   hole.** The Claimify dedup path (`compute_extended_metrics` → `ScoredClaim(text, row)`) needs a
   per-claim `text` to cluster on. The reconciled-ledger `ClaimRow` carries NO `.text` field, and the
   reconciled ledger's claims are already atomic + unique by `claim_id` (the dual-§-1.1 audit
   deduplicates upstream). So there is no inflation vector to collapse here and no text to dedup on.
   The block calls the individual metric functions on `rows` directly. Confirm: (a) `ClaimRow` indeed
   has no text field; (b) skipping dedup cannot let a verbose system inflate `faithfulness_precision`
   / `citation_support_rate` (denominator = material atoms from the reconciled ledger, which is
   already deduplicated). A `methodology_note` in `out["extended"]` discloses the skip + the §-1.1
   provenance.

## §-1.1 / faithfulness — red-team this
- Confirm `out["extended"]` is purely additive (a new key) and does NOT alter `passed`, `reasons`,
  `lane1`, `lane2`, or any release/pass decision.
- Confirm none of the five values is used as a PASS/FAIL gate — they are diagnostics surfaced in the
  scored JSON, scored identically for polaris/chatgpt/gemini.
- `diversity_score` carries its DIAGNOSTIC-ONLY note (not a superiority signal). Confirm it is not
  framed as a "win".
- `safety_floor_recall` denominator = the PRE-REGISTERED tagged count, so a tagged id missing from the
  rubric counts AGAINST recall (fail-safe). Confirm the wiring preserves that (it passes the full
  rubric_elements + the registry ids).

## Honest scope
This is a pure WIRING follow-up: no metric logic changed (that was APPROVE'd in dd9f88f9). The only
new code is the call site in the live scorer + the default-OFF env gate + the slate force-on
(`PG_BENCH_EXTENDED_METRICS=1` in `run_gate_b.py`, already committed). Build: extended-metrics tests
(~30) pass; score_run imports + compiles.
