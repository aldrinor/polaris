# §-1.1 audit — FX-08b (#1113): 4-role claim-level dedup (determinism)

**Standard:** §-1.1 on the REAL held drb_72 4-role artifacts
(`outputs/audits/I-ready-017/run_artifacts/`: `four_role_claim_audit.json` = per-claim INPUT,
`manifest.json /four_role_evaluation/final_verdicts` = per-claim VERDICT). The fix is
flag-gated/additive (default ON; OFF reverts to the per-claim run), so the override behaviour is
locked by 5 focused unit tests; this §-1.1 confirms the fix targets the EXACT real regression.

## The bug, on the real artifact (claim-by-claim)

CLAIM: byte-identical claims get SPLIT VERIFIED/UNSUPPORTED in the same run — a non-deterministic
release gate (BUG-04).

EVIDENCE: grouping the 156 held 4-role claims by their exact `sentence` (which embeds the cited
`[#ev:id:start-end]` ids+spans) yields **18 byte-identical-input groups (41 claims)**. The
claim_id carries a content-hash suffix; within every group the suffix is IDENTICAL — independent
proof the pipeline INPUT is byte-identical. **4 of those groups SPLIT** across verdicts in the
held run:

| group (content-hash suffix) | claim_ids → held verdicts | sentence |
|---|---|---|
| `04ac0772` | 00-028→**UNSUPPORTED**, 00-048→VERIFIED, 00-096→VERIFIED | "These complementarities increase productivity [#ev:autor_why_still_jobs:0-800]." |
| `4f76d6f1` | 00-050→VERIFIED, 00-074→VERIFIED, 00-085→**UNSUPPORTED** | "They augment demand for labor [#ev:autor_why_still_jobs:0-800]." |
| `821c642a` | 00-062→VERIFIED, 00-101→**UNSUPPORTED** | "They augment the demand for labor [#ev:autor_why_still_jobs:0-800]." |
| `9f410a6c` | 00-066→VERIFIED, 00-078→**UNSUPPORTED** | "In the last few decades, one noticeable change has been a polarization of the labor market…" |

VERDICT: **CONFIRMED regression.** 10 claims across 4 groups have byte-identical pipeline input
(same sentence + same evidence ids + same spans, proven by identical content-hash suffix) yet were
assigned BOTH VERIFIED and UNSUPPORTED in the same run. A claim's release verdict therefore
depended on batch nondeterminism, not on its content — exactly the §-1.1-lethal class for a release
gate (the same claim is simultaneously "release-eligible" and "held").

This matches the issue's named signature (00-050/00-074/00-085/00-101 and 00-028/00-048/00-096).

## The fix corrects exactly this (verified)

The dedup key is the FULL pipeline input — `(normalized claim_text, sorted (doc_id, doc.text),
severity, sorted s0_categories)` — which is precisely what the content-hash suffix encodes. So the
4 split groups key together identically; the pipeline runs ONCE per group and the single verdict is
fanned out to every member under its own claim_id. Post-fix, all 3 of `04ac0772` share one verdict,
all 3 of `4f76d6f1` share one, etc. — the split is structurally impossible.

Two genuinely-different claims can NEVER collapse: the key includes everything the pipeline
consumes, so a different sentence / evidence text / span / severity / s0 → different key → separate
run (unit test `test_distinct_claims_are_not_deduped`: idx-0 VERIFIED and idx-1 UNSUPPORTED stay
distinct).

## Fan-out is honest (audit trail + cost)
- A duplicate gets its OWN `claim_id` (`dataclasses.replace` on `d8_row`), the SHARED verdict +
  sub-results, EMPTY `records` (it made no model calls), and zero cost — so `all_records` /
  `four_role_role_calls.jsonl` / spend reflect only the calls that actually happened
  (`test_claim_dedup_runs_pipeline_once_and_fans_verdict`: 4 calls not 8; log has one claim's rows).
- Coverage credit still flows per-claim: each duplicate credits its own `covered_element_ids` on the
  shared VERIFIED verdict (`test_dedup_fan_out_credits_coverage_per_claim`: coverage_fraction == 1.0).

## Offline evidence
`pytest tests/roles/test_seam_parallel.py` → 14 passed (9 existing seam/cost/coverage + 5 new:
dedup-runs-once, dedup-disabled-runs-each, distinct-not-deduped, coverage-fan-out, temperature/seed
knobs). py_compile clean on both touched source files.

## Faithfulness
Dedup is at the DECISION layer (identical input → identical output); no grounding / strict_verify /
provenance / 4-role-binding change. temperature=0 always (safe under provider.require_parameters);
seed is OPT-IN (default off) so it cannot break pinned-provider routing. Flag-gated
(`PG_FOUR_ROLE_CLAIM_DEDUP` default ON); OFF is byte-identical to the prior per-claim run.
