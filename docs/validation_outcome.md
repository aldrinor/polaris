# Validation Outcome — Zero-Cost Phase Completed

**Vector:** PG_LOOPBACK_MIN (query: "What are the proven health benefits and risks of intermittent fasting?")
**Run time:** 1815s (30 min wall), ~45 min operator serving time
**Cost:** $0 (loopback mode, Claude-as-LLM)
**Status:** Pipeline completed, final JSON written

---

## Gate results

| Phase | Gate | Criterion | Result | Status |
|---|---|---|---|---|
| P0 | G0a-e | Remediation integration test (5 assertions) | 5/5 pass | **PASS** — gap 3 closed |
| P5/P6 | G1 | Pipeline completed, final JSON written | status=complete | **PASS** |
| P5/P6 | G2 | `perspective_entropy` populated in final JSON | 0.844 (4 Scientific, 9 Methodological, 2 Regional) | **PASS** — FIX-ENTROPY verified in production |
| P5/P6 | G3 | `hallucination_audit` non-empty with real ratios | 5 entries, ratios 0.71-0.84, all `needs_rewrite=True` | **PASS** |
| P5/P6 | G4 | `[wiki-compose] Hallucination audit:` log line | Present in log | **PASS** |
| P5/P6 | G5 | `[polaris graph] FIX-ENTROPY:` log line | Present in log | **PASS** |
| P5/P6 | G6 | Bibliography "Unknown" authors < 30% | 6/6 = 100% | **FAIL — ship-blocker** |
| P5/P6 | G7 | Prose `[N]` citations resolve to bibliography | 5/5 unique cites resolve | **PASS** |
| P5/P6 | G8 | D3 URL diversity after canonicalization | 6/6 distinct | **PASS** |

**7/8 smoke-test gates + P0 gate PASS. G6 is the single ship-blocker.**

## What was validated

1. **FIX-ENTROPY works in production.** The Shannon entropy computation in `graph.py::_evaluate` populates `perspective_entropy` to 0.844 when evidence has real perspective diversity. This closes the "code present but never executed" concern.
2. **Hallucination detector + remediation loop works end-to-end.** The NLI detector flagged all 5 composed sections (avg 77.2% unsupported), triggered 5 remediation re-compose calls via `_compose_one_section(unsupported_spans=...)`, all 5 rewrites succeeded (log line `REMEDIATE: 5/5 flagged sections rewritten`). This matches the P0 integration-test result in a live pipeline context.
3. **FIX-HALLUC-1b anti-hallucination prompt is in `COMPOSE_SYSTEM`.** Every compose prompt contained the ABSOLUTE HALLUCINATION BAN block.
4. **Citation resolution holds.** Every `[N]` in the prose resolves to a real bibliography entry. No phantom citations.
5. **D3 URL canonicalization holds.** 6 bibliography entries, 6 distinct canonicalized URLs.
6. **Loopback infrastructure works.** Pending/responses/done file protocol, dispatcher Tier-A auto-serve with Pydantic-validated templates, Tier-B/C operator routing all functioned. `LoopbackLLMClient` is a true drop-in replacement for `OpenRouterClient` on the v1 graph.

## Real bugs surfaced during the run

1. **BUG-70 — Abstract composed BEFORE hallucination audit.** In `compose_from_wiki`, the abstract is generated immediately after section compose (line ~437) and the hallucination audit runs afterward (line ~556). If remediation rewrites a section, the abstract still reflects the pre-remediation fabricated text. Fix: move abstract generation to after the remediation loop.

2. **BUG — Bibliography authors always empty.** All 6 bibliography entries have `authors: []`. Root cause is upstream in `analyzer.py` — the atomic-fact extraction does not populate source-level authors into the bibliography dict. 100% ship-blocker.

3. **BUG — Safety evidence routing to wrong section.** Section 3 titled "Safety Signals and Population-Specific Contraindications" received only methodological-description claims from meta-analyses, not the safety-specific claims (pregnancy, lactation, sulfonylurea) that were generated in STORM interviews. Cluster-to-section assignment failed to route safety evidence to the safety section.

