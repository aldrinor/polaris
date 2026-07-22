# Consolidated Implementation Plan — closing the RACE gap without touching faithfulness

**Author:** Opus (consolidation of two independent reviews)
**Reviewers:** Sol (GPT-5.6, read the code cold) · Fable 5 (Claude, read code + tested the cellcog swap)
**Date:** 2026-07-16
**Status:** PLAN ONLY. Build is delegated to a workflow; this document is the contract for that build.

> ## ⚠️ TARGET CODEBASE — read before any edit
> **ALL modifications land in the CHAMPION pipeline: `/home/polaris/wt/outline_agent`.** Never edit cellcog.
> - **Files we modify (all in champion):** `scripts/compose_agentic_report_s3gear329.py`, `src/polaris_graph/generator/multi_section_generator.py`, `src/polaris_graph/generator/provenance_generator.py` (the frozen `strict_verify` lives here — READ-ONLY), `scripts/adapt_cards_to_champion.py`.
> - **Cellcog (`/home/polaris/wt/flywheel`) is READ-ONLY**, used two ways only: (1) copy proven *logic* FROM it into the champion (e.g. `argument_planner.py:find_bundles`, the source-eligibility firewall); (2) read *data* FROM it for Pillar 5 (`outputs/compose_inputs/task72_cards_curated.json`, `outputs/provenance_graph.json`).
> - **⚠️ Filename collision:** `compose_agentic_report_s3gear329.py` exists in BOTH repos. The build MUST hard-pin `/home/polaris/wt/outline_agent` as cwd and reject any `/home/polaris/wt/flywheel/...` path as an edit target. Editing the flywheel copy = silent no-op on the champion.

---

## 0. The one-paragraph situation

Our open-weight champion is the faithfulness leader (FACT 90.3%, 84 supported citation-instances) but trails on RACE quality: **0.4447** vs Fable **0.5065** and Gemini **0.4506**. Task-72 dimension weights are **Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14**. Both reviewers, working blind to each other, reached the **same diagnosis**: the gap is *architectural*, not a model or corpus-size problem — and the fix is **more verifiable structure**, never less verification. Sol independently ranked the **instruction-following / source-eligibility contract as the #1 fix**, which matches the operator's directive to make instruction-following "super super smart."

**Non-negotiable guardrail (operator, hard line):** FAITHFULNESS IS FROZEN. Do not touch `strict_verify`, the drop rule, or the verification layer in any way — no change, no new pass, no new test, no re-verification. The 90.3% must stay produced by exactly today's code. Every quality gain in this plan comes from *upstream* changes (what evidence enters, how sections are planned) — never from the verifier. Priority order: **COVERAGE > INSIGHT > READABILITY**.

---

## 1. What both reviewers agree on (high confidence — build on these)

1. **Root cause is a three-link chain, not one bug:**
   - **(a) Starved analytical sections.** The outline assigned ~33–35 evidence IDs to descriptive body sections but **only 3 each** to Policy, Cross-Study Synthesis, and Conclusions. Fable: only 132 of 997 evidence rows (13%) were used at all.
   - **(b) A prose contract that bans insight.** The field-agnostic section prompt requires *every sentence to end in a citation*, targets 10–18 atomic fact sentences in one paragraph, and says "just the paragraph body." Topic sentences, cross-study interpretation, and transitions cannot survive by construction.
   - **(c) Post-verify deletion with no coherence repair.** `strict_verify` dropped **64 of 155 sentences (41%)**, concentrated in the analytical sections (Synthesis kept 3/15 = 20%; Conclusions 8/21; Policy 5/13), then the driver **concatenates survivors in original order** — producing sections that open mid-thought and 450-word single-paragraph walls.

2. **This is NOT primarily a length problem.** Fable won with ~4,090 words vs our ~3,914. Fable spends its words on a thesis-first TL;DR, key findings, positive-vs-negative framing, method notes, and an industry comparison **table**; we spend ours on source-by-source fact accumulation.

3. **Cellcog corpus reuse: YES, but only as selective enrichment — never a bulk swap.** Fable *tested* the naive swap (champion composer over 838 cellcog cards) → **0.3671**, drop rate rose to 53%. Cause: cellcog spans are ~500 chars vs champion's ~4,539-char quotes, starving the span-window matcher. Both reviewers: enrich uncovered slots only, widen quotes, resolve DOIs to full-text mirrors, dedup by work.

