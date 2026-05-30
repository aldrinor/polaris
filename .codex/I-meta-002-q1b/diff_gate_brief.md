RULE NOW — emit the YAML verdict block FIRST, before any prose. The diff is SMALL and SELF-CONTAINED;
read the patch at `.codex/I-meta-002-q1b/codex_diff.patch` (or the 6 changed files) and rule. Do NOT
explore beyond these files.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
required_changes: [...]   # only if REQUEST_CHANGES
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — I-meta-002-q1b (#939): verifier reasoning separation + capture. Review the DIFF against the brief-gate-APPROVED plan. NO SPEND / NO NETWORK.

The brief (`.codex/I-meta-002-q1b/brief.md`) was APPROVE'd (`.codex/I-meta-002-q1b/codex_brief_verdict.txt`).
This diff implements Parts A-E verbatim. Review the patch for correctness against that plan + the
POLARIS red-team checklist.

## The diff (read `.codex/I-meta-002-q1b/codex_diff.patch`)
6 files, +265/-9 (production +104 incl. comments; tests +161):
- `src/polaris_graph/roles/role_transport.py` — `reasoning: str | None = None` on `RoleResponse` + `RoleCallRecord`.
- `src/polaris_graph/roles/openai_compatible_transport.py` — NEW `_separate_reasoning(content, model_repr)` (splits a LEADING `<think>…</think>`; raises on unterminated); `_parse_response` now returns 4-tuple `(raw_text, served_model, usage, reasoning)`: prefers a non-blank `reasoning_content` field (content = bare verdict), else splits inline `<think>`, else `reasoning=None`; post-split blank guard raises identically across BOTH paths; `complete()` passes `reasoning` to `RoleResponse`.
- `src/polaris_graph/roles/role_pipeline.py` — `RecordingTransport.complete` sets `reasoning=response.reasoning` on the record.
- `src/polaris_graph/roles/sweep_integration.py` — `run_four_role_evaluation` collects per-claim `{claim_id, role, model_slug, served_model, raw_text, reasoning}` and writes `four_role_role_calls.jsonl` (new constant `FOUR_ROLE_ROLE_CALLS_FILENAME`) under run_dir; `reasoning` is its own field, never concatenated into `raw_text`.
- tests: 13 new transport tests (3 shapes × 3 roles + unterminated-`<think>` raises + think-only raises + separate-field-blank-verdict raises + Mirror `<co>` preserved-after-split) + 1 seam test (jsonl written, reasoning separate from verdict, all 3 roles logged).

## Evidence (verified by Claude main-thread)
- All 433 tests in `tests/roles tests/dr_benchmark tests/architecture` PASS (offline; the 69-test role
  subset incl. the new tests PASS).
- `verify_lock --consistency` OK; `gate_a_dry_run` OVERALL PASS (role_contracts via transport: Sentinel
  yes=UNGROUNDED, Judge off-enum raises, Mirror two-pass binds — i.e. the verdict parsers still work over
  the bare post-split verdict).
- Frozen/untouched: runtime lock NOT promoted; claim_audit_scorer.py, the 5 PR-10 contracts, served==pinned
  (M4) logic, Sentinel polarity, Judge 5-enum, D8 gate all unchanged.

## Red-team focus (rule on these)
1. **No reasoning leak**: confirm `reasoning` reaches ONLY the record + jsonl, never `raw_text` (the bare
   verdict) and never the shipped report. Check the split returns the post-`</think>` remainder as
   `raw_text` and the inner text as `reasoning`.
2. **Fail-closed parity**: a think-only/blank-after-split response AND a separate-field-with-blank-content
   response BOTH raise `RoleTransportError` ("no/blank message content after reasoning"). Confirm.
3. **Unterminated `<think>`** raises (never feeds a half-think to a parser). Confirm.
4. **Mirror `<co>` integrity**: only a LEADING block is split; `<co>` spans in the body are byte-preserved
   and mirror_adapter aligns offsets over the returned bare `raw_text`. Confirm no offset corruption.
5. **Non-str content parity**: a non-str/None `content` path preserves prior behavior (the post-split
   blank guard still raises on None/blank; a structured non-str content is returned as-is as before).
6. **LOC**: +265/-9 total; production executable LOC is ~70 (rest comments+tests). The brief anticipated
   Parts A-E + tests and you APPROVE'd that file set. Confirm this is within acceptable PR bounds for the
   issue, or direct a test/code split.
7. Hygiene: snake_case, explicit imports, no `except: pass`, no `unittest.mock` in src, fail-closed.

APPROVE iff the diff faithfully implements the APPROVE'd plan, cleanly separates verifier reasoning from
the verdict with fail-closed parity, persists it to a reviewable artifact, leaves the frozen
gate/lock/contracts untouched, and is test-proven.
