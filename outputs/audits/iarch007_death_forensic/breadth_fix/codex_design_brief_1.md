# Codex DESIGN-agree gate — I-arch-007 breadth-collapse fix (iter 1 of 3)

HARD ITERATION CAP: 3 per document. This is iter 1 of 3.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real faithfulness or correctness risks.
- If you detect "I'm holding back a P1 for the next round" — DON'T. Surface it now. The 3-cap means banked findings die.
- Verdict APPROVE iff zero P0 AND zero P1.

## How to run (you are in read-only sandbox)
- STATIC read-only analysis ONLY. Do NOT run pytest, do NOT build, do NOT execute anything. Read the files and reason.
- The design under review: `outputs/audits/iarch007_death_forensic/breadth_fix/BREADTH_FIX_DESIGN.md`. Read it in full first.
- Repo root is `C:/POLARIS` (passed via `-C`). All paths below are repo-relative.

## What this design does (one paragraph)
The benchmark renders ~5 contract-bound entities + a few planner picks, so ~437 weighted, span-verified SUPPORTS sources never surface (the "breadth funnel"). The fix has two items. ITEM 1: prove (no new prod code) that the already-live whole-basket inline multi-citation render works on the Gate-B contract path. ITEM 2: add ONE field-agnostic enrichment section whose `ev_ids` are the UNBOUND basket SUPPORTS members ordered by `weight_mass` (full list, no cap/target), routed through the UNCHANGED `_run_section` so strict_verify decides what renders. New code = one helper file + a ~6-line additive, default-OFF append in `multi_section_generator.py`.

## Your job — verify these claims, in this priority order

**CLAIM A (the load-bearing faithfulness claim).** Every sentence in the new enrichment section is gated by the SAME strict_verify the contract path uses, so no fabricated/unsupported citation can render. Verify `_run_section` (`src/polaris_graph/generator/multi_section_generator.py`, def at `:3544`) routes drafted text through `strict_verify(rewritten, evidence_pool)` (I read it at `:3657`) and applies the section-floor `kept_fraction` (`:3717-3718`); and that a NON-contract-titled plan reaches `_run_section` via `_run_legacy_bounded`/`is_contract_section()` (`contract_section_runner.py:1621`). If `_run_section` does NOT verify enrichment sentences, the whole faithfulness argument fails — that is a P0.

**CLAIM B (no fabricated/unsupported citation introduced).** In `select_unbound_supports_by_weight` as specified (§2.3): it only ever returns members with `span_verdict == "SUPPORTS"` that resolve in `evidence_pool`; weight is ORDERING only; it returns the FULL list (no `[:N]`/cap/target/floor); `credibility_analysis is None` ⇒ returns `[]`. Confirm this cannot smuggle an UNSUPPORTED member into render, and that an empty result yields no section (byte-identical). The basket source fields it reads (`baskets`, `BasketMember.span_verdict`, `BasketMember.evidence_id`, `ClaimBasket.weight_mass`, `supporting_members`) exist — verified at `src/polaris_graph/synthesis/credibility_pass.py:140-186` (dataclasses) and `:442-457` (per-member `span_verdict == "SUPPORTS"` assembly), and `CredibilityAnalysis.baskets` at `:199`.

**CLAIM C (item 1 multi-citation is faithful + anti-cross-claim preserved).** `verified_corroborators_for_tokens` (`provenance_generator.py:2961-3006`) expands ONLY a token mapping to EXACTLY ONE cluster (the `len(_ccids) != 1: continue` guard at `:3000-3001`), only SUPPORTS members, only members in `evidence_pool`. The contract-path call site is `contract_section_runner.py:1364-1372`. Confirm the design keeps this UNCHANGED and that nothing in the design relaxes the single-cluster guard.

**CLAIM D (§-1.3 faithfulness — the architectural law).** Verify the fix surfaces real weighted corroboration and does NOT:
- force a breadth NUMBER (no cap/target/thinner/top-N/floor anywhere — the deleted `_augment_legacy_section_breadth`/`PG_LEGACY_SECTION_BREADTH_TARGET` bolt-on is at `multi_section_generator.py:6507-6512`; confirm this fix is categorically different, §2.4);
- relax strict_verify / NLI / 4-role D8 / span-grounding / the ≥40% section floor / the fail-closed sentinel (the design asserts ALL unchanged — verify no specified change touches any of them);
- attach a citation to a claim it does not support (anti-cross-claim, CLAIM C).
Breadth must EMERGE from how many offered sources survive the unchanged gates.

**CLAIM E (file:line site correctness).** Spot-check the design's anchors are right:
- `multi_section_generator.py`: plan/enrichment assembly `:6482-6492`; `evidence_pool` built `:6505`; death-fix credibility wall + always-release degrade `:6642-6707` (`credibility_analysis` resolved to a value-or-None by `:6692`/`:6706`); `ev_subset` enrichment chokepoint `:3577-3580`.
- The design's append must occur AFTER `credibility_analysis` is resolved (~`:6707`), NOT at `:6482` where it is not yet set — confirm the design says this (§2.3 parenthetical + §5 step 3) and that the relocated insertion is correct.
- Note for your check: I corrected the `credibility_pass.py` path to `src/polaris_graph/synthesis/credibility_pass.py` during anchor verification (it is under `synthesis/`, not `generator/`); the line anchors `:140-186` and `:442-457` are correct. Flag if you find any remaining wrong path/line.

**CLAIM F (degrade / collision boundary).** The design declares "baskets present" as a precondition and does NOT re-touch the degrade path (`credibility_analysis is None`), which is the death-fix's domain (`:6670-6698`). Confirm the additive append cannot collide with or alter the death-fix block, and that on the degrade path the fix is byte-identical (empty ev_ids ⇒ no section).

## Output schema — END your response with EXACTLY ONE of these as the FINAL line
Put all findings ABOVE the verdict line. The harness parses the LAST `verdict:` line.

```
verdict: APPROVE
```
(iff 0 P0 AND 0 P1)

OR

```
verdict: REQUEST_CHANGES
```
with, above it:
- p0: [...]
- p1: [...]
- p2: [...]
- notes: [...]
