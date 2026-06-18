# Apodix — The Landscape (deep / current / provable), 2026

*Dated 2026-06-18. An audit-grade analysis of deep-research engines and the verification layer around them, built from a 5-lane research workflow (8 agents, recency + honesty audited). Every quantitative claim is sourced to a primary 2025-2026 reference. No benchmark is claimed for Apodix's own gate; no "beats GPT/Gemini" claim is made — the competitor failure numbers are independently-measured findings about the FIELD.*

> **One correction applied to the raw research:** a research agent wrongly claimed "$1.6M is inflated; use AU$440K." Both Deloitte cases are real and independently verified: the **CA$1.6M Newfoundland & Labrador** health report (Fortune, Nov 2025 — the *Canadian* case, primary here) AND the separate **AU$440K Australian DEWR** report (refunded final installment, Oct 2025). The CA$1.6M figure is retained.

---

## 0. The one idea that organizes the whole map

A citation is a **directional** claim: *this span supports this sentence* (source ⊨ claim). Entailment has structure — A⊨B does not imply B⊨A. The unbreakable observation is simpler than any claim about embeddings: **no frontier deep-research engine runs a post-hoc, per-claim check that each generated sentence is actually entailed by the exact span it cites.** They retrieve, they generate, they attach the topically-nearest source — and they stop. "On-topic" is treated as "supported." That missing hop — not a weak model — is the field's structural defect.

Why even the best retrieval stack doesn't close it: retrieval ranks by **topical relevance, not directional entailment.** A bi-encoder scores cosine similarity, which is *symmetric* — sim(A,B)=sim(B,A) — so on its own it cannot tell "span entails claim" from "claim entails span"; a cross-encoder reranker *can* score a pair asymmetrically, but it is still trained for **relevance**, not for "does THIS span logically entail THIS generated sentence." Reranking sharpens topical match; it is not a per-claim entailment verdict. The 2026 paper *From Fluent to Verifiable: Claim-Level Auditability for Deep Research Agents* (defining **AAR = Auditable Autonomous Research**; arXiv 2602.13855) names the consequence — **citation decorrelation**, *"the systematic disconnect between cited papers and the claims they purport to support"* — and argues verification must be measured as whether cited sources *entail* attributed claims, not merely whether a citation resolves.

So the field substitutes **topical resemblance** for **logical support** — not from laziness, but because retrieval (even reranked) is a relevance engine, and *nothing downstream re-tests the claim against its span.* Every player below inherits this same blind spot; they differ only in surface and ambition.

**The field-wide footprint (independently measured):**
- **DeepTRACE** (arXiv 2509.04499): citation accuracy **40–80%** across GPT, Perplexity, Gemini, You.com, Copilot.
- **"Cited but Not Verified"** (arXiv 2605.06635, Onweller et al.): frontier engines keep **>94% live links** and **>80% topical relevance** but only **39–77% factual accuracy**.
- **CJR / Tow Center** (Mar 2025, 8 engines, 1,600 queries): Grok-3 wrong on **94%** of news-attribution queries; ChatGPT Search 67%; Perplexity 37%. *Grok-3-era, but the 2026 DeepTRACE/PwC numbers show the failure mode persists across model generations — a recurring property, not a stale snapshot.*

---

## 1. The three clusters

| Cluster | Competes on | How it "verifies" | The shared failure |
|---|---|---|---|
| **Frontier deep-research** | Breadth + autonomy | Self-attribution / none | Cites by topic; punts verification to the human |
| **Research deep-research** | Scholarly rigor + recall | Extraction / stance / relevance | Verifies the *wrong object* (extraction ≠ entailment) |
| **Vertical high-stakes** (clinical / legal) | Domain trust | Source whitelist / citation cross-reference | Fixes *fabricated/invalid sources* — not *cited-but-not-entailed* |
| **Verification / sovereign** | Trust + control | Independent check (partial) | Closest to right — but no single product closes all four legs |

---

## 2. FRONTIER — compete on breadth, verify by self-attribution

