Frame-driven is the right diagnosis, but your wording is still one layer too polite. The true root cause is not just "custody" and not just "retrieval variance." It is that POLARIS has no mandatory content model for clinical reports. The system treats pivotal trials as optional evidence rows competing inside a generic relevance market. That is why V29 did not move the scoreboard: you fixed transport of evidence inside a corpus-driven architecture, but you did not change the architecture that decides what must exist in the report.

The code path supports that reading. The outline planner explicitly says "if the evidence doesn't support a topic, don't include it." The section generator writes from an evidence subset, not from a required editorial frame. `strict_verify` then acts only on what was written. So the real failure is: no frame, no slot obligation, no bind between slot and source, and verification that is purely retrospective. In that design, primaries will always be fragile. Retrieval misses them, selection can displace them, and even when injected, the model can ignore them by writing around them. V29 proved that.

So yes: the non-band-aid fix is frame-first architecture. But I would define it more sharply than "frame-driven." The missing layer is a query-specific report contract:

1. Required entities: SURPASS-1..6, SURPASS-CVOT, SURMOUNT-2, mechanism primary, per-jurisdiction regulators.
2. Required fields per entity: N, population, comparator, endpoint, timepoint, effect size, uncertainty, study design, sponsor, limits.
3. Required rendering slots: one subsection or table row per entity, even if partially empty.
4. Required evidence binding: each slot is bound to one or more designated evidence rows before generation starts.

That changes the system from "retrieve then narrate" to "instantiate report schema then fill it." That is the correct architectural move.

On `strict_verify`: it is not the root cause, and I would not relax it. `strict_verify` is doing what it should do: refusing to bless claims that are not grounded in retrieved text. The problem is upstream. Today, if a frame element is not retrievable in machine-readable form, the element silently disappears because nothing in the pipeline reserves an empty slot and emits an explicit coverage failure. In a frame-first design, `strict_verify` remains strict, but the output contract changes from omission to explicit insufficiency: "SURPASS-2 primary publication not retrievable from accessible sources; subsection limited to metadata-level reporting." That is honest and structurally stable. The current architecture converts retrieval failure into content absence. That is the real bug.

On paywalls: yes, this is achievable autonomously up to a ceiling, but not to competitor parity in every clinical dimension. Highest-quality clinical synthesis does require reliable access to primary full text. If the clamp paper or a NEJM/Lancet primary is paywalled and POLARIS cannot legally fetch enough text to verify quantitative claims, then POLARIS cannot honestly match a system whose model already internalized those details or whose product has licensed access. You should stop pretending architecture alone erases that. Architecture can eliminate self-inflicted failure; it cannot conjure inaccessible evidence.

Cost estimate: your 10-15 day guess is credible for a production-quality first cut. I would budget 12-16 engineering days, not 5-7. Reason: the work is not just retrieval and prompt edits. You need schema design, deterministic DOI/PMID resolution, a frame compiler from query to report contract, planner changes, generator prompt changes, new validators that enforce slot completion rather than prose mention, explicit gap-reporting, and regression tests across at least one non-tirzepatide clinical topic so this does not become a drug-specific special case.

Would frame-driven get you to 7/7 BEAT_BOTH? No. It should materially lift Dims 1, 4, and 5, and likely recover some of 7. It is the correct path to get off the current 3/0/4 plateau. But 7/7 is still blocked by evidence access and by editorial synthesis quality. Narrative depth is not just "mention all trials." Gemini's clamp discussion is strong because it contains specific mechanistic quantitative detail. If the Thomas clamp paper is paywalled and POLARIS cannot retrieve enough verified text, then a frame-first pipeline can only produce an honest mechanistic gap statement plus whatever is extractable from abstracts/reviews. That may beat ChatGPT on honesty, but it may still lose on perceived richness.

So the actionable direction is:

1. Build frame-first for clinical, with deterministic DOI/PMID retrieval for known primaries and explicit unrecoverable-gap reporting.
2. Replace M-44-style soft injection with slot-bound generation and a validator keyed on slot completion, not on whether the LLM happened to name the trial.
3. Keep `strict_verify` intact.
4. Stop setting "ChatGPT-DR replacement on clinical" as the near-term product claim unless you also solve licensed-access coverage. Without that, POLARIS should be positioned as the transparent, auditable synthesis system, not the maximal-richness system.

The strongest non-band-aid alternative is hybrid, not another prompt trick: frame-first autonomous pipeline plus optional licensed/human evidence completion for inaccessible primaries. If you refuse human or licensed augmentation, accept the product truth. POLARIS can become best-in-class for transparent clinical synthesis under accessible evidence constraints. It cannot reliably be the richest clinical narrator against systems that benefit from inaccessible primary content.