4. **The pitch page has real, attackable red flags** (see §7). Both independently flagged the same top ones: "84 citations" framing, "quality is a tight band," self-hosting vs OpenRouter reality, and 0.4447 reproducibility.

---

## 2. Where they diverge — and my adjudication (this is the critical decision)

**The Insight fix. Two proposals:**

- **Fable — "two-lane prose":** permit *uncited* analytic sentences (that introduce no new numbers/entities), enforced by a deterministic checker. Rationale: FACT only extracts statement-URL pairs, so uncited interpretation never enters the 90.3% denominator.
- **Sol — "verified relational synthesis":** do *not* allow uncited claim sentences. Instead build verified comparison **bundles** so relational/synthesis claims are themselves citable and pass `strict_verify`. Sol explicitly warns that enabling any unverified claim lane "would violate the sacred faithfulness constraint and is NOT a valid fix."

**FINAL RULING (operator, 2026-07-16): FAITHFULNESS IS FROZEN. Do not touch it — at all.**

- **Absolute constraint.** No change to `strict_verify`, no change to the drop rule, no new verification pass, no new test, no re-verification of rewrites. The 90.3% is produced by exactly today's code and stays that way. Any earlier proposal in this document that touches the gate, the drop rule, or adds verification is **RETRACTED.**
- **Why.** Cellcog collapsed because it kept fiddling with the verification layer. Every touch there risks a sudden, unexplainable score drop. That risk is unacceptable. So we do not go near it.
- **The consequence for Insight.** We do **NOT** raise Insight by relaxing citations or adding an uncited-prose lane (that would touch the gate). We raise Insight, Comprehensiveness, and Instruction-Following **entirely upstream of the verifier** — by controlling *what evidence enters* and *how sections are planned and allocated*. The writer and the gate keep running exactly as today; they simply receive richer, better-organized, rule-compliant input.
- **Both reviewers' good structural ideas are kept ONLY in their upstream form:** better evidence allocation to starved sections, comparison-ready evidence bundles that *feed* the existing writer, required-section coverage. None of these touch verification.
- **The clean separation (this is what makes it safe):**
  - **Faithfulness** = the END of the pipeline (post-writing citation check). → **FROZEN.**
  - **Instruction-following** = the FRONT/MIDDLE (rule reading, source eligibility, section planning). → **the entire focus of this plan.**
  - They do not overlap. We change *what goes in*, never *how it is checked*.

---

## 3. The plan — five pillars, ordered by leverage

### PILLAR 1 — Instruction-Following Compiler + Source-Eligibility Gate  ⟵ #1 (operator + Sol)
**Targets:** Instruction-Following (0.25 weight), Comprehensiveness. **Faithfulness risk:** LOW — likely *decreases* risk (ineligible sources withheld from cited prose). **Effort:** M.

**Why it's #1:** Task 72 buries a hard constraint — *"only cites high-quality, English-language journal articles"* — worth ~0.25 of the IF dimension (0.15 journal-only + 0.10 English-only) ≈ **6% of total RACE**. Our unscoped run cited **Wikipedia, Morgan Stanley, WEF, OECD/ILO/IMF reports, NBER/IZA working papers, personal sites** — ~60%+ of 37 cited URLs are non-journal. And RACE has 100 tasks, each with different, unpredictable embedded constraints; a Telus customer's prompt is unknowable in advance. **The fix must be general, not a task-72 filter.**

**Existing plumbing to exploit (verified):** `generate_multi_section_report` already accepts `deliverable_spec` and `scope_spec` (both default `None` → byte-identical OFF path), already has `OUTLINE_SYSTEM_PROMPT_REQUIRED` + a required-sections conform-remap. **The driver `compose_agentic_report_s3gear329.py:main` (call site line 249) simply doesn't pass them.**