- **OpenAI Deep Research (GPT-5.2, Feb 2026).** One RL-trained model browses a tool loop over "several to dozens" of sites, synthesizes a report with model-emitted citations. *Verifies:* none — citation is a learned generation behavior, not a post-hoc check. *Four legs:* ~0/4 (closed-weight). (Moved off o3 onto GPT-5.2, Feb 2026.)
- **Gemini Deep Research (Gemini 3.1 Pro).** Plan → ~80 Google searches (~160 for Max) → grounds on what it gathered → report with a `citations` array. *Verifies:* none — docs tell the human to verify. *Four legs:* 0/4 (closed, Google-cloud).
- **Perplexity Sonar Deep Research.** RAG agent on the in-house **Sonar** family (Llama-3.3-70B-derived, retrained for factuality) — ~21 searches → ~27 cited sources. *Verifies:* citation presence only. Best-in-class but **37% news-attribution error** (CJR). *Four legs:* ~0.5/4. (Honest knock = cloud-SaaS + no independent per-claim check — NOT "runs on closed Opus"; Sonar is in-house.)
- **You.com ARI / ARI Enterprise.** Highest raw breadth — **400–500+ sources** in parallel (~10× typical). *Verifies:* none as an independent verifier; its 76% win-rate / 80% FRAMES are *preference/answer* wins, not faithfulness. *Four legs:* 0/4 (closed SaaS).
- **xAI Grok DeepSearch.** Iterative web + live-X loop (~10 steps), Heavy-mode debating agents. *Verifies:* **self-consistency only** (checks itself, not each claim vs its span). Worst in class — Grok-3 **94% wrong** on news-attribution (CJR). *Four legs:* 0/4.

---

## 3. RESEARCH — compete on rigor, verify the *wrong object*

- **Elicit.** Search ~125M-paper index → screen abstracts then full texts → read **full text**, extract structured columns → PRISMA-2020 log. *Verifies:* extraction-accuracy + per-row citation linkage (the extractor is the citer; no separate verifier of a composed sentence vs its span). *Honest number:* SAGE-2025 (Hilkenmeier et al.) measured Elicit at **81.4%** as a semi-automated second reviewer — competitive with humans (86.7%, not statistically significant) — but it measures *extraction agreement*, not entailment. Ships **(ii) full-content**; cloud SaaS on closed models.
- **Consensus.** Hybrid retrieval over **~220M papers** → "Consensus Meter" stance aggregation → snapshot with citations. *Verifies:* retrieval-grounding + stance counting, not entailment. Partial (ii); closed GPT-5, cloud.
- **FutureHouse (PaperQA2 / Robin).** Retrieve + rerank chunks + citation-graph → answer cites the specific retrieved passage; contradiction mode. *Verifies:* passage-grounded **relevance** (closest in this cluster to entailment, but relevance not deterministic span-entailment; same family reads+cites). Ships (ii) full-content + **(iv) open-source/self-hostable** — strongest research-cluster partial; lacks span-entailment + signed record. (Robin published in *Nature* 2026.)
- **Undermind.** Recursive keyword+semantic+citation-graph; LLM scores paper relevance until coverage saturates. *Verifies:* none at claim level — a discovery/recall engine (paper-to-query relevance), not sentence entailment. 0/4 as a verification product.
- **scite.ai.** ~38M full-text papers → classify each in-text citation supporting/contrasting/mentioning (~1.5B statements). *Verifies:* the **wrong object** — stance over the *published* citation graph, not a *generated* sentence vs its cited span. (92.6% of statements are uninformative "mentioning.")

---

## 3a. VERTICAL HIGH-STAKES — compete on domain trust, verify by whitelist / cross-reference

*The two best-funded professional verticals — clinical and legal — are exactly the high-stakes domains a sovereign buyer deploys into. Both have $B-scale leaders that solved the **fabricated-source** problem and still do not run a per-claim entailment-vs-span check. The missing hop is not an academic edge case; it is unclosed in the buyer's own domain.*

- **OpenEvidence (clinical) — compete on source trust, verify by whitelist.** A medical-only deep-research engine answering physician questions over a **whitelist of peer-reviewed journals** (NEJM, JAMA Network, 300+ titles — *no open web*), with clickable inline citations; Quick Consult / Deep Consult modes; ~**757k verified U.S. physicians and ~20M+ clinical consults/month** (early 2026), embedded in **Microsoft Dragon Copilot**. *Verifies:* by **source-whitelist + inline-citation linkage** — every citation is a real, named, high-quality article, which removes the *fabricated-source* failure but **not** the *cited-but-not-entailed* one. The writer is the citer; no independent post-hoc test that the generated sentence is entailed by the specific cited passage. *Four legs:* ~0.5/4 (closed-weight, cloud). **Squarely a regulated clinical domain** — which makes the missing entailment hop a live clinical-safety gap, not a theoretical one.
- **Harvey (legal) — compete on domain trust, verify by cross-reference + Shepardize.** Legal deep-research and drafting on GPT-class models + RAG over case law and filings; **citation cross-reference + confidence scoring**, integrated with **LexisNexis Shepard's** to flag overruled / negative-treatment authority; reports ~**0.2% internal hallucination** on its own evals yet still errs on niche or recent matters. ~**$8–11B** valuation (2026). *Verifies:* **citation validity** (does this authority exist, is it still good law) — adjacent to entailment but **not** "does THIS passage entail THIS drafted sentence." Independent-ish, but the object is the citation's *standing*, not the span's *support*. *Four legs:* ~0.5/4 (closed-weight, cloud).

