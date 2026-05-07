# Codex Brief Review — I-f15-005 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-005 — F15 adversarial: paywalled, 500MB resumable, partial run
**Phase:** 1 / **Feature:** F15
**LOC budget:** 150 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict consumed

- P1 (500MB total-cap conflicts with `evidence_pool.json` containing full_text): RESOLVED iter 2 — test #2 scopes assertion to `sources/*.txt` only (the source-snapshot files), NOT the total bundle. evidence_pool.json's size with full_text is out-of-scope (sanitization is a separate I-f15-005-pool follow-up). Test #2 asserts each `sources/<id>.txt` ≤ MAX_SOURCE_TEXT_BYTES + 500 (500-byte buffer for the truncation note); does NOT assert total bundle bytes.
- P2 (paywalled "must be marked"): RESOLVED iter 2 — drop the "marked" requirement from this Issue. `Source.full_text_available=False` + `full_text=None` is the existing metadata marker; test asserts the snippet content lands in the snapshot file. Marker UI annotation → I-f15-005b follow-up.

## Mission

3 adversarial tests for audit bundle export. Each handled per spec.

Per breakdown, "paywalled / 500MB resumable / partial run" map to 3 distinct adversarial scenarios:

1. **Paywalled source** — a Source whose `full_text` is None (paywall blocked retrieval). Snapshot must fall back to `snippet`. Bundle must build but the snippet snapshot must be marked.
2. **500MB resumable** — a bundle whose total bytes would exceed a sane limit (e.g. 500MB simulated via a source with 600KB full_text after multiple sources adding up to >500MB). The bundle build must NOT silently truncate beyond `MAX_SOURCE_TEXT_BYTES`; tests assert each source ≤ 200KB and total ≤ a hard test cap. (HEAD ships the 200KB-per-source cap; this Issue tests it holds.)
3. **Partial run** — a `pipeline_verdict = "abort_no_verified_sections"` report (where every section is dropped). The bundle build must REFUSE — `build_manifest_and_files` raises `ValueError` per `manifest_builder.py:97`. Test asserts the refusal envelope.

## Substrate (HONEST at HEAD)

- `src/polaris_graph/audit_bundle/snapshot_sources.py:64` — `_snapshot_text` falls back to `source.snippet` when `full_text is None`. So paywalled sources don't break snapshot; they get a snippet-only snapshot.
- `src/polaris_graph/audit_bundle/snapshot_sources.py:27` `MAX_SOURCE_TEXT_BYTES = 200 * 1024`.
- `src/polaris_graph/audit_bundle/manifest_builder.py:97` raises `ValueError` if `pipeline_verdict != "success"`.
- `tests/polaris_graph/audit_bundle/test_snapshot_sources.py` already covers some of these: `test_snapshot_falls_back_to_snippet_when_no_full_text`, `test_snapshot_truncates_oversize_full_text`. This Issue extends with adversarial versions covering the END-to-END `build_manifest_and_files` path, not just the helper.

## Approach

Single new pytest module with 3 tests:

`tests/polaris_graph/audit_bundle/test_f15_adversarial.py`:

1. **test_paywalled_source_falls_back_to_snippet**: Build fixture chain where Source has `full_text=None`, `snippet="paywalled snippet text 50 chars."`, sentence cites `[#ev:src-A:0-30]`. Call `build_manifest_and_files`. Assert the source file in bundle contains the snippet content. Assert the cited span resolves (since 30 < snippet length).

2. **test_500mb_per_source_capped**: Build fixture with 5 sources each `full_text="x" * 250_000` (well over the 200KB cap). Sentences cite each within reachable bounds. Call `build_manifest_and_files`. For each `sources/<source_id>.txt` entry in files dict, assert `len(content) <= MAX_SOURCE_TEXT_BYTES + 500` (500-byte buffer for the appended truncation note; SOURCE_TRUNCATION_NOTE_TEMPLATE formats to ~120 bytes). The "500MB" framing in breakdown maps to: per-source files scale linearly with the hard 200KB cap, so a corpus that would otherwise be ≥500MB ships with each source capped — bundle stays bounded. NOTE: this Issue does NOT assert total bundle size, because `evidence_pool.json` serializes full_text per source which is out-of-scope here (I-f15-005-pool follow-up).

3. **test_partial_run_aborts_bundle_build**: Build fixture where every section has `section_status="dropped"` and `pipeline_verdict="abort_no_verified_sections"`. Assert `build_manifest_and_files` raises `ValueError` containing `"verdict"` substring (matches existing message at line 99).

## Acceptance criteria (binding)

1. **`tests/polaris_graph/audit_bundle/test_f15_adversarial.py`** NEW: 3 tests above.
2. NO production-code changes — this Issue is purely test coverage of HEAD behavior.

## Planned diff shape

```
tests/polaris_graph/audit_bundle/test_f15_adversarial.py   NEW +120
```

LOC: +120 net. Under breakdown 150 budget by 30; under CHARTER §1 200-cap by 80.

## Out of scope

- Streaming bundle download for >500MB total (resumable HTTP) → separate I-f15-005a follow-up; the breakdown's "500MB resumable" framing maps here to per-source byte caps holding.
- Real paywall detection (HTTP 403 retry logic) → retrieval-layer concern, not audit_bundle.
- Snippet-vs-full_text "marked" UI annotation → I-f15-005b follow-up.

## Risks for Codex Red-Team

1. **`section_status="dropped"` consistency.** Per `verified_report.py:142-162`, `pipeline_verdict="abort_no_verified_sections"` requires ALL sections dropped. Test fixture obeys that.

2. **Dropped sentences need `verifier_pass=False` + `drop_reason`.** Per `verified_report.py:71-80`, VerifiedSentence with `verifier_pass=False` requires a `drop_reason`. Test fixture obeys.

3. **`section_verify_pass_rate` for dropped sections.** Float [0.0, 1.0]. 0.0 is valid for fully-dropped section.

4. **5-source x 250KB body fixture.** Total Python heap during the test is ~1.25MB pre-truncation; ~1MB post-truncation. Acceptable per CLAUDE.md §8.4.

5. **Snippet-as-snapshot path.** snapshot_sources falls back; no behavior change here; test asserts existing fall-back works end-to-end.

6. **CHARTER §1 LOC cap.** 120 net. Under 200.

7. **No new package dep.**

8. **§9.4 compliance.** No mocks. No magic numbers (250_000 is a fixture size; MAX_SOURCE_TEXT_BYTES is the production constant). No `try: pass`. No TODO/FIXME.

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
