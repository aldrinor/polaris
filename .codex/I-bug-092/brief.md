# Codex Brief — Provenance-correctness gap (post-audit architectural fix)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- DO NOT call exec / rg. Brief is self-contained.
- Don't pick bone from egg. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What the audit found

We just ran a **content-level line-by-line audit** of the V3.2-Exp + Gemma 4 31B tirzepatide report (Claude + Codex parallel, 20 atomic claims, full-source reads). Aggregate verdict: **13 VERIFIED / 4 PARTIAL / 2 UNSUPPORTED / 1 FABRICATED**.

The fabrications/inflations the strict_verify gate let through:

**M2 — fabricated mechanistic granularity** (the worst case):
- Report says: *"GIP receptor agonism independently potentiates insulin secretion from pancreatic β-cells and acts on adipocytes to influence lipid metabolism and energy storage."*
- Cited URNCST source actually says: *"synergistic actions on insulin secretion, glucagon suppression, appetite regulation, and adipocyte metabolism."*
- Generator inserted: `pancreatic β-cells`, `GIP receptor agonism independently`, `lipid metabolism`, `energy storage` — none of these specifics are in the cited text.

**C2 — comparator inflation**:
- Report: *"tirzepatide HbA1c reductions up to 2.4%, exceeding semaglutide at the highest studied doses"*
- URNCST: *"up to 2.4%... compared to GLP-1 RAs"* (class-level)
- "exceeding semaglutide at the highest studied doses" is generator-invented specificity.

**C1 partial**:
- The <5.7% range (27-46% vs 19%) is sourced.
- The ≤6.5% range (69-80% vs 64%) is **not in any accessible source** — likely fabricated or pulled from paywalled NEJM Table 2 we couldn't reach.

## Why strict_verify let these through

`src/polaris_graph/generator2/strict_verify.py:89` `verify_sentence()` runs five mechanical checks:

1. **Token presence** — `[#ev:ev_id:start-end]` must exist in sentence
2. **Token validity** — token references known source_id in pool
3. **Span bounds** — start-end falls within source character bounds
4. **Decimal subset** — every decimal in sentence appears in cited span (one-way: span can have MORE)
5. **Content-word overlap** — `>=N` shared content words between sentence and span (default N=2 via `PG_PROVENANCE_MIN_CONTENT_OVERLAP`)

For M2: the URNCST span contains "insulin secretion", "adipocyte metabolism" — those overlap with the sentence (≥2 shared words). The decimal check is moot (no decimals in this sentence). Token validity OK. **All five checks pass.** But the *additional* claims the sentence introduces (β-cells, lipid metabolism, energy storage) are not enforced to come from the span. The check is **necessary but not sufficient** — it bounds claims to the same TOPIC as the source but not to the same FACTS.

For C1: if the cited span happens to contain the word "62%" or "70%" anywhere, the claim's "69-80%" passes the decimal check (because `69` and `80` happen to appear elsewhere in the source) AND the content-word check (because "tirzepatide", "semaglutide", "HbA1c" overlap). But the SPECIFIC CLAIM (69-80% reaching ≤6.5%) need not be present.

For C2: pure qualitative drift. No decimals to check. "tirzepatide", "semaglutide", "highest" all share content words. Passes mechanically.

**Architectural diagnosis:** strict_verify enforces **provenance presence** (token format + lexical overlap), not **provenance correctness** (semantic entailment between sentence and span). The current design assumes that lexical overlap implies content fidelity. Empirically, with capable generators, this assumption breaks — they generate plausible-sounding extensions of the source's topic that share words but introduce unsourced facts.

## Existing substrate (relevant)

`src/polaris_graph/agents/nli_verifier.py` — NLI-based entailment verifier already exists:
- Uses `flan-t5-large` (75.0% LLM-AggreFact, 770M params, runs on CPU)
- Optional `Bespoke-MiniCheck-7B` (77.4%, requires vLLM/Linux)
- `PG_NLI_ENABLED` defaults to `0` (off)
- Has `_ANALYTICAL_CLAIM_PATTERNS` regex to skip synthesis-style claims
- Has domain-adaptive threshold + LLM-second-opinion fallback for borderline
- Known limit per memory: flan-t5 has 512-token context; spans need to be chunked or pre-extracted to ~2K chars (`_extract_quote_context()`)

But this substrate is **NOT wired into strict_verify.py**. The generator2 path runs only the 5 mechanical checks. The NLI verifier sits in the older agent-graph path (M-INT-era).

## Candidate solutions (you pick architecturally correct one)

**Option A — Wire existing NLI verifier into `strict_verify.verify_sentence()`** as a 6th check after content-word overlap. Set `PG_NLI_ENABLED=1` by default. Drop sentence if NLI says CONTRADICT, route to LLM second-opinion if DISPUTED. Trade-off: adds ~5-10s per sentence on CPU; the 13/20-section run would add ~60-120s.

**Option B — LLM-as-judge content check using the existing two-family evaluator (Gemma 4 31B)**. After strict_verify keeps a sentence, ask Gemma "Does the cited span entail this exact sentence?" with structured output. Drop if no. Trade-off: 1 extra Gemma call per kept sentence (~$0.0005 each, ~50 calls per report, ~$0.025 total). Avoids the flan-t5 dependency. Bonus: same-evaluator stays consistent.

**Option C — Reverse-direction overlap (sentence-words-IN-span requirement)**. Currently requires N words in common. Change to: `>=80% of the SENTENCE's content words must appear in the cited span`. Catches over-elaboration mechanically. Cheap, no model. Trade-off: false-positives on legitimate paraphrasing where the generator uses synonyms; needs synonym table or stemming.

**Option D — Structured fact extraction + per-fact verification**. Decompose each sentence into (subject, predicate, object) triples, then verify each triple against the span. Requires a small extraction LLM call per sentence. Trade-off: adds latency, complexity; hardest to implement reliably.

**Option E — Hybrid B+C**: cheap rule-side reverse-overlap (C) catches obvious over-elaboration without any model call; LLM-judge (B) catches the residual qualitative drifts that survive C. Both gates ON; sentence dropped if either gate fails.

## What I want from you

1. **Pick the architecturally correct path** — A, B, C, D, E, or hybrid. Justify in 2-3 sentences against the audit failures (M2, C2, C1).

2. **Identify the minimum implementation surface** — where in `strict_verify.verify_sentence()` does the new check go? Does it slot in as `check 6` or replace `check 5`? Does the `is_synthesis_claim=True` exemption in line 120 still apply?

3. **Test surface** — what tests should pin the new behavior so it doesn't regress? At minimum we need the M2/C2/C1 patterns as test cases.

4. **LOC estimate** — does this fit under CHARTER §3 200-LOC cap? If not, propose split.

5. **Crown Jewel candidate?** — `tests/crown_jewels/` has 7 binding tests for the §9.1 invariants. Should "no claim survives strict_verify if cited span doesn't entail it" become I-cj-008?

6. **Risk** — what false-positive class do you anticipate (legit claims dropped)? What's the rollback plan if the new gate is too aggressive?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
recommended_option: A | B | C | D | E | hybrid
fix_location: <file:line>
test_surface: [list]
loc_estimate: <number>
crown_jewel_candidate: yes | no
false_positive_risk: <one sentence>
rollback_plan: <one sentence>
rationale: <2-3 sentences>
```