4. **BUG — Search-query shape drift from Tier A template.** Auto-generated `QueryPlan` template produced queries with domain-appropriate modifiers ("FDA EFSA regulatory guidance", "cost-effectiveness QALY") that caused Serper to return commercial-determinants-of-health and cost-effectiveness papers for round 1 instead of IF-specific content. Validates the advisor's "shape drift" concern: Tier A templates are Pydantic-valid but semantically less precise than a real LLM would produce. A live LLM would self-correct; the template did not. Round 2 (operator-served corrective `AgenticRoundAnalysis`) fixed the query drift and surfaced real IF content.

5. **BUG — Fetch robustness.** One page returned a captcha-block as "content" (sciencedirect.com, 1-2 sentences of bot-challenge text). Another page's content was truncated to intro only (nutritionj.biomedcentral.com PDF redirect failure). No stub-detection gate prevents these from being treated as real evidence.

6. **BUG — `analyses` vs `analyzer.py:177` prompt example.** The prompt example in the analyzer shows `"perspective": "Scientific"` hardcoded in the example JSON, which may bias the LLM toward Scientific perspective across all facts. Worth probing in the paid run whether production GLM-5.1 preserves STORM-assigned diversity.

## What remains unvalidated (requires paid GLM-5.1 run)

- Whether GLM-5.1 specifically complies with `FIX-HALLUC-1b` anti-fabrication prompt under production prose-generation pressure (gap 4 of advisor audit).
- Whether production GLM-5.1 output shape triggers code paths that the Tier A templates did not exercise (silent divergence concern).
- Whether the `perspective_entropy` stays >0.3 when the planner and analyzer are driven by real LLM output rather than template + operator.
- Real fabrication patterns the detector may miss (planted-known is not unknown-unknown).

## Recommended next step

Run one paid GLM-5.1 single-vector (Phase 7) with `PG_LOOPBACK_MODE=0` and same query. Budget cap $5. Gate checks P1-P5 from the plan. Before running, fix the bibliography author extraction (G6 ship-blocker) or the paid run will produce the same 100% "Unknown" output.

## Additional findings worth tracking

- The dispatcher's Tier A templates for `StormPersonaBatch`, `StormQuestion`, `StormAnswer` were all Pydantic-invalid (wrong field names). The validator correctly rejected them and routed to operator. **This is the Phase 2 safety-net working as designed.** For future smoke tests, update templates to match real schemas (one-time fix).
- Remediation rewrites successfully reduced flagged content — every rewritten section was significantly shorter and hugged literal quotes more tightly. This is the designed behavior.

## Artifacts

- `outputs/polaris_graph/PG_LOOPBACK_MIN.json` — full pipeline output
- `outputs/polaris_graph/PG_LOOPBACK_MIN_report.md` — final report markdown
- `logs/pg_loopback_minimal.log` — full pipeline log with FIX-ENTROPY and REMEDIATE lines
- `loopback/done/` — archived Tier B/C operator-served request/response pairs
- `loopback/shape_drift.jsonl` — Tier A auto-serve fingerprints (for later comparison vs GLM-5.1)
- `loopback/operator_queue.jsonl` — operator request queue log

## Cost summary

- Phase 0 (integration test): $0, 30 min
- Phase 1 (audit): $0, 30 min
- Phase 2 (dispatcher): $0, 1 hour
- Phase 5 (full-pipeline loopback): $0, 30 min wall + ~45 min operator time
- Phase 6 (audit): $0, 30 min

**Total $0 investment: ~3 hours operator time. Validated: gap 3 fully, code paths for gaps 2/4 demonstrated operational. Gap 6 (bibliography metadata) identified as ship-blocker.**

Remaining paid validation (Phase 7): $1-5, 60-120 min, same vector, gate P1-P5. Required for gap closure on GLM-5.1 prompt compliance.