---

## 4. VERIFICATION / SOVEREIGN — the cluster converging on the right problem (Apodix's cluster)

- **Primer.ai (RAG-V) — the closest competitor, ~3 of 4 legs.** Ingest corpus in-enclave → RAG draft with line-level citations → **RAG-V** independent fact-check stage (validates each statement against retrieved source material, corrects in real time) → air-gapped IL5/IL6. *Strongest leg in the field — a genuinely independent post-hoc check.* **But:** validates against the **source SET**, not the one **specific cited span**; an LLM-style fact-check with **no deterministic floor**; **no signed re-runnable record**; open-WEIGHT model not claimed. (RAG-V is a 2024-origin method being productized — maturing, not freshly invented.)
- **Cohere (Command A+ / North) — cleanest leg-4, ~1.5/4.** Command A+ emits `<co>…</co>` grounding markup linking each span to its source AS it writes; trained into the model; on-prem/air-gapped; **Apache-2.0** (218B MoE, May 2026). *Verifies:* **generator self-citation** at span level — but the writer is the citer; no independent re-test. (Merged with Aleph Alpha ~$20B, Apr 2026, under a Canada–Germany Sovereign Technology Alliance — directly relevant to the Canadian-sovereign frame.)
- **Vectara (HHEM-2.1-Open / FCS) — ~1/4.** A hallucination *detector*: (context, response) → a 0–1 Factual Consistency Score. *Verifies:* independent entailment-style score, but at the **response level** (a single fabricated clause can pass), and it outputs a *number*, not a per-claim drop/keep.
- **Contextual AI (Grounded Language Model) — ~2/4.** RAG → GLM cites as it writes → a separate **Groundedness Reward Model** reviews. *Verifies:* self-attribution PLUS a post-hoc checker (strongest non-Primer independence) — **but writer and checker are both Llama-based** (violates writer≠checker), groundedness not span-entailment, not deterministic. No signed record.
- **Factiverse — ~1/4.** Independent fact-checking API: detect claims → search **external** evidence → stance-classify. Per-claim and independent, but vs evidence it goes and finds — answers "is this true in the world?", not "does THIS span entail THIS sentence?"
- **Aleph Alpha (AtMan) / Mistral.** Attention-based relevance / run-level audit — *explainability and observability, not per-claim entailment.* Strong on sovereign + open-weight, **no verification leg** — the clearest evidence that **sovereignty is commoditizing**.

---

## 5. The systemic mechanism — why they ALL fail the same way

**The leak is at one hop: cite-by-topic.** (1) RETRIEVE — symmetric cosine returns topically-near spans (the entailing span may not rank top). (2) READ SNIPPET — chunking separates the qualifier that flips entailment ("in mice", "did not reach significance", "contraindicated") from the headline. (3) SYNTHESIZE — the model fills gaps from its parametric prior. (4) **CITE-BY-TOPIC — THE LEAK** — attach whichever retrieved source is topically closest. *Nothing in the loop ever asks "does THIS span entail THIS sentence, in this direction?"*

**Depth makes it worse — the death of "just call more tools."** "Cited but Not Verified" (arXiv 2605.06635) scaled tool calls 2→150: fact-check accuracy **drops ~42% on average** (GPT-5.4: 78.6% → 16.7%) while "Link Works and Relevant Content remain above 92% at all search depths." The two CHEAP signals are **symmetric** (Link-Works = HTTP-200 binary; Relevant-Content = cosine overlap) and stay pinned; the one EXPENSIVE signal (Fact-Check = does the span *entail* the claim?) is **asymmetric** and craters. Each hop multiplies the high-relevance candidate pool faster than a fixed synthesis budget can adjudicate entailment. **Structural property of binding-by-relevance, not a model deficit a bigger agent fixes.**

**Why a checker bolted on the end can't catch up.** AAR: *"Post-hoc verification does not scale because it cannot recover missing reasoning chains and it arrives too late to prevent error build-up."* → verification must run **per-claim, against the exact span, fronted by a deterministic floor.**