**Build — a four-stage compiler (general, prompt-agnostic):**
1. **EXTRACT.** An LLM pass, adversarially prompted ("find every constraint, especially ones buried mid-sentence or phrased as a soft aside"), emits a **typed constraint set**: source-type, recency/date-cutoff, language, format/structure, length, required-coverage slots, exclusions/prohibitions, entity include/exclude, tone. Task-72's journal-only rule is one row it must catch on *any* prompt.
2. **ROUTE & ENFORCE.** Bind each constraint to the stage that can enforce it:
   - source-type / language → **retrieval queries + a corpus-entry eligibility gate**. Eligibility is a *positive proof* (journal version verified, English, on-topic, documented quality rule), not an inferred tier. Ineligible sources stay in retrieval telemetry / gap detection but **never enter the writer's cited menu**.
   - **recency → soft preference, not a hard filter (operator ruling).** We do **not** cut off by date unless the prompt explicitly demands it — we never invent a constraint the user didn't ask for. Instead we **bias retrieval and ranking toward fresher sources** (recency as a ranking boost). A hard date filter is applied ONLY when the extractor finds an explicit cutoff in the prompt.
   - required-coverage / industries / heterogeneity → `deliverable_spec.required_sections` (theory, empirical designs, heterogeneity, conflicts, sector cases, implications, limitations) layered with task-specific facets.
   - format / length / exclusions → outline + writer + assembly.
3. **AUDIT.** A final compliance pass checks the rendered report against *each* extracted constraint (pass/fail with evidence): every facet supported or **disclosed as a gap**; every reference passes the source contract; no empty URL.
4. **REPAIR.** Violations loop back (re-retrieve journal-only, cut an off-topic digression). No new faithfulness pass is added — repaired content flows through the **single existing** gate like everything else.

