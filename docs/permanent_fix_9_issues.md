# POLARIS Permanent Architecture Fix — THE 9 ISSUES (pinned, hard)

**Status:** ACTIVE program (operator-directed 2026-06-10). No band-aids. Each issue: research frontier best-practice → line-by-line study of OUR code → design permanent migration → build → SERIOUS stress smoke → Codex review with evidence → iterate-or-approve. After ALL 9 Codex-approved → serious preflight → present summary → operator go for the full beat-both run.

**Governing principle (the root reframe):** the pipeline today is built to **WITHHOLD when imperfect**. It must become: **ALWAYS RELEASE, with honest per-claim confidence + provenance, and let the user judge.** The ONLY hard line: never assert an *ungrounded* claim as fact — an unsupported claim ships as a transparent "no source found," never silently, and safety caveats are shown PROMINENTLY. This reframe is also the differentiator vs ChatGPT/Gemini (radical transparency, not a confident oracle).

**Process per issue (binding):**
1. Research how the latest frontier DR/RAG/faithfulness systems + best-practice literature handle it (WebSearch the current SOTA; cite sources).
2. Investigate OUR related code line-by-line (file:line); list every call site + consumer.
3. Design the permanent migration (best-practice → our code), stable + quality, not a patch.
4. Build it; wire to the MAIN pipeline with full function.
5. SERIOUS stress smoke (real adversarial test on real data — NOT a trivial pass-through).
6. Codex reviews everything with solid evidence → iterate or APPROVE (Codex is the only gate).

---

## I1 — Release-model reframe + the WHOLE gate stack
**Problem:** ~7 stacked gates can withhold/abort/thin a report: scope-reject, corpus-inadequate, corpus-approval-denied, per-section "≥40% verified or drop," four-role "≥70% or hold," S0 must-cover hold, "zero-verified → abort run." Any one kills or thins output even after deep research.
**Our code:** `src/polaris_graph/nodes/` (scope/adequacy/approval gates), `clinical_generator/strict_verify.py` (per-section floor), `roles/release_policy.py` + `roles/native_gate_b_inputs.py` + the four-role D8 seam (coverage 0.70, S0 must-cover), `generator/report_redactor.py`, manifest status `abort_*` (architecture.md §9.3).
**Research:** how do frontier DR systems (OpenAI/Google DR, Elicit, Consensus, Ai2 OLMoE/paper-QA, FacTool/RARR/SAFE) handle low-confidence — withhold vs label? Calibrated abstention vs transparent confidence.
**Permanent fix:** convert every gate from BLOCK → LABEL. No "held." Each claim/section carries a confidence + provenance; thresholds become DISPLAYED quality scores, not trap-doors. Keep abort ONLY for true zero-grounding (and even then render an honest "insufficient grounded evidence" report).

## I2 — Corpus-wide satisfaction (kill tunnel vision)
**Problem:** a requirement is checked against ONE bound source; if that exact source doesn't extract, it holds — even though the same fact sits in another URL we already fetched for a different query (the drb_76 contraindication was IN the corpus under a different source).
**Our code:** `roles/native_gate_b_inputs.py` (`_entity_canonical_match`, must-cover binding), `retrieval/frame_fetcher.py` (url_pattern bind), `retrieval/required_entity_retrieval.py`.
**Research:** evidence aggregation / multi-document grounding; how SOTA verifies a claim against a CORPUS not a single doc (cross-document NLI, claim→pooled-evidence retrieval).
**Permanent fix:** before declaring any requirement unmet, search the ENTIRE fetched evidence pool across all queries for satisfying content; bind to whatever genuinely supports it.

