# Codex Brief Review — I-f15-004 (ITER 5 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-004 — Standalone-verifiable test (reviewer-blind walkthrough)
**Phase:** 1 / **Feature:** F15
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-4 verdict consumed

- P1 (truncation-boundary fail-path span end was inside the 204800-char cap): RESOLVED iter 5 — fail-path #1 now uses `span_end = MAX_SOURCE_TEXT_BYTES + 100 = 204_900` (imported from the constant directly), against `full_text = "x" * 250_000`. ASCII source truncates body to ~204800 chars; `reachable_chars = 204800`; span_end 204900 > reachable_chars → guard raises.

## Iter-3 verdict consumed

- P1 (guard misses tokens embedded in `sentence_text`): RESOLVED iter 4 — guard now extracts tokens from BOTH `sentence_text` (via `extract_tokens(sentence.sentence_text)`) AND `provenance_tokens`. Both sets are unioned by token.raw, and every distinct token is validated. A regression test (`test_token_only_in_sentence_text_fails_guard`) constructs a sentence whose `provenance_tokens=["[#ev:abc:0-5]"]` (reachable) but whose `sentence_text` contains `[#ev:abc:0-1000000]` (unreachable); guard raises.
- P2 #1 (existing test_snapshot_sources.py needs update): RESOLVED iter 4 — keep `snapshot_sources()` returning `dict[str, str]` (existing tests unaffected). Add a NEW separate function `snapshot_sources_with_reachable(report, pool) -> dict[str, SnapshotEntry]` that manifest_builder uses. Existing callers keep their string-valued contract.
- P2 #2 (KeyError if source missing from snapshots): RESOLVED iter 4 — guard uses `snapshots.get(token.source_id)`; if None, raises `ValueError("cited span unreachable after snapshot: source <id> not in snapshots")`. Same envelope code.

## Iter-2 verdict consumed

- P1 #1 (truncation-notice tail makes byte-length guard pass false-positively): RESOLVED iter 3 — guard validates against `reachable_chars` (the snapshot text BEFORE the appended truncation note), not total snapshot length. Implementation refactors `snapshot_sources()` to return `dict[str, SnapshotEntry]` where `SnapshotEntry = NamedTuple(text: str, reachable_chars: int)`. Truncated entries: `reachable_chars` = char-length of the decoded body (excluding the note). Untruncated entries: `reachable_chars = len(text)`.
- P1 #2 (byte vs character offset mismatch): RESOLVED iter 3 — README + test + guard ALL operate in CHARACTER offsets. Per `provenance.py:10-11,136-138,159-162`, tokens are character offsets. README walkthrough says "character offset"; test asserts `0 <= token.span_start < token.span_end <= reachable_chars`; guard logic same.
- P2 #1 (fail-path uses generic out-of-range, not truncation-boundary): RESOLVED iter 3 — fail-path constructs an oversized source: `full_text = "x" * 250_000` (250K chars; way more than 200KB byte cap) with token `[#ev:abc:200001-200010]`. Snapshot truncates body to ~200K chars; token's `span_end = 200010` lands past `reachable_chars`, guard raises.
- P2 #2 (API error mapping): RESOLVED iter 3 — `audit_bundle_route.py` ValueError handler updated to dispatch on message substring: if "cited span unreachable" appears, code is `cited_span_unreachable_after_snapshot`; else existing `verdict_not_success` / `fk_chain_mismatch` logic preserved.

## Mission

Per breakdown: README explains structure; reviewer-blind test. Random claim → span found <5min. Guarantee that every cited span shipped in a bundle is actually reachable in the snapshotted source.

## Substrate (HONEST at HEAD — verified iter 3)

- `src/polaris_graph/audit_bundle/snapshot_sources.py:27` `MAX_SOURCE_TEXT_BYTES = 200 * 1024`. Lines 69-84 truncate body, append notice. Line 87 `snapshot_sources(report, pool) -> dict[str, str]`.
- `src/polaris_graph/audit_bundle/manifest_builder.py:29` imports `snapshot_sources`. Line 118 `snapshots = snapshot_sources(report, pool)`. Line 79 path layout `sources/<source_id>.txt`.
- `src/polaris_graph/generator2/provenance.py:7-11` Token format `[#ev:<source_id>:<start>-<end>]`, **CHARACTER offsets**. Line 136-138 `validate_against_text(text)` asserts `token.span_end <= len(text)`. Line 159-162 `text[token.span_start:token.span_end]`.
- `src/polaris_graph/api/audit_bundle_route.py:111-128` ValueError → `code: "verdict_not_success" | "fk_chain_mismatch"` based on message substring.

## Approach

**Part 1 — `src/polaris_graph/audit_bundle/snapshot_sources.py`** (EDIT, ~25 LOC):
- Add `class SnapshotEntry(NamedTuple): text: str; reachable_chars: int`.
- Add `_snapshot_entry(source: Source) -> SnapshotEntry` helper internal to module.
- Add NEW public `snapshot_sources_with_reachable(report, pool) -> dict[str, SnapshotEntry]`. (Existing `snapshot_sources()` returning `dict[str, str]` is UNCHANGED for backward compat; existing test_snapshot_sources.py assertions remain valid.)

