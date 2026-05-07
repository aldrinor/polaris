# Claude architect audit — I-f15-004

**Issue:** Standalone-verifiable test (reviewer-blind walkthrough)
**Branch:** bot/I-f15-004
**Canonical-diff-sha256:** 1f1e16e5827a59080715707a09580ed6d7e8a7ed760c012a111b39354b4a6dd6
**Brief verdict:** APPROVE iter 5 (cap-hit; 0/0/0P1; 1 P2 cosmetic; no remaining blockers)
**Diff verdict:** APPROVE iter 1 (0/0/0P1; 1 P2 cosmetic; accept_remaining; LOC exemption granted)

## Substrate honesty
- `snapshot_sources` retains its `dict[str, str]` API; new `snapshot_sources_with_reachable` and `SnapshotEntry` are additive. 11 existing snapshot tests still PASS.
- `_assert_cited_spans_reachable` walks the UNION of `extract_tokens(sentence_text)` + `extract_tokens(t) for t in provenance_tokens`, deduped by `token.raw` — closes the iter-3 P1 (token only in sentence_text).
- `MAX_SOURCE_TEXT_BYTES + 100 = 204_900` is genuinely past the truncated body cap (iter-4 fixed the 200_010 boundary fail).
- API error mapping updated in BOTH `/audit-bundle` and `/audit-bundle/preview` ValueError handlers; AuditBundleErrorBody.code union extended.

## Algorithm correctness
- Reachable-chars logic: untruncated → `len(text)`; truncated → `len(decoded_body)` BEFORE truncation note appended.
- Guard correctness: missing source_id → unreachable; `span_end > reachable_chars` → unreachable; otherwise pass.
- Codex iter-1 P2 (zero-length spans rejected): documented as known cosmetic; `0 <= start < end` enforces non-empty spans which matches strict-verify intent (a "claim" is text content, not nothing). Captured for follow-up if generator2 ever ships zero-length tokens.

## §9.4 compliance
- No mocks. No magic numbers (`MAX_SOURCE_TEXT_BYTES + 100` derives from constant; `250_000` is a fixture size, not production logic). No `try: pass`. No TODO/FIXME.

## Sovereignty / external-egress
- Pure additive guard + reviewer doc + tests. Zero external-egress surface.

## Test integrity
- 28/28 PASS locally on Python 3.13.13 (4 new + 24 neighboring).
- Hermetic: no env, no network, no fixtures shared with bundle_builder tests.

## Out-of-scope follow-ups (named)
- I-f15-004a: span-preserving truncation (snapshot windowing around cited spans rather than fail-loud).
- I-f15-004a (extended): align zero-length span handling between provenance contract and bundle guard.

## CHARTER §1 LOC cap
- 303 net. Codex granted exemption iter 1 (accept_remaining, no remaining_blockers). Per CLAUDE.md §8.3.6, when convergence_call flips to accept_remaining, accept and ship.

## Verdict
APPROVE on architect review. Ready to ship.
