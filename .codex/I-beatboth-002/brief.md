HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: review ONLY against 2025-2026 frontier practice; no grandfather downgrade. Reject any design choice justified by a pre-2024 pattern; verify external claims against the cited primary source (AutoVerifier arXiv 2604.02617v1; CiteEval ACL 2025; Contradiction-to-Consensus 2602.18693v1) as inspiration-only on our own slate.

---

# Codex BRIEF review — I-beatboth-002 (Fix 1) increment 1: F1-0 (replay-harness FIRST) + F1-1 (multi-cited compose, PER-BASKET verify pool)

**This is a BRIEF gate, not a diff gate.** You are confirming the ACCEPTANCE CRITERIA + design are CORRECT, BUILDABLE, and FAITHFULNESS-PRESERVING for this increment — before any code is written. Verify the increment boundary, the per-basket-pool decision, and the F1-2-deferral safety hole. Do NOT review a diff (none exists yet); do NOT run pytest.

## GOAL

GitHub issue #1278 (umbrella #1270 beat-both; lane #1268 consolidate→synthesize + #1274 RC-D). DRB-II analysis dimension (18%) needs verified cross-source SYNTHESIS. Today `verified_compose` composes ONE basket at a time. Fix 1 promotes it to a multi-cited synthesis producer WITHOUT relaxing faithfulness. This increment ships ONLY the first two of the five F1 steps:

- **F1-0 (harness FIRST):** a §-1.4 fail-loud replay-harness on a real `corpus_snapshot.json`. Synthesized sentences appear in `report.md`, each carries its cited baskets' citations, every citation strict_verify-passes; a contested basket (carrying a `ContradictionEdge`) renders both-sides or labeled author-summary, NOT "consistently". **Non-zero exit on silent no-op.**
- **F1-1:** `verified_compose` composes a multi-cited synthesized sentence from N corroborating basket members; UNCHANGED `strict_verify` per cited member; **PER-BASKET verify pool by default** (the ONE open decision — union ONLY with Codex + operator sign-off); **P1-2 fail-closed** for any `evidence_id` outside the cited baskets.

Design basis: `state/beatboth_campaign/PHASE4_DESIGN_BASIS_2026.md` Fix 1 (advisor-blessed 2026-06-20), §38-41 (the open decision), §44-45 (F1-0/F1-1 steps).

## SCOPE FENCE — what is and is NOT in this increment

**IN:** F1-0 (the harness) + F1-1 (multi-cited compose with per-basket pool). The harness is built FIRST and gates F1-1.

**OUT (later increments, do NOT flag as missing):**
- **F1-2** — the relational-quantifier guard (detect aggregate predicates `consistently / most / broad consensus / studies show` + the §2.3 independence-weight-mass + zero-ContradictionEdge predicate → `both_sides.py` or labeled author-summary). DEFERRED. See the boundary contract below — this increment is SAFE WITHOUT F1-2 because F1-1 does not emit an unguarded aggregate predicate (see "Boundary contract").
- **F1-3** — wiring `PG_SWEEP_CLAIM_GRAPH` + `PG_SWEEP_BOTHSIDES_DISCLOSURE` onto the synthesis path. `src/polaris_graph/synthesis/claim_graph.py`, `both_sides.py`, `independence_collapse.py` stay default-OFF with NO production caller in this increment — that is correct and intentional, not a gap.
- **F1-4** — full banked-corpus §-1.1 behavioral acceptance.

## THE BOUNDARY CONTRACT (the one place this increment can be unsound — verify it closes)

Per the design basis itself (§17, §34-35): `strict_verify` / span-grounding **cannot** verify a RELATIONAL QUANTIFIER — every fact in a sentence can be span-true while the word "consistently" is invented. That guard is F1-2, which is DEFERRED in this increment. Therefore F1-1, as built here, **MUST NOT permit the writer to emit an emergent cross-member aggregate predicate**, or the increment ships an unverified quantifier with no guard (a P0).

