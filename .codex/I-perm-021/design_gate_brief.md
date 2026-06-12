# Codex DESIGN gate — I-perm-021 (#1213): RequiredEntityLedger (completeness fix)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
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
answers_to_design_questions: {q1: "...", q2: "...", ... q7: "..."}
```

## What you are gating
This is a DESIGN gate (no code yet). Rule on the design + ANSWER the 7 design questions so the
build is correct first time. The full grounded forensic is at `.codex/I-perm-021/forensic.md`
(read it — it cites file:line). The issue is #1213: build a RequiredEntityLedger so the report
INCLUDES all verified required entities and DISCLOSES unsupported ones as explicit evidence_gaps
(never hallucinated); gap-driven targeted retrieval for missing slots; default-OFF flag,
byte-identical when off; faithfulness gates (strict_verify/4-role/D8) NEVER relaxed.

## The forensic's load-bearing findings (verify these)
1. **The completeness gap is LARGELY UPSTREAM (retrieval/extraction), not reduce-time.** A
   reduce-time ledger cannot MANUFACTURE coverage — it can only force INCLUSION of already-verified
   findings + DISCLOSE the rest + FEED bounded retrieval. If this is wrong, say so.
2. POLARIS ALREADY measures required-entity coverage post-strict_verify, report-level
   (`native_gate_b_inputs.build_native_gate_b_inputs` :649-783, `_claim_covers_entity` :514-535,
   `_entity_canonical_match` exact-equality :293-309). `missing = required − ⋃covered` is already
   computable there. ALREADY has a bounded gap-retrieval lane (`run_required_entity_lane` #1190,
   required_entity_retrieval.py:295-428, wired run_honest_sweep_r3.py:4808, default OFF) — but
   S0-safety-only, fires once pre-gen, never closes the loop.
3. **The owner's proposed hook (`_run_section`, between distillate and reduce) is at the WRONG
   ALTITUDE:** the S1 pivotal-trial entities (the bulk of the clinical denominator) render via the
   V30 CONTRACT path (`contract_section_runner.py`), not `_run_section`; and `_run_section` is dark
   unless `PG_SECTION_DISTILL` is also on. `generate_multi_section_report` (:4711) receives NO
   template/slug/required_entities. So a `_run_section`-local ledger is structurally blind to S1.
4. **Sequencing contradiction:** "ledger BEFORE reduce" + "missing = required − VERIFIED bindings" +
   "strict_verify is the SOLE VERIFIED authority" cannot all hold (strict_verify runs on the reduce
   OUTPUT). Forensic resolves with a TWO-PHASE ledger: Phase A (pre-gen, corpus-presence → MAPPED,
   drives extended pre-gen retrieval), Phase B (post-strict_verify, VERIFIED/INCLUDED/GAP_DISCLOSED).
5. The V30 contract path ALREADY discloses unfillable trial slots faithfully
   (`contract_section_runner.py:993-1019` + `compose_gap_payload` :370-372) — the evidence_gaps
   precedent. Gap disclosures are DETERMINISTIC TEMPLATED strings (no LLM), never fabricated prose.

## §-1.1 faithfulness design (the crux — verify every path)
INCLUDED reachable ONLY from VERIFIED; VERIFIED set ONLY by reading strict_verify is_verified=True
(ledger never sets is_verified). Gap retrieval never keys a fetched row to an entity_id (the #1190
invariant :319) and coverage still requires EXACT canonical match (alt URL can't flip a url_pattern
entity — recovery gets CONTENT in, never forces coverage). evidence_gaps are templated, no fabricated
citation. Re-generation (if any) re-runs the UNCHANGED strict_verify. The ledger MUST NOT add a new
D8 coverage-CREDIT path (its VERIFIED set must EQUAL `_claim_covers_entity`); new credit = §-1.1-lethal.
Native scope template is the ONLY source of "required" (the contamination lock — NEVER read
outputs/dr_benchmark/). Flag `PG_REQUIRED_ENTITY_LEDGER` read at call time (never import — I-cap-005).

## THE 7 DESIGN QUESTIONS — please RULE on each
1. **ALTITUDE (pivotal):** report-level (post-`generate_multi_section_report`, pre/at
   build_native_gate_b_inputs) vs per-section (`_run_section`)? Forensic strongly recommends
   report-level (S1 trials, missing already lives there). Confirm or correct.
2. **Two-phase** (pre-gen MAPPED-driven retrieval + post-verify VERIFIED ledger) vs a single
   pre-reduce ledger (internally contradictory)? Confirm two-phase.
3. **Extended (non-S0) pre-gen retrieval budget:** reuse #1190 caps as-is, or a separate reserved
   budget under the no-overshoot 1000-fetch envelope (#1168)? Which?
4. **SCOPE (risk-critical):** ship #1213 as INCLUSION + DISCLOSURE ONLY (no 2nd LLM generation —
   lower risk, smaller diff, still "disclose not hallucinate"), deferring the post-verify
   gap-RECOVERY round (re-generate + re-verify recovered slots) to a gated follow-up? Forensic
   recommends the split. Rule.
5. **evidence_gaps placement:** explicit body "Coverage gaps" section vs per-section vs
   manifest-only? (Blind operator + §-1.1 argue for an explicit body section.)
6. **"Required" sourcing:** confirm the ledger inherits the native-scope-template-only contamination
   lock (never the gold rubric).
7. **url_pattern-only entities** (structurally un-flippable by alt-URL retrieval): need a distinct
   "content present but cited URL not canonical" gap note?

## Honest framing for your ruling
Given finding #1 (gap is upstream), is #1213 worth building now, or is the higher-leverage move the
retrieval-breadth campaign (#1204)? If you think #1213 should ship narrow (inclusion+disclosure-only)
or be resequenced behind #1204, say so plainly — the operator wants the highest-value path, not
motion. I will build exactly the design you approve.
