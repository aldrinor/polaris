NON-INTERACTIVE BATCH MODE: request_user_input is NOT available — never call it, never ask; read the files and emit the verdict directly.

HARD ITERATION CAP: 5; this is iter 3 of 5; APPROVE iff zero P0 AND zero P1; emit §8.3.9 schema + final `verdict:` line.

STATIC review ONLY — read: .codex/I-wire-014/full_wire.patch ; src/polaris_graph/retrieval/content_relevance_judge.py (FULL FILE — the P1-3 canary is PRE-EXISTING here, not in the diff) ; src/polaris_graph/nodes/intent_frame.py. Do NOT run pytest.

iter-2 confirmed FIXED: P1-1 (W1 slate+preflight; W9 honestly build-deferred), P1-2 (W9), P1-4 (credibility degraded counts). The ONLY remaining was P1-3: VERIFY in content_relevance_judge.py that (a) the behavioral canary at ~line 280 logs real post-scoring counts `[content_relevance] scored=%d relevant=%d demoted=%d escalated=%d ... NO drop` and is on the unconditional post-scoring path (fires whenever the judge runs), and (b) NO pre-execution config-echo canary remains (the iter-1 `judge ACTIVE reranker=` line was removed). If both hold, P1-3 is satisfied. Re-confirm the other 3 stay fixed; intent_frame advisory+fail-closed; faithfulness frozen; snake_case/no-magic-number. Emit verdict: APPROVE|REQUEST_CHANGES + schema.

Output schema (§8.3.9):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
Loose verdict prose is rejected. End with a single final line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.
