# POLARIS Canonical Pipeline — single source of truth (anti-drift anchor)

**Status of this doc:** CANONICAL. Pinned in `docs/canonical_pin.txt`. Any change to the
POLARIS pipeline MUST update this file in the same PR, or it is drift (the failure that
produced the 4-role-drift incident, I-meta-001 #933). Codex review briefs reference this
file; the per-prompt standing-workflow hook points to it.

**Last verified against code:** 2026-05-29, by reading `scripts/run_honest_sweep_r3.py`,
`src/polaris_graph/retrieval/live_retriever.py`, `src/tools/access_bypass.py`,
`src/polaris_graph/generator/multi_section_generator.py`, the `src/polaris_graph/nodes/`
gates, and `config/architecture/polaris_runtime_lock.yaml`.

## Honest build state

- **Built and running today: 14 of 20 stages** — stages 1–13 + 18–20.
- **NOT built yet: 6 items** — stage 14 (Mirror), 15 (Sentinel), 16 (Judge), 17 (snowball
  memory), plus pause/resume (cross-cutting). The single old checker (Gemma) still occupies
  the "AI checking" slot until the 3 roles replace it.
- **THE SYSTEM IS NOT FULLY BUILT.** Do not claim or imply otherwise anywhere.

## Architecture DNA — WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP (operator-locked 2026-06-13, CLAUDE.md §-1.3)

The pipeline's design genome. Binding. See CLAUDE.md §-1.3 and `docs/pipeline_architecture_forensic_2026_06_13.md` (I-arch-001 #1245).

1. **WEIGHT, DON'T FILTER.** Every relevant source flows to composition carrying a credibility **weight**. Do not hard-drop a source to hit a number; social media stays at low weight. The tier classifier (T1–T7) + `authority_score` ARE the weighting system — surface them per-citation, never rank-then-drop. *(Forensic 2026-06-13: today weight is used only to rank-then-cut at the lexical relevance floor + a corpus-level advisory mean; it is NOT surfaced per-claim. Re-wire.)*
2. **CONSOLIDATE, DON'T DROP.** Group same-claim sources into a **basket**; keep ALL of them as multi-citation corroboration; cover qualitative claims, not numeric-only. *(Forensic: `finding_dedup` keeps ONE representative, DROPS corroborators, and is numeric-only — qualitative drb_72 claims get no consolidation. Re-wire.)*
3. **BASKET FAITHFULNESS.** Decide faithfulness against the whole basket of sources, never one span (single-source = blind spot); the verdict carries corroboration count + weights + agreement. STRENGTHENS faithfulness, never relaxes it.

**Only hard gate = the faithfulness engine** (strict_verify / NLI / 4-role D8 / provenance). Everything else is a weight or a consolidation. **BANNED:** hardcoded caps/targets/thinners/hard-filters to force a breadth number. **SURGICAL, not rewrite:** the machinery exists; re-wire semantics + delete the bolt-ons.

## The 20-stage pipeline

| # | Stage | Input | Output | Task | Tool | Status |
|---|---|---|---|---|---|---|
| 1 | Scope gate | question + domain | scope decision + protocol.json | decide if answerable, write run protocol | run_scope_gate + scope templates | built |
| 2 | Domain routing | question | domain tag (telemetry) | pick the domain profile | M-INT-5 template classifier | built |
| 3 | Web search | scope-approved queries | candidate sources (URLs, metadata) | find candidate sources | SERPER, Semantic Scholar, OpenAlex, Exa | built |
| 4 | Fetch + read | candidate URLs | clean full text per source | open each source, extract text | Crawl4AI, Jina, Firecrawl, trafilatura, PMC BioC, Unpaywall, ScienceDirect resolver, PyMuPDF | built |
| 5 | Tier grading | fetched sources | sources tagged T1–T7 | grade source quality | tier classifier | built |
| 6 | Adequacy gate | tiered corpus | proceed / expand / abort | enough good sources? | assess_corpus_adequacy | built |
| 7 | Completeness | corpus + topics | covered/uncovered, maybe re-search | every topic covered? | completeness_checker + expansion retrieval | built |
| 8 | Approval gate | corpus + operator note | approved / denied | reject rubber-stamped corpora | corpus_approval_gate | built |
| 9 | Contradiction check | selected evidence | numeric conflict flags | catch conflicting numbers | contradiction_detector | built |
| 10 | Evidence select | approved corpus | balanced evidence set | pick evidence to write from | tier-balanced selection | built |
| 11 | Write report | question + evidence | report, each sentence tagged to its source span | draft the answer | multi-section STORM generator + cross-trial synthesis, DeepSeek V4 Pro (Generator) | built |
| 12 | Strict-verify (Python) | sentences + evidence | passing sentences, bad ones dropped | check numbers, spans, word overlap, block injection | strict_verify | built |
| 13 | Fact dedup | verified sentences | deduped sentences | merge repeated facts | fact_dedup | built |
| 14 | Mirror check | claim + cited span | calibration verdict | is the claim really supported? | Cohere Command A+ (rented GPU) | NEW — not built |
| 15 | Sentinel check | claim + span + Mirror | grounded / ungrounded | hunt for hallucination | IBM Granite Guardian (rented GPU) | NEW — not built |
| 16 | Judge verdict | claim + span + Mirror + Sentinel | verified / partial / unsupported / fabricated / unreachable | final grade per claim | Qwen (rented GPU) | NEW — not built |
| 17 | Snowball memory | prior proven claims in, new verified claims out | graph nodes + cross-time contradiction flags | remember, catch old contradictions | self-hosted graph store | NEW — not built |
| 18 | Codex §-1.1 audit | report + claims + sources | line-by-line verdict + signed report | human-equivalent deep audit | Codex | built (manual) |
| 19 | Budget cap | running cost | hard stop if over | never overspend per run | budget tracker | built |
| 20 | Identity gate | captured model calls | pass / fail | prove the right 4 models ran | Path-B gate | built |

## Cross-cutting

- **Pause / resume:** today only cancel-at-stage-boundary works in the production runner.
  True pause-and-resume-from-any-stage is NOT built (GitHub #629). NEW.
- **Two-family rule:** generator and checker must be different model lineages (now extended
  N-way across the 4 roles via `validate_role_families`). Built.

## What changes from BEFORE to AFTER

- Stages 1–13 + 18–20: UNCHANGED. The whole research engine (search, fetch, read, write,
  Python-verify) stays exactly as built.
- Stage "AI checking": BEFORE = one model (Gemma) + rule checks. AFTER = three roles
  (Mirror → Sentinel → Judge). This is the only stage that changes.
- NEW: stage 17 snowball memory; cross-cutting pause/resume.

## Anti-drift

This file is the contract. The runtime lock (`config/architecture/polaris_runtime_lock.yaml`)
holds the 4 model roles; THIS file holds the full 20-stage pipeline. `verify_lock` checks the
roles; the weekly drift report checks for stale references. If code and this table disagree,
that is a drift halt — fix the code or fix this file in the same PR, never neither.
