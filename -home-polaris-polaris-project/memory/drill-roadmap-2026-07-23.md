---
name: drill-roadmap-2026-07-23
description: "3-model drill (Sol max + Fable; K3 pending outage) roadmap to push the pre-gen pipeline past champion; readability/insight/comp levers + hardcode audit"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-23 — pre-generation redesign WORKS: new config (scope contract + clean prompt) draw-1 = 0.5062 vs 0.5084 champion, every dim up (Comp .5195, Insight .5149, IF .4985, Read .4702). See [[flat-result-diagnosis-2026-07-22]], [[no-post-generation-fix-rule]].**

**HONEST CAVEATS (Sol+Fable drill):** (1) the 0.5062 is ONE draw, inside noise (~0.02); measure 3x on real kimi-k3. (2) journal-only barely enforced — report still cites MIT Sloan news/IBM newsroom because scope_contract.py:143-147 only runs the non-journal check when extracted source_types ⊆ journal set, but extractor produced `["journal_article","high-quality"]` and the extra quality descriptor DISABLED it; plus UNKNOWN fails open. (3) "faithfulness PASS" was NOT a real faith test (strict_verify OFF); rerun candidate with locked engine. (4) the winning run used the CLINICAL section template (research_plan never passed → use_field_agnostic=False) AND run_raw_a.sh overrides PG_ANTI_VERBOSITY=on (so my env=0 didn't take).

**BUILD ROADMAP (build ALL, remove old incentives as you add new, then measure 3x — Sol+Fable consensus):**

BATCH 1 (readability, pure pre-gen prompt/assembly — IN PROGRESS): kill sentence/citation COUNT targets ("Target 10-18 sentences", "50-200 citations") that CAUSE cramming+monolithic paragraphs; enable REAL paragraph breaks (fix the " ".join flattening on strict-verify-OFF path — biggest readability defect: sections are ONE 600-990-word paragraph); KILL the residual "Additional Corroborated Findings" catch-all dump (943w after conclusion; verified_compose.py:3768-3781/3887-4008) — conclusion LAST, no catch-all; READER-register limitations+preamble (kill "T1/telemetry/span-grounded" in prose; reader variants exist at 3549-3598); ANTI-ECHO rule (report parrots "cross-context comparative unit", "condition" 13x); scholarly attribution (not "one review"); non-formulaic transitions; synthesis 4-move contract (converge/conflict/mechanism/boundary).

BATCH 2 (journal-only bug + overfit cleanup): fix the "high-quality defeats journal check" + UNKNOWN-fail-open under exclusive constraint (separate doc-type from quality; resolve metadata; UNKNOWN can't enter citable pool under exclusive term); generalize the CLINICAL template (3613-3754) — PORT claim-frame/authority/primary-over-derivative rules in PLACEHOLDER form, delete tirzepatide/HbA1c/FDA/KwikPen/N=1879 AND workforce literals (75.5%/PWBM/Goldman); field-agnostic facet prompt also has labor examples (1622-1647); scope_contract.py:358 clinical=True hardcoded; coverage_obligations round-robin+literal-audit+English-only regexes → semantic; _smart_titlecase rename; DOI-registrant over-veto of IEEE/ACM journals.

BATCH 3 (heavy Insight/Comp levers): contradiction/counter-evidence MINING — plain generator-model judge (NOT the banned NLI/entailment substrate — semantic_conflict_detector.py rides PG_ENTAILMENT_MODEL, do NOT wire), thread real conflicts into owning sections; CONTRACT-BOUND DEEPENING to the ACTUAL task RQ (corpus was built for a DIFFERENT narrower RQ = why 50% off-topic; deepen_scope_contract built + live_retriever + SERPER key present; but gap-retrieval currently runs UNSCOPED — every fold-in must re-pass the full contract + canonical-work dedup; stop on new-proposition novelty NOT magic count); relation-aware evidence packs (proposition + supporting + contradicting + design/context/observed-vs-modeled); give synthesis section a GLOBAL relation map (got only 9 evidence IDs vs intro 65, residual 138); semantic obligation binding.

**DISCIPLINE:** all pre-generation (retrieval scope OR compose prompt), smart/semantic not hardcoded, general/no-overfit, no adjective. Smoke-verify paragraph breaks survive. kimi-k3 had an OpenRouter provider outage 2026-07-23 (~1h+, NoEndpointError) blocking the 3-draw measurement + K3 drill — re-run when recovered. GitHub: fix/race-batch1-evidence-substrate @ ba55b96d (Step 2 committed).