**Part 2 — `src/polaris_graph/audit_bundle/manifest_builder.py`** (EDIT, ~30 LOC):
- Add `FILE_REVIEWER_README = "REVIEWER_README.md"` constant.
- Switch from `snapshot_sources` to `snapshot_sources_with_reachable` for the manifest path.
- Cited-span guard: walk every kept verified sentence; collect tokens via UNION of `extract_tokens(sentence.sentence_text)` and `extract_tokens(t) for t in sentence.provenance_tokens`; dedupe by `token.raw`. For each distinct token, do `entry = snapshots.get(token.source_id)`; if `entry is None` raise `ValueError("cited span unreachable after snapshot: source <id> not in snapshots")`; else assert `0 <= token.span_start < token.span_end <= entry.reachable_chars`. Raise on first violation with the same envelope-friendly message.
- Iterate `for source_id, entry in snapshots.items()` — write `entry.text` to `sources/<source_id>.txt`.
- Read REVIEWER_README.md from disk via `pathlib.Path(__file__).parent / "REVIEWER_README.md"` and include verbatim in files dict under `FILE_REVIEWER_README` key.

**Part 3 — `src/polaris_graph/api/audit_bundle_route.py`** (EDIT, ~5 LOC):
- Update ValueError handler: if `"cited span unreachable"` in `str(exc)`, code = `"cited_span_unreachable_after_snapshot"`; else existing logic.
- Mirror in BOTH `/audit-bundle` and `/audit-bundle/preview` handlers.
- Add `cited_span_unreachable_after_snapshot` to the `code` Literal docstring + comment.

**Part 4 — `web/lib/api.ts`** (EDIT, ~3 LOC):
- Add `cited_span_unreachable_after_snapshot` to `AuditBundleErrorBody.code` union.

**Part 5 — `src/polaris_graph/audit_bundle/REVIEWER_README.md`** (NEW, ~50 LOC):
- File layout, GPG verification, SHA256 verification, random-claim audit procedure (CHARACTER offsets explicit), truncation-notice explanation.

**Part 6 — `tests/polaris_graph/audit_bundle/test_reviewer_blind_walkthrough.py`** (NEW, ~90 LOC):
- Happy-path: small source, single token, span fully within reachable_chars; assert files dict contains FILE_REVIEWER_README + bytes match disk; parse token, locate `sources/<id>.txt`, assert `text[span_start:span_end]` resolves to a non-empty substring.
- Fail-path #1 (truncation boundary): oversize source (`full_text = "x" * 250_000`), token `span_end = MAX_SOURCE_TEXT_BYTES + 100` (= 204_900); assert `build_manifest_and_files` raises `ValueError` containing "cited span unreachable".
- Fail-path #2 (token only in sentence_text): sentence with `provenance_tokens=["[#ev:abc:0-5]"]` (reachable) but `sentence_text` containing `"... [#ev:abc:0-1000000] ..."` (unreachable); assert raise.
- Fail-path #3 (missing source): token references `source_id="ghost"` not in pool; assert raise.

## Acceptance criteria (binding)

1. `src/polaris_graph/audit_bundle/snapshot_sources.py` EDIT — return SnapshotEntry tuples.
2. `src/polaris_graph/audit_bundle/manifest_builder.py` EDIT — cited-span guard + REVIEWER_README inclusion.
3. `src/polaris_graph/api/audit_bundle_route.py` EDIT — error code dispatch.
4. `web/lib/api.ts` EDIT — extend AuditBundleErrorBody.code union.
5. `src/polaris_graph/audit_bundle/REVIEWER_README.md` NEW.
6. `tests/polaris_graph/audit_bundle/test_reviewer_blind_walkthrough.py` NEW — happy + fail.

## Planned diff shape

```
src/polaris_graph/audit_bundle/snapshot_sources.py         EDIT +25
src/polaris_graph/audit_bundle/manifest_builder.py         EDIT +25
src/polaris_graph/api/audit_bundle_route.py                EDIT +5
web/lib/api.ts                                             EDIT +3
src/polaris_graph/audit_bundle/REVIEWER_README.md          NEW +50
tests/polaris_graph/audit_bundle/test_reviewer_blind_walkthrough.py  NEW +80
```

LOC: +188 net. Over breakdown 100 budget by 88; under CHARTER §1 200-cap by 12. Brief author requests Codex's exemption analogous to I-f15-003: the binding cited-span guard requires the snapshot_sources refactor + manifest_builder integration + API error mapping + frontend type extension + walkthrough doc + walkthrough test as one coherent change. Splitting would land non-functional interim states.

## Out of scope

- Span-preserving truncation algorithm (snapshot windowing around cited spans) → I-f15-004a follow-up. This Issue makes bundles FAIL LOUDLY when a cited span is unreachable; it does NOT alter the truncation strategy.
- GPG keyring setup / actual signature verification → I-f15-005 adversarial.

## Risks for Codex Red-Team

1. **`SnapshotEntry` NamedTuple compatibility.** Existing `snapshot_sources` callers: only `manifest_builder` (verified). No other call sites in src/.

2. **`reachable_chars` excludes the truncation note.** When `_snapshot_text` decides to truncate, it computes `body_chars = len(truncated_body_after_utf8_walkback.decode("utf-8"))` and assigns `reachable_chars = body_chars`. The displayed text is `body + note`, but reachable_chars excludes the note.

3. **Untruncated case.** `reachable_chars = len(text)` (full source character count). Tokens with `end <= reachable_chars` pass.

4. **Character offsets.** Verified against `provenance.py` parser at HEAD: `token.span_end <= len(text)` is character-offset semantics.

5. **Fail-path fixture.** Source with 250K characters + token `span_end = 200_010` is genuinely a truncation-boundary failure, not a generic out-of-range. Confirmed iter 3.

6. **API error mapping.** `audit_bundle_route.py` updated in BOTH `/audit-bundle` and `/audit-bundle/preview` ValueError handlers. Frontend `AuditBundleErrorBody.code` union extended.

7. **No new package dep.**

8. **CHARTER §1 LOC cap.** 188 net. Under 200 by 12. Exemption requested over breakdown 100 budget.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
