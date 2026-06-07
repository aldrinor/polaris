# I-ready-017 FX-08b (#1113) — DIFF gate (iter 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this implements (#1113 PART B — the determinism half of BUG-04)
Diff: `.codex/I-ready-017/fx08b_codex_diff.patch` (base 121b931a^..HEAD; 3 files, +82/-1 src).
Non-rerun-gating P2 follow-up of FX-08 (#1112, PART A tolerant-parse already landed).

## The bug (PROVEN §-1.1 on the held drb_72 artifact)
Byte-identical claims were SPLIT VERIFIED/UNSUPPORTED in the same run — a non-deterministic release
gate. Grouping the held 4-role claims by exact sentence (which embeds `[#ev:id:start-end]`) yields
18 byte-identical-input groups; the claim_id content-hash suffix is identical within each group
(independent proof of identical INPUT). 4 groups SPLIT in `manifest.json
/four_role_evaluation/final_verdicts`:
- 04ac0772: 00-028 UNSUPPORTED vs 00-048/00-096 VERIFIED
- 4f76d6f1: 00-050/00-074 VERIFIED vs 00-085 UNSUPPORTED
- 821c642a: 00-062 VERIFIED vs 00-101 UNSUPPORTED
- 9f410a6c: 00-066 VERIFIED vs 00-078 UNSUPPORTED
Full audit: `outputs/audits/I-ready-017/fx08b_s11_audit.md`.

## The fix
1. `sweep_integration._compute_claim_results`: CLAIM-LEVEL DEDUP at the batch entry (pinned here,
   NOT role_pipeline.py — FX-11 collision avoidance per the issue; FX-11 already merged).
   - Key = the FULL pipeline input: `(normalized claim_text, sorted (doc_id, doc.text), severity,
     sorted s0_categories)`. The evidence doc `text` is the FX-03 cited WINDOW, so it encodes the
     span. Anything that could legitimately change the verdict is in the key -> two
     genuinely-different claims can NEVER collapse (faithfulness-safe; identical-input-only).
   - Run the pipeline ONCE per distinct key (recurse on representatives — one level; reps have
     all-distinct keys so the inner call skips the dedup branch). Fan the verdict out to each
     duplicate under ITS OWN claim_id (`dataclasses.replace(rep.d8_row, claim_id=...)`), SHARED
     verdict + sub-results, EMPTY `records`, cost None.
   - Audit-trail honesty: a duplicate made no model calls, so empty records keep `all_records` /
     `four_role_role_calls.jsonl` / spend reflecting only real calls (no inflation). Coverage credit
     still flows per-claim (each dup credits its own covered_element_ids on the shared VERIFIED).
   - Flag-gated `PG_FOUR_ROLE_CLAIM_DEDUP` (default ON); OFF byte-identical to the per-claim run.
2. `openrouter_role_transport._build_openrouter_body`: temperature=0 (PG_VERIFIER_TEMPERATURE,
   universally supported -> safe even with provider.require_parameters=True) + seed OPT-IN
   (PG_VERIFIER_SEED, DEFAULT OFF). seed is opt-in on purpose: a `seed` in the body under
   require_parameters=True can make OpenRouter REFUSE to route to the pinned healthy provider
   (seed is not universally advertised) -> a fail-loud no-endpoint crash on every verifier call.
   The dedup is the real determinism guarantee; temp/seed are necessary-not-sufficient.

## Offline evidence
`pytest tests/roles/test_seam_parallel.py` -> 14 passed (9 existing seam/cost/coverage + 5 new:
dedup-runs-pipeline-once-and-fans-verdict [4 calls not 8; log = one claim's rows],
dedup-disabled-runs-each [8 calls, byte-identical-to-pre-fix], distinct-claims-not-deduped [idx-0
VERIFIED vs idx-1 UNSUPPORTED stay distinct], dedup-fan-out-credits-coverage-per-claim
[coverage_fraction==1.0], build_openrouter_body temperature=0 + seed opt-in). py_compile clean.

## Faithfulness
Dedup is at the DECISION layer (identical input => identical output). No grounding / strict_verify /
provenance token / 4-role-binding / two-family change. temperature=0 is standard for deterministic
verification; seed stays operator-gated for routing safety.

## Questions
1. Is the dedup KEY complete (can two genuinely-different claims collapse to one verdict)? Is the
   per-claim-id fan-out (own claim_id, shared verdict, EMPTY records, zero cost) honest on the
   served-identity audit trail + cost + coverage?
2. Is the temperature=0-always / seed-opt-in split correct for provider.require_parameters routing
   safety, or should seed be handled differently?
3. Any faithfulness / determinism / correctness gap before APPROVE?
