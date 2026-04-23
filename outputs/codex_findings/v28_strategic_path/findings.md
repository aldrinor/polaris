# V28 Strategic Path: Reaching 7/7 BEAT_BOTH

## 1. Achievability assessment

Yes, 7/7 BEAT_BOTH is achievable autonomously on the tirzepatide/T2D query, but not with the current retrieval-to-selection-to-generator shape. V28 proves POLARIS can beat ChatGPT DR and Gemini DR on dimensions where its architecture is genuinely different: per-sentence provenance, four-regulator jurisdictional breadth, machine-readable contradiction enumeration, and a strict verification culture. Those are structural advantages, not copywriting advantages. Competitors can describe caveats, but they do not expose sentence-level evidence IDs, source-tier mix, contradiction lists, or FDA/EMA/NICE/Health Canada distinctions with the same consistency.

The ceiling V28 hit is equally real. The four LOSE_BOTH dimensions are not independent failures. Citations, claim frames, structural depth, and narrative depth all failed because the report did not make the pivotal primary publications the spine of the answer. SURPASS-2 was cited through a T4 post-hoc instead of the Frías NEJM primary; SURPASS-4 Del Prato and SURPASS-CVOT Nicholls were in live_corpus but did not reach the final bibliography or prose; mechanism remained review-grade because primary clamp evidence did not become extracted narrative. Once the primary frame was missing, every downstream artifact became compensatory: trial tables were thin, per-trial summaries selected easier trials instead of the important ones, and mechanism prose grew longer without becoming more primary-evidence-dense.

This is not a human-curation ceiling. It is a pipeline-ordering problem. ChatGPT and Gemini appear to start from a curated pivotal-trial frame, then enrich around it. POLARIS retrieves broadly, selects by scorer, then tries to recover named-trial structure from whatever survived. That order is backwards for a clinical evidence review.

The strict_verify gate is both the reason POLARIS is credible and the reason cheap imitation of competitor prose fails. Competitors can quote or synthesize trial numbers from memory or inaccessible primary papers. POLARIS must match claims to fetched direct_quote text. For paywalled NEJM/Lancet primaries with thin fetched text, strict_verify blocks the exact numeric specificity that wins clinical dimensions. The answer is not to discard strict_verify globally. The answer is to make primary publication reachability and quote adequacy a first-class pipeline contract before generation begins.

## 2. Recommended strategy

Pick strategy beta, with alpha as the V29 entry point. The architectural path should be a two-stage evidence pipeline:

Stage 1: build an outline skeleton from pivotal primary publications only. For tirzepatide/T2D, reserve anchors for SURPASS-1, SURPASS-2, SURPASS-3, SURPASS-4, SURPASS-5, SURPASS-6, SURPASS-CVOT, and relevant SURMOUNT trials with population-scope labels. Each anchor needs the primary publication, design, N, population, comparator, endpoint, timepoint, primary effect estimates, uncertainty when available, and safety/caveat field. If a primary is in live_corpus but not selected, selection fails. If a primary is unreachable or quote-thin, refetch runs. If refetch still cannot support numeric extraction, the report says so explicitly instead of silently substituting post-hocs or reviews.

Stage 2: enrich the primary skeleton with meta-analyses, reviews, regulatory documents, labels, HTA guidance, and contradiction machinery. This preserves POLARIS's existing advantages while adopting the competitor-like primary-trial spine.

This beats alpha alone because A+B fixes "primary in live_corpus but not report," but does not force the answer to organize around pivotal publications. Alpha can lift Citations, Claim frames, and Structural depth to BEAT_ONE or partial BEAT_BOTH, but Narrative depth will remain vulnerable because mechanism and interpretation still depend on what the selector passes through.

I would not choose gamma as the main path. Relaxing strict_verify for narrative sections may help Gemini-style mechanism prose, but it attacks the wrong bottleneck and risks losing POLARIS's strongest brand: traceable claims. A narrower version is acceptable later: strict numeric verification for all numeric claims, with a separate "synthesis-only" mode for nonnumeric interpretation that still requires same-paragraph evidence support. That is a refinement, not the core roadmap.

Delta is useful only as a validation sidecar, not as a reason to pause. Running V28 on a non-clinical slug could tell us whether the primary-publication failure generalizes, but the tirzepatide evidence is already conclusive enough: primaries landed in live_corpus and were dropped. That is pipeline-wide enough to fix now.

Epsilon is premature. V28 is valuable as a transparent regulatory/contradiction artifact, but accepting complementarity now would strand POLARIS below its obvious achievable quality. The cheap path to 7/7 is not more prose polish; it is enforcing primary-publication custody through selection and generation.

## 3. Cycle count and risk

Expected path: 3 cycles.

V29 should implement alpha as the first architectural slice: selector-level primary hard reservation plus generator-side named-trial injection from live_corpus. This should recover SURPASS-4/CVOT and prevent post-hoc substitution for SURPASS-2 when a primary exists. Expected outcome: Citations, Claim frames, and Structural depth move from LOSE_BOTH to at least BEAT_ONE, with possible BEAT_BOTH if quote extraction is adequate. Risk: medium. If primary direct_quotes are too thin, the report may cite primaries without extracting the competitor-level ETDs.

V30 should implement the Stage 1 primary skeleton contract: anchor registry, quote-adequacy checks, refetch-on-thin-primary, and fail-loud behavior before normal evidence enrichment. Expected outcome: primary-trial dimensions become stable rather than cycle-variant. Risk: medium-high because it changes pipeline control flow, but it attacks the dominant root cause.

V31 should address mechanism and narrative: primary clamp/PK extraction first, then review-based synthesis second, with numeric strict_verify retained and nonnumeric synthesis clearly evidence-bounded. Expected outcome: Narrative depth can compete with Gemini without fabricating. Risk: medium because paywalled mechanism papers may still have thin text.

V32, if needed, is calibration: run a second slug, tune anchor registry generality, and prevent tirzepatide-specific hardcoding from masquerading as architecture.

## 4. Single most impactful next action

V29 should be Candidate A+B only, but framed as the first slice of beta, not as a narrow patch. Implement hard primary reservation in the selector and named-trial injection from live_corpus into section evidence pools. Add a gate that reports, per anchor, whether the primary was found, selected, injected, quote-adequate, and cited in prose. Do not spend V29 on table cosmetics, mechanism relaxation, or broad prompt rewrites. If SURPASS-4 and SURPASS-CVOT are already in live_corpus and still absent from the report after V29, the architecture is failing at the exact custody boundary that must be fixed before 7/7 is credible.