---

## 6. What the 2026 research prescribes — the field is converging on Apodix's stack

1. **Auditability is a governance primitive.** AAR: *"Auditability… is a governance primitive for scientific trust when discovery becomes autonomous."* It measures **Provenance Soundness** — "whether cited sources actually *entail* attributed claims, not merely whether citations resolve" — explicitly superseding response-level groundedness scores with per-claim-vs-span entailment.
2. **Deterministic-gate-the-judge.** "Deterministic Integrity Gates" (arXiv 2606.09500): a single-prompt LLM reviewer caught **11 of 27** seeded defects; **deterministic gates caught all 27, no false positives.** A confident hallucination is exactly what an LLM judge alone is *least* likely to catch — which is why a deterministic floor *under* the judge matters.
3. **A re-runnable signed record.** 2606.09500 carries "a content-hash manifest recording a **SHA-256** over every input and derived table," so a clean run "re-verifies its archived tables byte for byte." The differentiator is not "we sign things" but that **a third party can re-EXECUTE the claim→evidence_id→span→verdict chain WITHOUT trusting Apodix's servers.** Aligns with the **EU AI Act's Article 50** transparency regime (in force Aug 2 2026); cryptographic provenance is named among accepted AI-marking techniques in the accompanying Recital 134 and Commission guidance, not in the bare Article 50 text.

**The field's own 2026 literature independently specifies Apodix's exact stack** — claim-level entailment-vs-span, a deterministic gate fronting an independent judge, a hash-signed re-executable record — while rejecting the pre-2024 grandfather pattern (symmetric-cosine RAG + response-level groundedness + writer-self-citation).

---

## 7. Apodix's funnel vs theirs — three forks, one decisive

| Hop | Generic DR funnel | Apodix | Differ? |
|---|---|---|---|
| 1 Expand | question → sub-queries / plan | STORM expansion → outline | Same (table stakes) |
| 2 Retrieve | cosine returns topically-near | thousands of candidates, **recall-only** | Same |
| 3 Read | snippet / RAG chunk (partial) | **FULL-CONTENT fetch** | **FORK 1** — the verification substrate |
| 4 Consolidate | (none) | distill same-claim sources into a **per-CLAIM basket** (corroboration + weights + agreement/contradiction) | **FORK 2** — weight-and-consolidate |
| 5 Generate | fluent prose + attach-by-topic citation | prose + provenance tokens `[#ev:id:start-end]` (an *unverified assertion* the next hop tests) | Same self-cite step |
| 6 Verify | **none — citation presence is the signal** | **INDEPENDENT entailment of every sentence vs the EXACT cited span**: a DETERMINISTIC FLOOR first — strict_verify (span-bounds + numeric-subset + content-word overlap ≥2), re-executable — UNDER a different-family judge (writer deepseek-v4-pro ≠ checker glm-5.1/minimax-m2/qwen3.6) | **THE DECISIVE FORK** |
| 7 Output | unsupported claim ships wearing a live, on-topic, non-entailing link | **DROP or LABEL "could-not-verify" — never silently asserted** | **Differ** |
| 8 Abstract | (with the body) | drafted LAST from the verified body only | Minor |
| 9 Seal | (none) | **GPG-signed, offline-re-runnable per-claim record**, third-party **re-EXECUTABLE without trusting Apodix's servers** | **Differ — the cleanest sole-empty leg** |

**Where the gate sits that the others lack:** at hop 5→6. The generic funnel's hop 5 is "attach the topically-nearest citation" — an embedding-proximity decoration, never re-tested writer→checker. Apodix replaces that bind with a **deterministic floor (re-executable) UNDER a cross-family judge** — the pairing **no mapped competitor ships** (Primer = LLM-fact-check, no floor, vs source-set; Vectara = response-level score; Cohere/Contextual = same-family self-citation).

---

## 8. Why Apodix stands out — architecture, not a feature checklist

**The standout is architectural.** Every competitor *adds* verification to a pipeline that was designed to retrieve-and-generate: a confidence number (Vectara), a self-citation markup (Cohere), a fact-check against the source *set* (Primer), a Shepard's lookup (Harvey), a journal whitelist (OpenEvidence). Bolt-on verification inherits the pipeline's blind spot — it inspects the answer *after* the cite-by-topic binding that already leaked, and it has no exact span to test against. Apodix inverts the order: **the per-claim entailment test — each generated sentence against the EXACT cited span, a deterministic floor under a cross-family judge, then sealed into a re-executable record — IS the pipeline**, the hop everything else routes around. You cannot reach Apodix's output without every shipped sentence having passed it. A bolt-on can be removed and the product still runs; remove this and there is no product. That is a different architecture, not a better feature — which is why the four legs below land as one design rather than four add-ons.

