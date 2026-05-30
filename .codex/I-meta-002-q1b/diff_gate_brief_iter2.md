RULE NOW — emit the YAML verdict block FIRST, before any prose. Read the patch at
`.codex/I-meta-002-q1b/codex_diff.patch` (the FULL current diff). Do NOT explore beyond the 6 changed files.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1/2. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd; do not bank issues for iter 6.
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

# Codex diff-gate (iter 2) — I-meta-002-q1b (#939): verifier reasoning separation + capture.

## Iter-1 verdict was REQUEST_CHANGES with ONE P1 — NOW FIXED:
> P1: `complete()` still passed the unsanitized raw to `capture_llm_call`; for `reasoning_content`
> responses that captured the reasoning field, and for inline `<think>` it captured the original
> content with the think block — reasoning leaked into the Path-B capture channel.
> Required change: before capture, build a sanitized raw — drop `reasoning_content` and replace
> assistant content with the bare verdict — preserving served/model/usage/_pathb_served.

**Fix applied (review it):**
- NEW `_sanitize_raw_for_capture(raw, *, bare_text)` in `openai_compatible_transport.py`: returns a
  copy of `raw` with the assistant message's `reasoning_content` dropped and `content` replaced by the
  separated bare verdict; preserves `model`/`usage`/`_pathb_served`/`system_fingerprint`/other choices;
  does NOT mutate the original `raw`.
- `complete()` now calls `capture_llm_call(..., raw_response=_sanitize_raw_for_capture(raw, bare_text=raw_text))`.
- NEW test `test_sanitize_raw_for_capture_strips_reasoning_keeps_served_identity`: asserts the sanitized
  object has `content == bare verdict`, NO `reasoning_content`, no reasoning text anywhere in the blob,
  served-identity fields preserved, AND the original `raw` is unmutated (still carries reasoning for the
  record/jsonl path).

## The rest of the diff (unchanged from iter-1, which you found aligned with the brief):
- `role_transport.py` — `reasoning` field on `RoleResponse` + `RoleCallRecord`.
- `_separate_reasoning` + 4-tuple `_parse_response` (prefer `reasoning_content`; else split leading
  `<think>`, raise on unterminated; post-split blank guard fires identically across both paths).
- `role_pipeline.py` — record carries `reasoning`.
- `sweep_integration.py` — writes `four_role_role_calls.jsonl` (reasoning in its own field).
- transport + seam tests (3 shapes × 3 roles + fail-closed + Mirror `<co>` preserved + jsonl separation).

## Evidence (verified by Claude main-thread)
- 434 tests in `tests/roles tests/dr_benchmark tests/architecture` PASS (offline).
- `gate_a_dry_run` OVERALL PASS (role_contracts via transport still parse the bare verdict).
- Frozen/untouched: runtime lock NOT promoted; claim_audit_scorer.py, 5 PR-10 contracts, served==pinned
  (M4), Sentinel polarity, Judge 5-enum, D8 gate.
- Diff total +331/-10 (production executable ~95 LOC; rest comments+tests).

## Rule on
1. Is the iter-1 P1 (capture-channel reasoning leak) fully resolved by `_sanitize_raw_for_capture`?
2. Any NEW regression from the sanitizer (M4 served==pinned still reads `model`/`_pathb_served` from the
   sanitized copy; non-str/None content path safe; original `raw` not mutated)?
3. Any remaining reasoning-leak path into raw_text, the verdict parse, the capture channel, or the report?

APPROVE iff the P1 is resolved and no new blocker is introduced.
