# Codex Brief Review — I-cj-002 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 collection blocker**: added `tests/crown_jewels/conftest.py` that prepends repo `src/` to `sys.path` so test imports of `src.polaris_graph.generator2.provenance` succeed despite the module's internal `from polaris_graph.retrieval2...` import. (cj-001 worked only because the openrouter_client module never reaches `polaris_graph.*` at import time.)
- **P2 unused imports**: dropped `pytest` and `PROVENANCE_TOKEN_RE` from imports (we use neither).



```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-002 — Provenance token Crown Jewel test. Scope: every generated sentence has `[#ev:source_id:start-end]`. Acceptance: test green. LOC estimate 70.
- **Substrate today:** `src/polaris_graph/generator2/provenance.py` ships:
  - `PROVENANCE_TOKEN_RE` regex (line 31) accepting `[#ev:<id>:<s>-<e>]` where id is `[A-Za-z0-9_][A-Za-z0-9_\-]{0,99}`.
  - `ProvenanceToken` dataclass (line 36).
  - `extract_tokens(sentence) -> list[ProvenanceToken]` (line 49).
  - `strip_tokens(sentence) -> str` (line 76).
  - `has_any_token(sentence) -> bool` (line 89).
  - `validate_token_against_pool(token, pool) -> str | TokenValidationError | None` (line 116).
- **Honest framing per CLAUDE.md §9.4:** ship `tests/crown_jewels/test_cj_002_provenance_tokens.py` that pins CLAUDE.md §9.1.2 ("every generated sentence carries `[#ev:source_id:start-end]` tokens"). The test surface verifies the format-acceptance-and-rejection contract of the parser plus the documented "no token = sentence droppable" property. Update `docs/crown_jewels.md` row 2 from "Pending" to the new test path.

## Plan

### `tests/crown_jewels/test_cj_002_provenance_tokens.py` (NEW, ~75 LOC, 6 tests)

```python
"""Crown Jewel I-cj-002 — Provenance token format invariant.

Per CLAUDE.md §9.1.2: every generated sentence carries
[#ev:<source_id>:<start>-<end>] tokens. Sentences without valid tokens
are dropped by strict_verify.
"""

from __future__ import annotations
from src.polaris_graph.generator2.provenance import (
    extract_tokens, has_any_token, strip_tokens,
)


def test_cj_002_canonical_format_accepts() -> None:
    tokens = extract_tokens("foo [#ev:src_001:10-25] bar")
    assert len(tokens) == 1
    t = tokens[0]
    assert t.source_id == "src_001"
    assert t.span_start == 10 and t.span_end == 25
    assert t.raw == "[#ev:src_001:10-25]"


def test_cj_002_uuid_shaped_source_id_accepts() -> None:
    tokens = extract_tokens("[#ev:abc-1234-def-5678:0-12]")
    assert len(tokens) == 1 and tokens[0].source_id == "abc-1234-def-5678"


def test_cj_002_multiple_tokens_in_sentence() -> None:
    tokens = extract_tokens("[#ev:s1:0-5] and [#ev:s2:10-20] together")
    assert [(t.source_id, t.span_start, t.span_end) for t in tokens] == [
        ("s1", 0, 5), ("s2", 10, 20),
    ]


def test_cj_002_malformed_tokens_rejected() -> None:
    bad = ["[#ev:src:abc-def]", "[#ev::0-5]", "[#xx:src:0-5]",
           "[ev:src:0-5]", "[#ev:src:5]"]
    for sentence in bad:
        assert extract_tokens(sentence) == []
        assert not has_any_token(sentence)


def test_cj_002_strip_tokens_removes_all() -> None:
    out = strip_tokens("hello [#ev:s1:0-5] world [#ev:s2:6-11]")
    assert "[#ev:" not in out and "hello" in out and "world" in out


def test_cj_002_no_token_sentence_is_droppable() -> None:
    # Empty / no-token sentences are exactly what strict_verify drops
    # per the "every generated sentence carries provenance" invariant.
    assert not has_any_token("This claim has no provenance.")
    assert not has_any_token("")
```

### `tests/crown_jewels/conftest.py` (NEW, ~8 LOC)

```python
"""Make src/ importable for crown-jewel tests so deep modules in
src.polaris_graph.* can resolve their own `from polaris_graph...` imports."""
from __future__ import annotations
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
```

### `docs/crown_jewels.md` (MODIFY, ~3-line change)

Update row 2 (I-cj-002): test path → `tests/crown_jewels/test_cj_002_provenance_tokens.py`; bound function → `src/polaris_graph/generator2/provenance.py::extract_tokens`. Replace "Pending" cell.

## Risks for Codex Red-Team

1. **Substrate-honest** — pins existing parser; no new functionality.
2. **§9.4 hygiene** — clean.
3. **CHARTER §3 LOC cap** — ~78 LOC under 200.
4. **Registry fix from I-cj-001 P2** — opportunity to also correct the source-of-truth path. The previous CJ-001 brief had `src/polaris_graph/generator/provenance.py` (does not exist — only `generator2/provenance.py` and `generator/provenance_generator.py` exist). This brief uses the correct `generator2/provenance.py` path and updates the registry accordingly.

## Acceptance criteria

1. New `tests/crown_jewels/test_cj_002_provenance_tokens.py` with 6 tests.
2. `docs/crown_jewels.md` row 2 updated with correct test path + correct source-of-truth function path (generator2/provenance.py).
3. All 6 tests pass.
4. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-4.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
