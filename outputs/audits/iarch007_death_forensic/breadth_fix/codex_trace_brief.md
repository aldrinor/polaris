# Codex INDEPENDENT FORENSIC TRACE — the 485 -> 13 breadth funnel (I-arch-007)

You are Codex, running as a SEPARATE forensic brain. Read-only. Do NOT fix anything.
Your job: trace, at `file:line` precision, WHERE the report collapses from 485
weighted/basketed sources down to ~13 distinct cited sources, and WHERE a
§-1.3-faithful fix would insert. Be a skeptic. If my three hypotheses are wrong,
say so and give the real chokepoint with line numbers.

---

## §-1.3 DNA (operator-LOCKED — the architectural law this trace serves)

The pipeline is **WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP.**

1. **WEIGHT, DON'T FILTER.** Every relevant source flows to composition carrying a
   credibility weight (tier T1–T7 / authority_score). Tier IS the weighting system —
   surfaced per-citation to the user, NEVER a rank-then-drop hard filter.
2. **CONSOLIDATE, DON'T DROP.** Group sources carrying the SAME claim into a **basket**.
   Repetition is corroboration. Multiple citations per claim is GOOD and expected.
3. **BASKET FAITHFULNESS.** Decide a claim's faithfulness against its WHOLE basket of
   supporting sources, never a single URL/span. The verdict carries corroboration
   (count + weights + agreement). This STRENGTHENS faithfulness; it NEVER relaxes it.

**THE ONLY HARD GATE is the faithfulness engine** (strict_verify / NLI entailment /
4-role D8 / provenance / span-grounding). Everything else is a WEIGHT or a
CONSOLIDATION — never a DROP/CAP/THIN/TARGET.

**BANNED anti-pattern:** bolting hardcoded caps/targets/thinners onto the pipeline to
push a breadth number up. Breadth must **EMERGE** from honest weighted
multi-attribution. A §-1.3-faithful fix SURFACES the already-computed weighted baskets;
it must NEVER relax strict_verify / NLI / 4-role / span-grounding, never invent a
citation, never pad with a source that does not genuinely support its claim.

---

## EVIDENCE — the funnel is REAL (measured, not asserted)

Question Q78 / `drb_78_parkinsons_dbs` (Parkinson's deep-brain stimulation), from the
corpus snapshot `outputs/audits/iarch007_death_forensic/draft_audit/Q78_corpus_snapshot.json`:

- `evidence_for_gen` = **485 evidence items**, **484–485 distinct `source_url`/`doi`**
  (448 distinct `evidence_id`). These are weighted, scored, tiered, and basketed.
- Tier distribution: **T1=92** (peer-reviewed), T2=11, T3=16, T4=233, T5=1, T6=18,
  T7=60, UNKNOWN=54.
- Content substance: **451 of 485 have >=400-char `direct_quote`/`statement`**;
  only **34 are stubs (<400 char)**. So 451 substantive corroborating sources reach gen.
- The corresponding `evidence_pack.json` (the evidence the report ACTUALLY resolved /
  cited) has **~13–16 entries** — orders of magnitude smaller than 485.
- Prior measurement on the same family: the generated report cited **13 distinct
  sources, each cited ~14x** (185 citation tokens total).

**So ~437 substantive, weighted, basketed sources are computed and then DROPPED at the
render/generation layer.** That is the §-1.3 violation: breadth was forced DOWN to the
contract entity set instead of EMERGING from the weighted baskets.

---

## THE QUESTION (answer with file:line evidence)

Where does the report cap to ~13 cited sources out of 485 weighted? Decide which of these
three is the cause — **one, two, or all three** — with line numbers for each:

**(H1) The contract entity count.** The outline/citation set is DETERMINED by the report
contract's `required_entities`, not by the basketed corpus.
- `src/polaris_graph/nodes/report_contract.py` — `RequiredEntity` /
  `required_entities` (~line 137), `entities_by_slot()` (~line 151). How many entities does
  a slug's contract declare, and is that the hard ceiling on what can be cited?
- `src/polaris_graph/nodes/contract_outline.py` — `compose_outline_from_contract`
  (~line 169), `all_entity_ids()` (~line 127): the outline's `entity_ids` come ONLY from
  `contract.entities_by_slot()`. Does anything OUTSIDE the contract entity set ever reach
  the outline?

**(H2) Single-citation-per-claim render.** Even within a slot, the resolver emits ONE
bound token per sentence (the contract `entity_id`), not the basket's multi-citation union.
- `src/polaris_graph/generator/contract_section_runner.py` — the citation-marker rewrite
  (~line 172–189): "sentence iff its primary token resolves to **a contract entity_id**".
  Is each sentence limited to its single contract entity's citation? Note the EXISTING
  `_a1_basket_fallback` / `_basket_fallback_corroborators_for_slot` (~line 338–453) and the
  INLINE multi-citation basket render hook (~line 656–659, `_basket_for_biblio`): are these
  ACTIVE on the live path, or byte-identical no-ops because basket data is never threaded?

**(H3) The basket `supporting_members` are not wired to the citation layer.** The
credibility pass already builds full baskets keeping ALL sources, but the resolve sites
only carry cited tokens.
- `src/polaris_graph/synthesis/credibility_pass.py` — `ClaimBasket.supporting_members`
  keeps ALL sources (~line 166–197, 480–492, `_assemble_baskets` ~line 357). BUT the
  comment at ~line 673–675 states: "the resolve sites today carry only cited tokens (each an
  evidence_id) ... lets the render layer (P5.x) map a cited token to the basket ...
  **Reference data only.**" Is `supporting_members` ever consumed by the citation/render
  layer, or does it dead-end as reference data? Trace the consumer (or prove there is none).

