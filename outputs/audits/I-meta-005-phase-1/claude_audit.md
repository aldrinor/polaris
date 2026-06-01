# Claude architect audit — I-meta-005 Phase 1 (research planner + archetype sections, #985)

## Scope
New `planning/research_planner.py` (field-agnostic ResearchFrame/ResearchPlan; 1 injected Writer call +
bounded retry; canonical-JSON SHA pin pre-retrieval), scope_gate additive frame extractor (KEEP _DRUG_NAME_RE),
scope_query_validator additive frame-token merge, multi_section_generator dual-path archetype model, sweep
on-mode wiring. All behind PG_USE_RESEARCH_PLANNER (default off), OFF byte-identical.

## Dual-review trajectory (Claude architect + Codex diff-gate)
- Build architect: CLEAN (off-byte-identity, field-agnostic, spend-free, archetype-routing verified by code-read).
- Codex diff-gate iter1: 4 P1 — (1) on-mode still ran load_scope_template + check_completeness + fed domain
  checklist labels to generation; (2) M-44 PRE-gen injection routed on clinical title; (3) planner Writer
  thread lost _RUN_COST_CTX (live spend invisible to budget cap); (4) on-mode base section prompt clinical.
- Fixes: (1) gated the whole M-28/M-35 + M-48 + DOI + R-6 (3 call sites incl. deepener re-check) behind
  `if not _use_research_planner:` + neutral CompletenessReport; (2) M-44 pre+post-gen route on archetype on-mode;
  (3) copy_context + explicit cost-delta write-back (copy_context alone is read-only for the float ContextVar);
  (4) SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC + pure selector at the _call_section format site.
- Codex diff-gate iter2: APPROVE (zero P0/P1). 1 P2 (atom-citation contract clinical examples) → follow-up issue.

## Verification
- Smoke P1-1..P1-21 (22) + generator regression (22) + 35 M-44 off-mode regression = all green, serialized.
- OFF byte-identity verified by code-read + regression (additive fields default ""/inert; only title-only
  projection serialized; no asdict of section dataclasses).
- Deviations accepted by Codex: (A) clinical.yaml advisory scaffold-only/unmapped (avoids misclassifying every
  empirical frame clinical); (B) production planner thread needs a live on-mode run before Gate-A.

## Verdict
APPROVE for merge. No live spend (deltas inert under off; on-mode is opt-in, operator-gated via Gate-A).