**Note:** the AUDIT/REPAIR here checks *instruction compliance* (did we obey the prompt's rules), which is a different thing from faithfulness. It adds no verification of citations.

**Reuse (don't rebuild):** the flywheel/cellcog pipeline already has `ResearchContract`, a Rank12 **source-eligibility firewall** ("tier compliance 43.3%→72.8%"), `gate_eligibility(row, policy)`, source-type classification, `recency_binding`. These are prototypes to port into the champion — but the *general extractor* (stage 1) is the piece that does not yet exist and must be built.

**Guardrail:** if a required slot has no eligible evidence, the report **says so** — never keep a non-compliant citation, never fabricate, never silently shrink scope.

---

### PILLAR 2 — Feed the starved sections (Insight, via upstream evidence only)
**Targets:** Insight (0.32 weight — biggest lever), Comprehensiveness. **Touches faithfulness?** NO — this is pure evidence allocation *before* the writer. The writer and gate run exactly as today. **Effort:** M–L.

**The problem it fixes:** the synthesis / policy / conclusion sections got only 3 evidence items each, so the writer had almost nothing to make cited claims about. Insight was starved of *input*, not blocked at the gate.

**Build (all upstream of the verifier):**
1. Convert eligible evidence into **comparison-ready records**: work, outcome, unit, population, industry, period/horizon, method/design, direction, magnitude, limitations.
2. Build **bundles** where a common outcome exists (which studies measure the same thing, and whether their numbers are comparable). Prototype: flywheel `argument_planner.py:find_bundles` — reuse the *selection logic* only.
3. **Give the synthesis and conclusion sections real evidence to work with** — a guaranteed floor of well-matched bundles instead of 3 loose rows — so the existing writer can produce *cited* comparative claims that survive the *unchanged* gate.
4. **Faithfulness untouched:** we do NOT add uncited synthesis prose, we do NOT re-verify, we do NOT touch the drop rule. Insight rises because the writer finally has organized, citable material — not because we relaxed anything.

**Acceptance:** the synthesis/conclusion sections carry real cross-study comparisons (all cited, all through today's gate); FACT accuracy and volume unchanged.

---

### PILLAR 3 — Presentation-only flow cleanup (DEFERRED / optional)
**Targets:** Readability (0.14). **Touches faithfulness?** This one sits closest to the verifier, so it is **DEFERRED** and kept strictly presentation-only. **Effort:** M.

- **Why deferred:** the original "recompose after verify + re-verify" idea touched the faithfulness layer and is **cut** per the frozen ruling.
- **What is allowed (safe, presentation-only, runs AFTER the gate on already-verified text):** reorder the surviving verified sentences for flow, and drop pure non-claim connective words that dangle (e.g. a leading "However," left behind by a deletion). No sentence is sent back through the verifier; no new claim is written.
- **Behavioral check (lint, not verification):** flag a section that opens mid-thought or has a dangling "however" — for a human/writer to smooth at the presentation layer only.
- If even this feels too close to the gate, we skip Pillar 3 entirely and rely on Pillar 4's rendering rules. Readability is only 14% weight; not worth any faithfulness risk.

---

### PILLAR 4 — Answer-First Rendering + Mechanical Polish  ⟵ cheapest points on the board
**Targets:** Readability (very high), IF/Comp. **Faithfulness risk:** near-zero. **Effort:** S–M.

**Build:**
- Replace the "one paragraph body" contract with discourse roles: **TL;DR / key findings** (generated *after* verification from the same verified claim objects), answer-first topic sentence, short multi-paragraph sections, method notes, a **verified industry comparison table** (built deterministically from verified fields — never ask a model to restate numbers), consensus/disagreement/gaps conclusion.
- **Mechanical fixes (do first — <1 day, zero risk):** wire `citation_truncation_normalizer` into the render path (kills `].[`); **dedup bibliography by work identity/DOI** (`same_work_groups` — removes the 4× Acemoglu–Restrepo repetition); fix/drop the **empty URL at reference 13**; strip "(tier …)" from references; rewrite the telemetry-speak Limitations section in reader language.
- **Free measurement:** `champion_report_with_tables.md` was built Jul 15 but **never scored** — score it 3× before anything else.

---

### PILLAR 5 — Selective Cellcog Enrichment  ⟵ last, and only after Pillars 1–2 exist
**Targets:** Comprehensiveness, Insight. **Faithfulness risk:** MEDIUM as raw import; LOW after re-acquisition + eligibility + span verification. **Effort:** M–L.

**Verdict:** worth doing, but **only as a provenance-backed acquisition/index layer**, never a bulk adapt. The naive swap already scored 0.3671.

**Why the current adapter is unsafe (Sol):** `adapt_cards_to_champion.py` substitutes author/year for the paper **title that exists in the provenance graph** (breaks the title-dependent outline digest); replaces the verified full-text locator with a **DOI landing URL** (turns locally-verified support into a FACT "unknown"); assigns tiers by venue-substring; treats one card as one independent source; drops the method/design/effect/uncertainty metadata that would create insight. Only 120 of 838 cards have a complete comparison tuple; the pool contains off-topic material (student anxiety, bank performance).

**Recommended reuse path:**
1. Join each candidate card to `provenance_graph.json`; recover real title, full-text locator, work identity, byte binding. Reject cards whose binding no longer verifies.
2. Apply the Pillar-1 task contract (English, high-quality journal, labor relevance, fills a required slot). Rejected cards become retrieval leads / gap telemetry, not citable evidence.
3. **Re-materialize each card's quote as a wide window** around its stored `span_start/span_end` offsets (fixes the ~500-char starvation that caused the 53% drop rate).
4. Merge at **work + finding level** (three cards from one DOI ≠ three sources); carry structured fields into a comparison store (feeds Pillar 2).
5. Add candidates **only to uncovered outline slots or valid comparison bundles** — never an all-card residual section (route-all is empirically −0.02 to −0.09).
6. Run the unchanged champion writer + `strict_verify` + work-level bib dedup + external FACT smoke. Success = coverage/insight rises **and** FACT accuracy/volume does not regress.

Corpora are nearly disjoint (≤38 of cellcog's 285 DOI works overlap our corpus), so genuine breadth is available.

---

## 4. Sequencing — LOCKED (operator, 2026-07-16). Do not reorder.

Every round runs the **current writer and current faithfulness gate, untouched**. Nothing here touches verification.

- **Round 1 — Coverage & Rules:** Pillar 1 (rule reader + source gate) + the planning half of Pillar 2 (build comparison bundles). Then run the current writer and measure. Plus the free Pillar 4 clean-ups.
- **Round 2 — Thinking & Flow:** Pillar 2 synthesis writer (fed by bundles, cited, through today's gate) + Pillar 3 rebuild (presentation-only flow cleanup).
- **Round 3 — Looks:** Pillar 4 rendering + table.
- **Round 4 — More evidence:** Pillar 5, only after the above works (and only if FACT holds).

**Rationale for order:** honors COVERAGE > INSIGHT > READABILITY; coverage must be **contract-directed, not count-directed** (route-all failed at −0.02 to −0.09); and evidence enrichment comes last so it doesn't feed a still-broken structure.

---

## 5. Measurement protocol (mandatory — the operator demanded rigor)

- Single-report rescore sd ≈ **0.002–0.007**; reproducibility band **±0.016**. **Score every change 3× (min).** A change must clear its own noise band, not a single lucky draw.
- **0.4447 is a judge-variance high** that did not reproduce (re-score mean ≈ 0.4272, max 0.4322). Track the *mean of 3–4 draws*, not the peak, as the real level.
- After every change: **re-run the external FACT harness.** Any drop below 90.3% accuracy or 84 supported instances reverts the change. Faithfulness is a gate, not a target to trade.
- Keep changes **behind default-OFF flags** where the codebase already uses that pattern (byte-identical OFF path), so each is independently reversible and A/B-able.

---

## 6. Faithfulness firewall (the lines we do not cross)

1. **The verifier is frozen.** `strict_verify`, its thresholds, and the drop rule are byte-for-byte unchanged. We do not edit, wrap, re-run, or add a pass to any of it.
2. **No new verification anywhere.** No "re-verify the rewrite," no second pass, no new faithfulness test. One gate, once, exactly as today.
3. **The unverified `analyst_synthesis` layer stays OFF** — we do not turn it on.
4. **All quality work is upstream of the gate** (source eligibility, evidence allocation, section planning) or downstream presentation-only (rendering). Neither touches how citations are checked.
5. **Ineligible sources never enter the cited menu**; missing evidence is disclosed as a gap, never padded or fabricated.
6. **FACT is a tripwire, not a dial:** after every change, re-run the external FACT harness; any drop below 90.3% accuracy or 84 supported instances reverts the change.

---

## 7. Parallel track — pitch-page corrections (from both reviewers' red flags)

Not part of the pipeline build, but must be fixed before the page is shared again:

| Claim on page | Correction |
|---|---|
| "84 verified citations" framed as 84 **sources** | 84 supported citation-*instances* of 93 with a known verdict, across **37 cited URL groups** (110 instances; 84 supported, 9 unsupported, 17 unknown). |
| "Quality is a tight band — everyone within a few points" | Fable leads by **0.0618 overall, 0.0838 on Insight** — a material product gap, ~4× our reproducibility band. Reads as spin. |
| "Leads on citation trust" | Grok's *accuracy* is higher (90.9% vs 90.3%); our real edge is accuracy **×** volume. State it explicitly. |
| "Self-hosted / zero data egress / ~$1–2 per report" | The benchmarked run used **OpenRouter-hosted GLM-5.2 + DeepSeek V4 Pro** and external retrieval. Self-hosting is a *license* property, not this measured run. Cost figure not auditable from telemetry. |
| "MIT-licensed model" (singular) | Name every runtime component (GLM-5.2 agent/generator, DeepSeek V4 Pro code-model, evaluator calls) and its license. |
| 0.4447 "reproducible" | Report observed 0.4447 **and** re-score mean 0.4272 / max 0.4322 across 4 draws. |
| Appendix = "complete output that produced the score" with 4 tables | The scored artifact has **no tables**; the appendix is an edited presentation. Label it as such; attach the exact scored artifact separately. |
| Bibliography defects | Reference 13 blank; 4 URL variants of one Acemoglu–Restrepo work. Fix before anyone checks. |
| "425 evidence items … verified" funnel | Units are inconsistent (997 initial rows / 1,104 after agent fetch / 37 final URL groups / 110 FACT instances). Define each unit precisely and keep one canonical set. |

---

## 8. Decisions — RESOLVED by operator (2026-07-16)

1. **Recency / cutoff → RESOLVED.** No hard date cutoff unless the prompt explicitly asks for one (never invent a constraint). Do **prefer fresher sources** via a retrieval/ranking bias.
2. **Round 1 scope → RESOLVED.** Bundle the comparison-planner *with* Pillar 1 in Round 1.
3. **Faithfulness → RESOLVED (frozen).** Do not touch the verifier at all. Insight is raised upstream only; no uncited-prose lane, no drop-rule change, no re-verification. §2's earlier adjudication is superseded by this freeze.

**Remaining before launch:** operator says "go" → Opus launches the Round 1 build as a workflow; main session monitors only.