**Increment-1 reading (conservative, the only sound one — verify the criteria enforce it):** the F1-1 "multi-cited synthesized sentence" is composed as **per-member attributed clauses**, each clause independently `strict_verify`-passing against its OWN basket's scoped pool + landing within its OWN basket's member region (the existing `_tokens_within_basket_regions` P1-1 gate). Multi-cited = multiple per-member-verified clauses co-located, EACH carrying its own member's `[#ev:...]` token. There is **NO emergent aggregate claim** ("studies consistently show X") asserted across members until F1-2's quantifier guard lands. This is "faithful by construction" and matches §40 ("over-relaxing faithfulness is the lethal direction"; under-relaxing is safe).

The render PROBE writer already in production (`build_short_member_sentence`, `verified_compose.py:166-193`, NO-LLM, first-sentence-of-strongest-member) is per-member and safe by construction; if F1-1 keeps a deterministic / per-member-attributed writer, the boundary holds. If F1-1 instead wires an abstractive LLM writer that can synthesize an aggregate predicate NOW, it has effectively pulled F1-2 forward and the deferral claim is false.

**Codex: confirm the F1-1 acceptance criteria forbid an unguarded aggregate predicate in this increment.** This is the single load-bearing soundness check.

## F1-0 must actually DISCRIMINATE per-basket vs union (the harness is the gate for the open decision)

