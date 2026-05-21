# Codex scope consult — I-cd-706 SSE sub-task event threading (live pipeline)

Operator delegates design to Codex at highest quality. This threads emit_event into the LIVE pipeline-A driver (scripts/run_honest_sweep_r3.py, ~3000 lines, runs every real query on the deployed VM) — wrong placement could break a running pipeline or emit misleading progress.

## Verified current state
- v6 SIDE IS READY: `src/polaris_v6/queue/run_events.py` `_TRANSLATOR` already maps these pipeline-A event_types → v6 events:
  - scope_gate.completed → scope_decision
  - corpus_adequacy.completed → retrieval_progress {sources_found, tier_breakdown}
  - evidence.id_assigned → evidence_id {evidence_id, source_url}
  - strict_verify.section_completed → verifier_verdict {section, local_pass, global_pass}
  - generator.section_completed → section_complete {section, verified_sentences, dropped}
  - run.completed → run_complete
  `translate()` + `stream.py` SSE consumer + Redis replay all handle these. The CONSUMER side is done.
- PRODUCER GAP: scripts/run_honest_sweep_r3.py emits ONLY scope_gate.completed (line 1246) + terminal events (run.completed/aborted/failed at 1432/1575/1802/1894/2490/3084). It does NOT emit corpus_adequacy.completed, evidence.id_assigned, strict_verify.section_completed, generator.section_completed.
- Concrete boundaries found: corpus adequacy computed at line 1606 (`adequacy = assess_corpus_adequacy(...)`); scope at 1231/emit at 1246. Generator (multi_section_generator) + strict_verify imported at lines 51-56. evidence-id assignment + the generator/verify per-section loops are elsewhere in the file (not yet located).

## The design questions
1. For each of the 4 missing events, WHERE exactly should emit_event be called (which stage boundary), and what's the minimal payload matching the translator's transform_fn input keys (e.g. corpus_adequacy.completed needs {pool_size, tier_counts})?
2. emit_event is documented non-raising (best-effort). Confirm threading it into the live driver can't break a run even if Redis is down. Any ordering/perf concern emitting per-evidence-id (could be 100s of sources) or per-section?
3. Should evidence.id_assigned emit per-source (potentially 100s of events) or be throttled/batched? The translator maps it 1:1 to evidence_id events.
4. The Redis translator/replay test (Codex iter-1 P2 on the reprioritization): what should it cover — emit→translate→replay round-trip for each of the 4 new events?
5. Is there risk that adding these emits changes the pipeline's existing terminal-event sequencing or the run_store state machine?

Give a concrete implementation plan: the exact emit points (function/stage), payloads, throttling decision for evidence-ids, and the test plan. Highest-quality + live-pipeline-safety lens.