| Leg | Apodix hop | Who else ships it |
|---|---|---|
| **(i) independent entailment vs the EXACT cited span (deterministic floor under a cross-family judge)** | Hop 6 | Primer (vs source-SET, no floor); Vectara (response-level); Contextual (same-family) — partials only |
| **(ii) full-content fetch as the substrate** | Hop 3 | Primer (closed corpus); Elicit / FutureHouse |
| **(iii) signed offline-re-EXECUTABLE per-claim record** ‡ | Hop 9 | **Documented-empty — no named player ships it** |
| **(iv) open-weight sovereign self-host (writer≠checker)** | Cross-cutting | Cohere, Mistral, Aleph, FutureHouse — commoditizing |

‡ **Honest maturity note on leg (iii):** for Apodix this leg is **architected and wired in the pilot, with the GPG signer + conformance tests in-tree** — the live-render wiring through the production deliverable is the pilot piece, *not yet a shipped GA feature* (see §9). The "documented-empty" column means **no competitor ships it either** — the open cell is real; Apodix's own claim to it is "pilot-wired, not GA," never "shipped."

Each leg is shipped by *someone* (except iii). No single product ships all four. **The claim is the combination, not four world-firsts — and the space is narrowing** (Primer ~3/4; sovereignty commoditizing). Never "the only sovereign one," never "no one verifies," never "beats GPT."

---

## 9. Honest engineering state (for technical due-diligence — sovereign-enterprise or government)

- **Hard half runs today (implemented + tested in-tree):** retrieve → full-content fetch → per-claim basket → deterministic strict_verify (span-bounds + numeric-subset "every decimal in the sentence appears in the cited span" + content-word overlap ≥2) → a different-family entailment judge → drop-or-label enforced *by* the gate.
- **Co-developed in the pilot:** the full end-to-end render, and especially **Hop 9** — the GPG-signed per-claim record wired all the way into the live deliverable. The signer + conformance tests **exist in-tree**, but the live-wiring through the production render is the pilot piece. **The one place not to over-claim maturity** — leg (iii) is architecturally ready, not fully shipped.
- **No benchmark is claimed for Apodix's own gate. No "beats GPT/Gemini."** The competitor failure numbers are independently-measured findings about the FIELD.

---

## 10. The Deloitte proof point — one illustration, not the argument

Two real, verified cases show what citation-decorrelation does to a real government report:
- **CA$1.6M — Newfoundland & Labrador (Canada, the primary case here).** Deloitte's just-under-CA$1.6M, 526-page health-workforce report carried AI-fabricated citations — nonexistent papers, real researchers credited on work they never wrote (Fortune, Nov 2025). *Provincial, not federal — state it plainly.*
- **AU$440K — Australia (the corroborating second instance).** Deloitte's AU$440,000 DEWR report was **partially refunded (the final installment)** in Oct 2025 after fabricated citations and a made-up Federal Court quote (*Amato v Commonwealth*) survived to delivery.

Both are **one vivid instance each of the field-wide failure mode** mapped above — a topically-relevant citation that did not actually support its claim, in exactly the cite-by-topic hop where every engine leaks. When the stakes are clinical, legal, or regulatory, that leak is not a quality nuisance; it is the liability the four-leg combination is built to remove.

---

### Primary sources
DeepTRACE (arXiv 2509.04499) · "Cited but Not Verified" (arXiv 2605.06635, Onweller et al.) · From Fluent to Verifiable / AAR (arXiv 2602.13855) · Deterministic Integrity Gates (arXiv 2606.09500) · GaussCSE asymmetric representations (arXiv 2305.12990) · CJR/Tow Center (Mar 2025) · Hilkenmeier et al. (SAGE 2025, Elicit) · vendor primary docs (OpenAI, Google, Perplexity/Sonar, You.com, xAI, Elicit, Consensus, FutureHouse/Nature 2026, scite.ai, Primer.ai, Cohere, Vectara, Contextual AI, Factiverse, Aleph Alpha, Mistral, OpenEvidence, Harvey) · EU AI Act Art 50 (Aug 2 2026) · Canada "AI for All" (Jun 4 2026) · Deloitte: Fortune (NL, Nov 2025) / CFO Dive / The Register (DEWR, Oct 2025).