## I3 — Stop discarding the research (selection)
**Problem:** selector keeps ~46 of ~500 fetched sources (~90% thrown away before the writer sees them). The deep STORM research is wasted.
**Our code:** `generator/multi_section_generator.py` (evidence_selection), the rerank/dedup path, `evidence_selected` cap (#1078).
**Research:** retrieval→generation context scaling, long-context evidence packing, best-of-N evidence selection, rerankers (cross-encoder/ColBERT) at scale.
**Permanent fix:** scale selection with corpus size; feed BEST-ranked evidence (not first-N); raise/remove the fixed cap; quality rerank.

## I4 — Verification recovery + label-not-delete
**Problem:** the verifier wrongly drops real, checkable claims — mis-pointed citations (claim bound to abstract-intro / author-header / badge-URL), clinical qualifier-drop (#1176), general↔specific widening mis-judged (#1180), the span-window logic shaky BOTH ways (passes imprecise spans / rejects valid ones, gap-#18).
**Our code:** `generator/provenance_generator.py` (re-anchor, span-binding, `allow_local_window_fallback`), `clinical_generator/strict_verify.py`, `llm/entailment_judge.py`, span extraction (skip boilerplate).
**Research:** claim-grounding precision, attribution (RARR/ALCE/AttributedQA), span selection, NLI calibration; specific-vs-general entailment.
**Permanent fix:** re-anchor each citation to the genuinely-entailing span; skip boilerplate spans; when verification is imperfect, LABEL the claim (confidence + source), don't delete it.

## I5 — Per-claim confidence & provenance render + 4-role becomes a LABELER + credibility = weight not filter
**Problem:** the reframe forces a build: every claim must show answer + source(s) + confidence; the 4-role verifier must change job from gatekeeper to labeler; source credibility must WEIGHT + DISCLOSE, not silently FILTER (journal-only tunnel vision #1146/#1147).
**Our code:** `report_redactor.py`, `multi_section_generator.py` render, `key_findings.py`, the 4-role seam output, credibility modules (I-cred-*), web Proof-Replay UI.
**Research:** evidence-grounded UX (per-claim citations + confidence), calibrated confidence display, source-credibility weighting (not exclusion).
**Permanent fix:** per-claim confidence+provenance render in report + UI; 4-role emits per-claim labels; credibility weights + discloses.

## I6 — Kill the pending-rewrite loop + speed
**Problem:** when held, the pipeline re-generates to try to pass (d8_pending_rewrite) — the slow loop that made drb_90 take ~2h. The reframe makes it largely redundant.
**Our code:** the four-role rewrite path, `contract_section_runner.py`, the regenerate-on-hold logic.
**Research:** single-pass vs iterative-repair generation; where repair adds value vs churn.
**Permanent fix:** remove/simplify the rewrite-to-pass loop under always-release; keep at most one bounded repair; faster runs.

## I7 — Features that aren't delivering
**Problem:** (a) the quantified trade-off differentiator frequently no-ops (spec rejected / nothing returned, #1184); (b) hard publisher PDFs (NEJM/Lancet/AJCN viewers) fail extraction even with paid Zyte (#954) → lost authoritative sources.
**Our code:** `generator/quantified_analysis.py` + `run_honest_sweep_r3.py` `_q_spec_provider`; `tools/access_bypass.py` + PDF/table extraction (Docling/Surya/structured).
**Research:** structured quantitative extraction from papers; robust scholarly-PDF parsing (GROBID/Docling/Nougat/Surya), table extraction.
**Permanent fix:** harden the quantified-spec so it fires; add structured PDF/table extraction for hard publisher PDFs.

## I8 — Kill the cruft
**Problem:** "curator/operator will fix" wording (no curator, #1193), the lying "did not survive verification" stub, the Key-Findings over-claim ("verbatim span-verified" while carrying headers/stubs), noisy logs.
**Our code:** `multi_section_generator.py`, `contract_section_runner.py`, `report_redactor.py`, `key_findings.py`, `slot_fill.py`, `honest_sweep_integration.py` (human_gap_tasks), warning sites.
**Permanent fix:** factual self-contained gap wording; relabel internal artifacts (no human refs); fix the carry-up; quiet warnings.

## I9 — Proof & measurement tooling
**Problem:** we keep discovering bugs only on a paid run; no behavioral proof before spend; no repeatable completeness score; the audit-by-status habit hid the false hold.
**Our code:** new `tests/` behavioral replay harness on saved beatboth8 evidence; reuse `claim_audit_scorer` for completeness; §-1.1 content-audit discipline.
**Research:** offline replay/eval harnesses for RAG/DR; faithfulness + completeness metrics (RAGAS, FActScore, ALCE, RACE) that are honest (no metadata proxies).
**Permanent fix:** a serious behavioral stress smoke on real saved data (proves each fix before any run); a repeatable completeness scorer; audit content claim-by-claim, never status.

---

## The target (outcome, not a build item)
**Completeness vs ChatGPT** — provable only AFTER I1–I9 + one clean run. We already beat Gemini and never fabricate; the game is becoming complete enough to beat ChatGPT while staying faithful.

## Watches (monitor, not in the 9)
- Provider flakiness (mitigated by #1191 retries; permanent = robust multi-provider).
- Reasoning-first structured-output timeouts (retry-handled).