F1-0 is what makes the per-basket-vs-union decision EVIDENCE-BACKED rather than asserted. The existing single-basket ancestor harness `scripts/iarch011_prc_verified_compose_replay_harness.py` proves the point for ONE basket via fixture c3 (a sentence content-faithful to a FOREIGN basket citing `[#ev:c2]`; under basket-3's scoped pool that foreign id is ABSENT → strict_verify REJECTS → own K-span; under a FULL pool it would wrongly PASS — the P1-2 regression that fixture discriminates).

For the MULTI-CITED case F1-0 needs the analogous discriminating PAIR (verify the criteria require BOTH):
1. a fixture that **FAILS if the pool were union** — a multi-cited sentence whose foreign citation MUST be rejected under per-basket (proves per-basket is actually wired, not silently widened to union); AND
2. a fixture proving per-basket does **NOT wrongly reject** genuine multi-cited synthesis where every clause cites its own in-basket region (design §51 — this is the smoke that would JUSTIFY escalating to union; if per-basket wrongly rejects it, that is the trigger to take the union question to Codex + operator).

Plus the contested-basket fixture from F1-0's own AC: a basket carrying a `ContradictionEdge` renders both-sides or labeled author-summary, NOT "consistently" (this fixture exercises the contested path that F1-3 will fully wire; in this increment it asserts the writer does not fabricate consensus over a contested basket).

New harness path (mirror the ancestor): `scripts/iarch_beatboth002_f1_multicited_replay_harness.py`. The LLM writer is FAKE/injected; `strict_verify` is the REAL production `verify_sentence_provenance`; no network, no model spend, no relaxation. Non-zero exit on silent no-op (zero synthesized sentences in `report.md`, or a foreign citation surviving, or a contested basket asserted as consensus).

## THE ONE OPEN DESIGN DECISION (needs your sign-off)

The AutoVerifier finding recommends the verify pool be the UNION of all cited baskets for a multi-cited sentence. POLARIS's existing P1-2 contract scopes the pool to a SINGLE basket (`_basket_scoped_pool`, `verified_compose.py:70-80`) and fails closed on any cross-basket citation (`_tokens_within_basket_regions`, lines 118-134). "Union" LOOSENS the region check; "per-basket" PRESERVES it.

**This increment DEFAULTS to per-basket** (the tighter, lane_synthesis §2.3 reading): each citation strict_verifies against its OWN basket region; the multi-cited sentence is the co-location of per-member-verified clauses. We do NOT write "union" as settled. Flip to a union pool ONLY if F1-0's fixture #2 proves per-basket wrongly rejects genuine multi-cited synthesis — and ONLY with explicit Codex review + operator sign-off (a scoped, documented extension of P1-2, never a silent change). **Codex: bless per-basket as the increment-1 default, or state the specific fixture evidence that would force union now.**

## Files I have ALSO checked and they're clean (verified by reading the actual files, not titles)

- `src/polaris_graph/generator/verified_compose.py` — VERIFIED the code map: `_verified_compose_enabled()` (46-49, `PG_VERIFIED_COMPOSE` default-OFF); `_basket_scoped_pool` (70-80, scopes to own member ids on GLOBAL rows, foreign id absent = fail-closed); `_basket_member_regions` (104-115) + `_tokens_within_basket_regions` (118-134, P1-1 own-region gate); `build_verified_span_draft` (137-163, basket-id-bound verbatim K-span fallback); `build_short_member_sentence` (166-193, deterministic NO-LLM render-probe writer, per-member by construction); `_compose_one_basket` (203-242, ONE basket → scoped pool → per-sentence verify + region check → own K-span / disclosure fallback, NEVER empty — CONFIRMED no cross-basket leakage); `_compose_section_per_basket` (245-260); `_section_baskets_for_compose` (263-279). The per-basket isolation invariant F1-1 must preserve is already enforced here.
- `src/polaris_graph/generator/multi_section_generator.py` — VERIFIED the call site: `_run_section()` 3910-3942 is the VERIFIED-COMPOSE PRIMARY branch (gated on `_verified_compose_enabled()` AND `credibility_analysis` AND baskets found), output `raw = "\n".join(...)` (3936) → UNCHANGED `_rewrite_draft_with_spans` (3971) → `strict_verify` (3975) → report.md. Legacy `_call_section()` fallback at 3943-3953 when not enabled/no baskets. Default-OFF path is byte-identical.
- `src/polaris_graph/synthesis/claim_graph.py` — `_FLAG = "PG_SWEEP_CLAIM_GRAPH"` (76), `claim_graph_enabled()` (112), `ContradictionEdge` (190), `build_contradiction_edges` (829). Default-OFF, NO production caller. DELIBERATELY UNTOUCHED this increment (F1-3 wires it).
- `src/polaris_graph/synthesis/both_sides.py` — `bothsides_disclosure_enabled()` (32), `compose_both_sides(...)` (68), `render_both_sides` (164). Default-OFF, NO caller. DELIBERATELY UNTOUCHED (F1-3).
- `src/polaris_graph/synthesis/independence_collapse.py` + `weight_mass.py` — origin-cluster weight-mass library, default-OFF, NO caller. DELIBERATELY UNTOUCHED (F1-2/F1-3 consume it).
- `src/polaris_graph/generator/provenance_generator.py` — `verify_sentence_provenance` (the REAL per-sentence gate) + `parse_provenance_tokens`. UNCHANGED — F1-1 calls it as-is, never relaxes it.
- Ancestor harness `scripts/iarch011_prc_verified_compose_replay_harness.py` — the single-basket discriminating-fixture pattern F1-0 mirrors for the multi-cited case.

## BINDING faithfulness invariants (any violation = P0)

- `strict_verify` / NLI / 4-role D8 / provenance / span-grounding = the ONLY hard gate, NEVER relaxed, NEVER replaced. F1-1 runs the UNCHANGED `strict_verify` per cited member.
- **Always-release:** the verifier LABELS, it never HOLDS. No abort/hold introduced. A failing clause falls back to its basket's verbatim verified K-span or an honest insufficient-evidence disclosure — never empty, never held.
- **Default-OFF + byte-identical when off:** `PG_VERIFIED_COMPOSE` off → the legacy section-prose path is unchanged byte-for-byte. F1-1 adds NO new always-on behavior.
- **Per-basket region grounding (P1-2/P1-1) preserved:** a citation outside the cited baskets fails closed; F1-1 does not widen the pool.
- **No unguarded aggregate predicate** (the boundary contract above) — F1-2 deferred means F1-1 must not assert an emergent cross-member quantifier.

## Output schema (§8.3.9 — return EXACTLY this, machine-parseable)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — return the schema. APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
