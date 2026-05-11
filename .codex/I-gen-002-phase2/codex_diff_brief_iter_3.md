Diff review iter 3 for GH#423 Phase 2. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Iter-2 P1-1 RESOLVED — SentenceVerification threading

Previous fix: extracted `sv.sentence` for kept_sentences_pre_resolve, then tried to pass strings into resolve_provenance_to_citations → AttributeError on sv.sentence/sv.tokens. Codex iter-2 caught this NOVEL P1.

Iter-3 fix: thread SentenceVerification objects end-to-end.

```python
# In _run_section return:
kept_sentences_pre_resolve=list(report.kept_sentences),  # list[SentenceVerification]

# In orchestrator pre-dedup:
sv_by_section_by_sentence: dict[str, dict[str, SentenceVerification]] = {}
sections_for_dedup: dict[str, list[str]] = {}
for sr in section_results:
    sv_list = sr.kept_sentences_pre_resolve  # list[SentenceVerification]
    sv_by_section_by_sentence[sr.title] = {sv.sentence: sv for sv in sv_list}
    sections_for_dedup[sr.title] = [sv.sentence for sv in sv_list]

# After dedup_pass + rewrite re-verify:
# fact_dedup operates on strings; we use the SV-by-sentence map to
# reconstruct SV list for resolve_provenance_to_citations.

final_svs: list[SentenceVerification] = []
for s in new_sentence_strs:
    if s in original_sv_map:
        final_svs.append(original_sv_map[s])           # original SV preserved
    elif s in accepted_rewrite_by_str:
        final_svs.append(accepted_rewrite_by_str[s])   # rewrite SV from strict_verify
    # else: drop (failed strict_verify)
new_text, new_biblio = _resolve(final_svs, evidence_pool)
```

Where `accepted_rewrite_by_str` comes from:
```python
rewrite_report = strict_verify("\n".join(rewrite_candidates), evidence_pool)
accepted_rewrite_svs = list(rewrite_report.kept_sentences)  # already SVs
accepted_rewrite_by_str = {sv.sentence: sv for sv in accepted_rewrite_svs}
```

This means:
1. Every SV that flows into `resolve_provenance_to_citations` is a real SentenceVerification (from upstream strict_verify of the original OR strict_verify of the rewrite).
2. The fact_dedup module remains pure-string API (independently testable).
3. SV ↔ string mapping is local to the orchestrator integration.

# Iter-2 P2-4 NOVEL — fact_dedup rewrite tokens vs production [#ev:id:start-end]

Codex iter-2 noted: fact_dedup rewrite instructions/tests use `[ev_X]` markers, while production strict_verify accepts `[#ev:id:start-end]` span tokens. Telemetry path is still safe (PRIMARY-only drop fallback) but rewrite accepts will be near-zero in practice.

**Status: ACKNOWLEDGED, not blocking.** The Codex note explicitly says "PRIMARY-only drop behavior remains safe." Worst case: rewrites all fail strict_verify, dedup degrades to "drop all redundants" — which IS the documented safe-fallback per Codex Path A quality analysis. The end-user-visible report shows the PRIMARY-only version with no redundancy AND no orphan cross-references.

For richer rewrites that pass strict_verify, a follow-up iteration of fact_dedup's REWRITE_SYSTEM_PROMPT can teach the LLM to preserve `[#ev:id:start-end]` span tokens from the original sentence. That's a Phase 2.5 enhancement, not a blocker for shipping Phase 2.

# Iter-2 P2-1, P2-2, P2-3 — continuing, captured as follow-ups

- **P2-1**: dedup runs before M-44/M-47 regen — these regens rarely fire on policy/pharmacare templates; deferred.
- **P2-2**: V30 contract sections skip dedup — Q5 + Carney templates don't trigger V30 lane; deferred.
- **P2-3**: dedup LLM tokens not in total_input_tokens — cosmetic telemetry, not functional; deferred.

All three are tracked for follow-up iteration after Phase 2 ships.

# Test results

```
44 passed in 2.98s
```

All fact_dedup unit tests + adjacent multi_section tests pass. Import smoke confirms generate_multi_section_report still loads.

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