For EACH of H1/H2/H3: VERIFIED-as-cause / PARTIAL / NOT-A-CAUSE, with the exact
`file:line` span text that supports your verdict.

---

## THE FIX QUESTION (where would §-1.3-faithful breadth insert?)

Identify the SMALLEST surgical insertion point(s) where the report would cite the
ALREADY-VERIFIED basket members per claim (multi-citation per claim) and broaden past the
contract entity set — WITHOUT relaxing ANY faithfulness gate:

1. **Multi-citation per claim from the verified basket.** Which resolve site(s) in
   `contract_section_runner.py` should emit the basket's span-VERIFIED `supporting_members`
   (those that passed ISOLATED per-member verification, `member_verdict == SUPPORTS` /
   `verified_support_origin_count`) as additional `[N]` citations — not just the single
   contract entity token? Confirm this consumes ONLY members that already passed
   strict_verify/span-grounding (no new claim is asserted, no gate relaxed).
2. **Broaden past the contract.** Where should basketed-but-non-contract sources (the ~437
   substantive T1–T7 sources not in `required_entities`) attach — as corroborators on an
   existing claim's basket, never as a new unverified claim? Name the file:line.
3. **Threading.** What is the minimal wiring so `supporting_members` (currently "reference
   data only," credibility_pass.py ~673–675) actually reaches the citation layer
   (`_basket_fallback_corroborators_for_slot` / `_basket_for_biblio` in
   contract_section_runner.py)? Is the plumbing already half-built (the A1 fallback / B6/B8
   inline render) and merely un-threaded / flag-gated OFF?

State explicitly for each proposed insertion: which faithfulness gate it touches (it must
touch NONE except to ADD already-passed corroborators) and why it is a WEIGHT/CONSOLIDATE
surfacing, not a CAP-removal that would admit unverified text.

---

## OUTPUT FORMAT

```
ROOT_CAUSE_VERDICT:
  H1_contract_entity_count: VERIFIED_CAUSE | PARTIAL | NOT_A_CAUSE  — file:line + span
  H2_single_citation_render: VERIFIED_CAUSE | PARTIAL | NOT_A_CAUSE — file:line + span
  H3_basket_not_wired:       VERIFIED_CAUSE | PARTIAL | NOT_A_CAUSE — file:line + span
PRIMARY_CHOKEPOINT: <the single most load-bearing file:line>
FIX_INSERTION_POINTS:
  - <file:line> — <what to change> — <which gate it touches (should be NONE relaxed)>
FAITHFULNESS_GUARANTEE: <one paragraph: why the fix never relaxes a gate / invents a cite>
NOTES: <anything I got wrong; the real funnel if my H1/H2/H3 are off>
```

Be precise with line numbers. This is read-only forensic; do not run pytest, do not edit.
