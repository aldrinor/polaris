# CONSOLIDATED PLAN — Entailment-Speed Fix + Basket-Grounded Repair Loop
_(Claude Codex Workflow wf_943791a5-d84 — 3 web-research + 3 code-investigation + Codex cross-check, 2026-06-16)_

**Anchor:** I-arch-007 / I-arch-006 (GH #1262/#1263). DNA = WEIGHT-AND-CONSOLIDATE (CLAUDE.md §-1.3).
**No faithfulness gate is relaxed anywhere.** strict_verify / NLI entailment / 4-role D8 thresholds, two-family
segregation, the sovereign open-weight lock, and the fail-closed `judge_error` contract are all preserved. Every
PART-A change is transport/concurrency (changes WHEN a verdict computes, never WHAT); every PART-B change
STRENGTHENS grounding (judge a claim against its whole basket, not one span).

## PART A — ENTAILMENT-SPEED FIX (surgical, zero verdict-logic change)

### A.0 Correct diagnosis (NOT "150s too tight")
Real GLM-5.1 NLI calls are ~6–40s (`entailment_judge.py:109`); `PG_ENTAILMENT_TOTAL_S=150` is a trickle-hang
backstop (Cloudflare holds the socket + trickles keep-alive bytes). The blow-up = three amplifiers:
1. **SERIALIZATION (dominant):** per-sentence judge runs serially by default (`PG_PARALLEL_VERIFY` unset → 1 worker,
   `provenance_generator.py:2553-2562`). Thousands of 6–40s calls back-to-back.
2. **Retry over-spend on hang:** a trickle-hung socket burns 3×150s=450s (`_DEFAULT_ENTAILMENT_RETRIES=2`,
   `entailment_judge.py:143`) and re-hangs on the same provider.
3. **Regen amplification:** judge_error → strict_verify drop → below `PG_MIN_KEPT_FRACTION=0.4`
   (`run_honest_sweep_r3.py:8071`) → `tighter_retry` section regen (`multi_section_generator.py:3477-3514`) which
   re-runs the WHOLE entailment pass on the retry draft.

### A.1 Knob changes
| # | Knob | File:line | Current | Proposed | Faithfulness |
|---|---|---|---|---|---|
| **A1** | `PG_PARALLEL_VERIFY` | `provenance_generator.py:2553-2562` | unset→1 serial | **=4** (validate 4→8 smoke; cap by keepalive pool 8 + 429 headroom) | NEUTRAL — changes WHEN not WHAT; identical judge per sentence. ENV-ONLY, no code change. |
| **A2** | total_deadline retry cap | `entailment_judge.py:404-425,143,394` | 2 extra retries (450s worst) | **retry `total_deadline_exceeded_*` at most ONCE** via new `PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES` (default 1). Other reasons keep 2. | NEUTRAL — same fail-closed `judge_error`→DROP sentinel on exhaustion. CODE change. Must branch on `reason.startswith("total_deadline_exceeded")`. |
| A3 | per-call deadline | `entailment_judge.py:111` | 150 | **KEEP 150** (single-span); a SEPARATE larger deadline for PART-B whole-basket verify | — |
| A4 | max_tokens | `entailment_judge.py:172` | 131072 | **KEEP** (operator §9.1.8 lock; web confirms generous-cap) | — |
| A5 | reasoning effort | `entailment_judge.py:174` | "high" | **KEEP** (§9.1.8 MAX lock; lowering = deferred operator call) | — |
| A6 | structured output | `entailment_judge.py:359` | json_object | optional future enum/JSON-schema (defer) | — |

**Role-routing preflight (do FIRST, guard not code):** assert every entailment call used mirror `z-ai/glm-5.1`
(`entailment_judge.py:81`), NOT Qwen. Drift → abort before spend.

### A.2 Section-gen hang — ALREADY DONE (verify, don't rebuild)
`asyncio.wait_for` already wraps section runner (`multi_section_generator.py:191-214`, default-ON 1800s) AND the
generator transport call (`openrouter_client.py:1977,2006`, default 600s). Smoke-confirm both fire; only add a guard
if the outline-builder call bypasses it (grep at build time).

### A.3 Sentinel blank — distinguish transport-blank from parsed-UNGROUNDED
`role_pipeline.py:269-276` collapses "Sentinel returned nothing (transport fault)" with "Sentinel said UNGROUNDED".
Fix: retry the Sentinel role on a TRANSPORT BLANK only (new `PG_SENTINEL_BLANK_RETRIES`, default 1–2); if still
blank → STAYS UNSUPPORTED. Faithfulness-neutral-to-positive (a flaky socket shouldn't cost a real claim; a genuine
UNGROUNDED still downgrades). CODE change.

### A.4 The second (re-anchor) judge call `provenance_generator.py:2158` (~900s/claim worst) is SUBSUMED by PART B — route re-anchor through the basket branch, don't stack.

## PART B — BASKET-GROUNDED REPAIR LOOP (the §-1.3 Principle-3 gap)
**Keystone finding: the claim-level repair loop is a PHANTOM** — `rewrite_already_attempted` is hardcoded `False`
at every non-test call site (`release_policy.py:297-303`); no outer loop flips it, so the "one rewrite attempt" the
whole D8 policy is built around never executes. Baskets ARE built + live on the run path
(`claim_graph.cluster_equivalent_claims:759`, assembled `multi_section_generator.py:6287-6368` BEFORE Stage-2), but
the binding gate (strict_verify) is basket-blind/single-span. Whole-basket verify EXISTS but is advisory only
(`credibility_pass._verify_member_in_isolation:199-242`, `_assemble_baskets:245-357`).

### B.1 Algorithm (per claim, after first strict_verify; bounded ≤N=3 `PG_BASKET_REPAIR_MAX_CYCLES`):
```
verify_claim_against_basket: members=clusters[cluster_id]; isolated=[m passing _verify_member_in_isolation]
  any member entails FULL claim → SUPPORTED ; jointly support narrower → PARTIAL ; member contradicts → CONFLICT ; else UNSUPPORTED
loop (≤N):
  SUPPORTED  → keep, cite supporting member(s); STOP        # multi-citation = GOOD
  PARTIAL    → (a) REWRITE-TO-EVIDENCE: re-anchor to a sibling IFF same cluster_id AND it independently passes
                   _verify_member_in_isolation on the FULL claim ; else (b) SOFTEN to the narrower basket scope (minimal edit)
  CONFLICT   → DROP/replace + DISCLOSE; STOP
  UNSUPPORTED→ soften to basket scope if any, else DROP + DISCLOSE; STOP
  GUARD: each cycle MUST inject NEW basket evidence; if none new → STOP (self-refine w/o new evidence degrades)
RE-GATE ONLY THE CHANGED CLAIM (re-run strict_verify on it; NOT whole-section regen). Terminal = release-with-label, NEVER hold.
```
Plug-ins (file:line): thread baskets into `repair_dropped_section_sentences` (`multi_section_generator.py:3394-3448`);
reuse `_verify_member_in_isolation` as the engine; widen `sentence_repair.py:346-356,300-309` token-set/PT12 to
"same-cluster + isolated-verified-on-FULL-claim"; **flip the phantom `rewrite_already_attempted=True`** after a real
cycle (`release_policy.py:213-233`); re-gate changed claim only (replaces broad `tighter_retry` regen = also a speed win).
**Faithfulness STRENGTHENED:** sibling re-anchor needs independent isolation-pass on the FULL claim (no union
laundering); basket may only downgrade/drop/label, never upgrade; binding gate unchanged.

## PART C — SMOKE (resume a corpus_snapshot, no retrieval):
1 Q (Q90 or lightest), baseline serial vs A1=4+A2 ; from judge ledger/raw-LLM-IO capture entailment wall-time +
`judge_error` count + `total_deadline_exceeded` count + `tighter_retry` count. Assert: wall-time materially down;
deadline-exceeded down; judge_error NOT up (else 429 → drop parallel to 2–3); real `status:ok` ratio holds/improves;
report RELEASES (STATUS_RELEASED[_WITH_DISCLOSED_GAPS], not abort). PART-B smoke: a claim failing its cited span but
corroborated by a sibling → re-anchors OR softens+discloses, and `rewrite_already_attempted` flips True. Then §-1.1
line-by-line audit of the released smoke report (gates-green ≠ faithful).

## PART D — INVARIANTS + OPEN QUESTIONS
**MUST NOT change:** no faithfulness-gate relaxation; verifier timeout NEVER becomes support (fail-closed
judge_error→DROP preserved); open-weight/sovereign only (entailment stays glm-5.1, effort MAX, max_tokens 131072);
verifier labels-never-holds applies to EVIDENCE-GAP holds only — PRESERVE the two integrity/safety holds (the
fabrication-screen body-withhold `run_honest_sweep_r3.py:2404-2422` + `safety_floor_insufficient`
`release_policy.py:603-615`); FABRICATED stays excised+disclosed; OFF paths byte-identical (every new env defaults to
current behavior, read at call time).
**Open questions for operator:** (1) Fast-verifier cascade (distilled OPEN-WEIGHT NLI like MiniCheck/Paladin/DeBERTa,
escalate only low-confidence to the slow judge) = the 100× lever but a new model → sovereignty sign-off needed — the
next lever IF A1+A2 prove insufficient at scale. (2) Lower reasoning effort for binary NLI conflicts with §9.1.8 lock.
(3) Confirm the two integrity/safety holds stay as the carve-out to "never holds".

## EXECUTION ORDER (autonomous, operator away)
1. Validate A1 (env-only, dominant win) via a snapshot-resume smoke — measure verify wall-time vs the serial twin.
2. Write A2 + A3 code diff (batched) → Codex diff gate (cap 5).
3. Deploy 5 FIXED runs (A1 env + A2/A3 code) — full batched fix.
4. Build PART B repair loop (separate follow-up) → smoke → Codex gate.
Faithfulness NEVER relaxed; all fixes ONE batched diff; commit-per-unit.
