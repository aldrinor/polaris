# Codex Diff Review — I-f3-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-001 — wire document_ids into graph_v4 evidence pool
**Branch:** bot/I-f3-001
**Brief:** APPROVED iter 3 (iter1 REQ_CH 2P1 _UPLOAD_TABLE wrong → iter2 REQ_CH 2P1 stale+security → iter3 APPROVE 0/0/3P2; all P2 addressed in implementation)
**Canonical-diff-sha256:** `140b8e9e8572f2156d171a04bdf5e61893bfc24da0110d46613dd5f7b360d96c`
**LOC:** 166 net (under CHARTER §1 200-cap by 34)
**Tests:** 7/7 PASS (`PYTHONPATH=src python -m pytest tests/polaris_graph/test_graph_v4_documents.py -v`)

## Files

```
src/polaris_graph/graph_v4.py                       EDIT  +50
tests/polaris_graph/test_graph_v4_documents.py      NEW   +116
```

## What changed

### `graph_v4.py`
- New module-level constant `_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")` matching DocumentIngester's `hashlib.sha256(file_bytes).hexdigest()[:16]` format.
- New helper `_load_uploaded_documents(document_ids, ingester=None, chunk_size=1500) -> list[dict]`:
  - Empty input → empty list.
  - Lazy-imports `DocumentIngester` (single canonical path; defaults if `ingester` not injected).
  - For each `doc_id`: format-validate via `_DOC_ID_RE.fullmatch` (path-traversal mitigation); skip + warn on invalid. `ingester.get_document(doc_id)`; skip + warn on None or empty content.
  - Filename: `original_filename or filename or doc_id` fallback chain.
  - Chunks via fixed-window: `[content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]`.
  - Each chunk emits `{document_id, filename, chunk_index, text}` (chunk_index is the ordinal 0/1/2 via `enumerate`, NOT the byte offset).
  - All-failed → RuntimeError (LAW II).
- In `build_and_run_v4`, after the `q` dict synthesis (line ~196): `if document_ids: q["uploaded_documents"] = _load_uploaded_documents(document_ids)`.

### `tests/polaris_graph/test_graph_v4_documents.py`
- 7 tests using `StubIngester` regular class (no `unittest.mock` per §9.4). Test 7 uses `pytest.MonkeyPatch` + `monkeypatch.setattr("src.polaris_graph.document_ingester.DocumentIngester", lambda: StubIngester(docs))` to patch the lazy import target + `monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", stub)` to capture the q dict end-to-end.

## Iter-3 brief P2 advisories addressed

- **P2 #1 (Test 7 patch target):** `monkeypatch.setattr("src.polaris_graph.document_ingester.DocumentIngester", ...)` — source-module patch covers the lazy import.
- **P2 #2 (`chunk_index` is ordinal):** `enumerate(chunks)` → 0/1/2; test asserts.
- **P2 #3 (`None` vs `list[str]` signature):** None-handling via `if document_ids:` truthy-check at the calling site (build_and_run_v4); helper signature stays `list[str]` per type hint correctness.

## Risks for Codex Red-Team

1. **Path-traversal mitigation.** `re.fullmatch(r"[a-f0-9]{16}")` rejects `"../etc/passwd"`, `"abc"`, mixed-case `"X"*16`, out-of-range `"g"*16`. Test `test_invalid_doc_id_format_skipped_with_warning` asserts.

2. **Lazy import of DocumentIngester.** Inside the function — keeps graph_v4 import cheap; no circular import.

3. **Forward reference to `logger`.** Defined at graph_v4.py:89; function references it; resolved at call-time. Safe. Confirmed via 7/7 PASS.

4. **Filename fallback chain.** Test 3 covers `original_filename` rung; Test 4 covers the `doc_id` fallback rung. The `filename` (no `original_` prefix) rung is not separately tested — minor coverage gap, non-blocking.

5. **Empty-content skip.** Documents with `content == ""` are skipped to avoid empty chunks. Logged warning. The empty-content branch is exercised indirectly via Test 5 (all-invalid-or-missing).

6. **Fail-loud RuntimeError.** Per LAW II. Test 5 asserts.

7. **Test 7 async path.** Uses `@pytest.mark.asyncio` decorator; `pytest-asyncio` is in plugins (config). Verified PASS.

8. **CHARTER §1 LOC cap.** 166 net.

9. **No new package.json / requirements.txt dep.**

10. **`test_q_dict_threading_with_stubbed_run_one_query`.** Patches both source modules; calls `await graph_v4.build_and_run_v4(...)` with valid 16-hex doc_ids; asserts `captured["q"]["uploaded_documents"]` has 2 entries with chunk_index=0 and original_filename set.

11. **Pipeline-A still does NOT consume `uploaded_documents`.** This Issue scopes to v4-layer wiring. Pipeline-A integration is I-f3-001b.

12. **Codex iter-3 P2 #2 wording-only concern (chunk_index ordinal):** test asserts `[c["chunk_index"] for c in out] == [0, 1, 2]` after splitting 4500-char content with chunk_size=1500. Confirmed correct.

## Out of scope

- Pipeline-A consumption → I-f3-001b.
- PDF semantic chunking → I-f3-001c.
- End-to-end strict_verify integration → blocked on I-f3-001b.

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
