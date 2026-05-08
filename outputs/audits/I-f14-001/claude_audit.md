# Claude architect audit — I-f14-001

**Issue:** Migrate workspace_memory to Chroma semantic
**Branch:** bot/I-f14-001
**Canonical-diff-sha256:** 8c2caa86d5c3a229365f0568f8ad1666757ed85ddab5132d4cc6e9ddf3601659
**Brief verdict:** APPROVE iter 3 (LOC trim to 200 cap; per-test unique collection_name; mkdir guard; metadata None-safe; telemetry off; empty-kinds short-circuit; persistent round-trip + wrong-metric tests)
**Diff verdict:** pending Codex iter 1

## Substrate honesty
- New `ChromaWorkspaceMemoryStore` adds vector-recall surface alongside (NOT replacing) the in-memory `WorkspaceMemoryStore`. Production router unchanged.
- `_default_embed_fn` raises RuntimeError loudly per LAW II — no silent fallback to a fake embedder in production.
- Per CLAUDE.md §8.4, the module never instantiates sentence-transformers; tests inject a deterministic 8-dim hash embedder. Production sentence-transformers wiring + router swap are explicit follow-up I-f14-001b work.
- Cosine-metric guard rejects pre-existing collections with the wrong distance metric — refusing to mix scoring scales.
- Telemetry-off via `Settings(anonymized_telemetry=False)`. Codex iter-3 P2 caveat: chromadb 1.0.20 still emits some failed-telemetry log lines — surfaced as known caveat, not silently suppressed.

## §9.4 backend hygiene
- No `try/except: pass`, no magic numbers (top_k from query, threshold from chromadb), no `time.sleep`, no TODO/FIXME/XXX, no `from x import *`.
- Lazy `import chromadb` inside __init__ avoids module-level cost.

## CHARTER §1 LOC cap
- 198 net. Under 200. Verified via `git diff --stat HEAD~1`: requirements-v6.txt +4, chroma_store.py +101, test +93.

## Tests
- 8 new tests pass in 2.5s, including persistent-round-trip (tmp_path) and wrong-metric-raise.
- Existing 14 tests (test_workspace_memory.py + test_api_memory.py) unchanged, 14/14 still passing.
- Total: 22/22 passing in 4.6s.

## Verdict
APPROVE.
