Diff review for GH#423 Phase 2 (fact_dedup wire-in). Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify P3/P2/cosmetic.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Lineage

Phase 1 (PR #425, merged at 5e85de14) shipped the fact_dedup module + 25/25 tests in isolation. This Phase 2 PR wires the module into the multi_section_generator.py production path per Codex's Path A recommendation (`.codex/I-gen-002/codex_path_quality_output.txt`, confidence 0.82).

# Test results

```
PYTHONPATH=src python -m pytest tests/polaris_graph/test_fact_dedup.py \
  tests/polaris_graph/test_section_prompt_gh422.py \
  tests/polaris_graph/test_multi_section_gap4.py \
  tests/polaris_graph/test_multi_section_limitations_r1.py \
  tests/polaris_graph/test_corpus_adequacy_r6_gap1.py
61 passed in 3.80s
```

# Diff scope

```
$ git diff --cached --stat -- src/
src/polaris_graph/generator/multi_section_generator.py | 84 ++++++++++++++++++++++
```

Single-file change (+84 lines, 0 deletions). Saved at `.codex/I-gen-002-phase2/codex_diff.patch`.

# Surgical changes (all opt-in / backwards-compatible)

## (1) `SectionResult` dataclass — new field (line ~93)

```python
# GH#423 I-gen-002: per-section verified sentences (pre-citation-resolution).
kept_sentences_pre_resolve: list[str] = field(default_factory=list)
```

Default empty list — backwards-compat with any caller that doesn't populate it.

## (2) `_run_section` return — populate the new field (line ~1258)

```python
return SectionResult(
    ...,
    # GH#423 I-gen-002: preserve pre-resolve sentence list for dedup.
    kept_sentences_pre_resolve=list(report.kept_sentences),
)
```

## (3) `MultiSectionResult` dataclass — new telemetry field (line ~166)

```python
# GH#423 I-gen-002: cross-section fact-dedup telemetry.
fact_dedup_telemetry: dict[str, Any] = field(default_factory=dict)
```

## (4) Orchestrator integration in `generate_multi_section_report` (between line 3521 section_results assembly and 3523 M-44 regen)

```python
# GH#423 I-gen-002: cross-section fact-dedup pass.
fact_dedup_telemetry: dict[str, Any] = {}
try:
    from .fact_dedup import dedup_pass as _fact_dedup_pass
    sections_for_dedup = {
        sr.title: list(sr.kept_sentences_pre_resolve)
        for sr in section_results
        if not sr.dropped_due_to_failure
    }
    if sum(len(v) for v in sections_for_dedup.values()) >= 2:
        # build llm_callable wrapping OpenRouterClient
        # call dedup_pass with section_order=[p.title for p in plans]
        # for each section whose sentences changed: re-resolve provenance,
        # update sr.verified_text, sr.biblio_slice, sr.sentences_verified
        ...
except Exception as exc:  # safe-degrade
    logger.warning("[multi_section] GH#423 fact_dedup pass failed (%s); continuing without dedup", exc)
    fact_dedup_telemetry = {"error": str(exc)}
```

Wrapped in try/except per Codex Path A safety design — if anything in the dedup pipeline fails, the production sweep continues with un-deduped sections (degraded UX but no data loss).

## (5) `MultiSectionResult` return — wire telemetry (line ~4138)

```python
fact_dedup_telemetry=fact_dedup_telemetry,
```

# Safety properties (per Codex Path A quality analysis)

- **Idempotent on no-duplicates**: if `sections_for_dedup` total < 2 sentences OR build_groups returns empty, dedup_pass returns sections unchanged.
- **Safe-degrade on LLM failure**: rewrite_redundant_sentences returns None for each redundant on JSON parse failure / count mismatch → apply_rewrites drops those sentences → final report keeps PRIMARY only.
- **strict_verify still policed**: rewrites re-flow through `resolve_provenance_to_citations` which preserves [ev_X] markers. Any rewrite that lost provenance is invisible to citation resolution (drops to biblio_slice mismatch).
- **No state mutation across reports**: dedup_pass is pure-function over the per-report section_results.
- **Exception-fenced**: top-level try/except catches any orchestration failure; production sweep proceeds with original sections + telemetry={"error": ...}.

# What this PR does NOT do (deferred to a follow-up)

- Integration regression test mocking the entire generate_multi_section_report (would require mocking 4 gather sites + strict_verify + resolve_provenance — out of scope for unit tests, belongs in E2E/smoke test).
- Live re-run of Q5 to measure 40% redundancy reduction (requires LLM API call; will happen post-merge as the natural next step in Codex's sequence step 3).
- Section-order parameter override (defaults to plan order, which is the standard outline order).

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
