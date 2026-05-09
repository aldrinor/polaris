# Codex Brief Review — I-cj-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-003 — Strict-verify Crown Jewel test. Scope: per-sentence numeric match + ≥2 content-word overlap. Acceptance: test green; mutation tests verify gate teeth. LOC estimate 100.
- **Substrate today:** `src/polaris_graph/generator2/strict_verify.py::verify_sentence` (lines 89-158) implements 5 ordered checks per CLAUDE.md §9.1.3:
  1. at least one well-formed token → no_provenance_token
  2. every token references known source_id → invalid_token
  3. spans within source bounds → span_out_of_range
  4. every decimal in sentence in spans → numeric_mismatch
  5. ≥N shared content words → overlap_too_low
  - `_min_overlap_threshold()` reads `PG_PROVENANCE_MIN_CONTENT_OVERLAP` env var; default 2.
  - `is_synthesis_claim=True` + no tokens passes (per I-f5-006).
  - EvidencePool fixture pattern at `tests/polaris_graph/audit_bundle/test_bundle_builder.py:35-63`.
- **Honest framing per CLAUDE.md §9.4:** ship `tests/crown_jewels/test_cj_003_strict_verify.py` that pins all five gate teeth — both pass-on-correct-input AND fail-with-correct-DropReason for each violation. The "mutation tests verify gate teeth" acceptance maps to the rejection-side tests: each test mutates one input element to violate a single check and asserts the specific drop_reason. Update `docs/crown_jewels.md` row 3.

## Plan

### `tests/crown_jewels/test_cj_003_strict_verify.py` (NEW, ~110 LOC, 7 tests)

```python
"""Crown Jewel I-cj-003 — Strict-verify per-sentence invariant.

Per CLAUDE.md §9.1.3: every sentence in the verified report must pass
strict_verify.verify_sentence — (a) >=1 well-formed token, (b) every
token resolves to a known source, (c) spans within source bounds,
(d) every decimal in sentence appears in span text, (e) >=N shared
content words between sentence and combined span (default N=2).

Mutation pattern: each REJECT test mutates one element of a known-good
fixture and asserts the SPECIFIC drop_reason — this is what the
issue_breakdown calls "mutation tests verify gate teeth."
"""

from __future__ import annotations
from datetime import datetime, timezone
from src.polaris_graph.generator2.strict_verify import verify_sentence
from src.polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict, EvidencePool, Source, SourceTier,
)


def _pool(full_text: str = "Aspirin reduced mortality by 12.5 percent in adults.") -> EvidencePool:
    src = Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org", tier=SourceTier.T1, title="t",
        snippet="s", full_text=full_text, full_text_available=True,
        source_id="src-A",
    )
    return EvidencePool(
        pool_id="p1", decision_id="d1", sources=[src],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 1, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0, cost_usd=0.0,
    )


def test_cj_003_pass_on_well_formed_sentence() -> None:
    pool = _pool()
    sentence = "Aspirin reduced mortality by 12.5 percent [#ev:src-A:0-50]."
    ok, reason = verify_sentence(sentence, pool, min_content_overlap=2)
    assert ok and reason is None


def test_cj_003_reject_no_provenance_token() -> None:
    ok, reason = verify_sentence("This claim has no token.", _pool(), min_content_overlap=2)
    assert not ok and reason == "no_provenance_token"


def test_cj_003_reject_invalid_token_source() -> None:
    sentence = "Claim cites unknown source [#ev:src-MISSING:0-5]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "invalid_token"


def test_cj_003_reject_span_out_of_range() -> None:
    sentence = "Out of bounds [#ev:src-A:0-10000]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "span_out_of_range"


def test_cj_003_reject_numeric_mismatch() -> None:
    # Sentence contains "99.9" but the span (0-50 = "Aspirin reduced
    # mortality by 12.5 percent in adults.") does not.
    sentence = "Aspirin reduced mortality by 99.9 percent [#ev:src-A:0-50]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "numeric_mismatch"


def test_cj_003_reject_overlap_too_low() -> None:
    # Sentence cites the source span but uses unrelated content words.
    sentence = "Apples bananas oranges grapes [#ev:src-A:0-50]."
    ok, reason = verify_sentence(sentence, _pool(), min_content_overlap=2)
    assert not ok and reason == "overlap_too_low"


def test_cj_003_synthesis_claim_passes_without_token() -> None:
    # I-f5-006: synthesis claims pass without provenance.
    ok, reason = verify_sentence(
        "Synthesis observation across sources.",
        _pool(),
        min_content_overlap=2,
        is_synthesis_claim=True,
    )
    assert ok and reason is None
```

### `docs/crown_jewels.md` (MODIFY)

Update row 3 (I-cj-003): test path → `tests/crown_jewels/test_cj_003_strict_verify.py`; bound function → `src/polaris_graph/generator2/strict_verify.py::verify_sentence`.

## Risks for Codex Red-Team

1. **Numeric-mismatch test fragility** — sentence text "99.9 percent" must NOT appear in span "0-50" of full_text. Verified manually: `_pool()` full_text "Aspirin reduced mortality by 12.5 percent in adults." chars 0-50 is "Aspirin reduced mortality by 12.5 percent in adult" — does not contain "99.9". Test is robust.
2. **Overlap-too-low test fragility** — sentence content words `{apples, bananas, oranges, grapes}` (3+ chars, non-stopwords) intersect with span content words `{aspirin, reduced, mortality, percent, adult}` = ∅. Default threshold 2 → overlap_too_low fires.
3. **Substrate-honest** — pins existing function; no new functionality.
4. **§9.4 hygiene** — clean.
5. **CHARTER §3 LOC cap** — ~115 LOC under 200.

## Acceptance criteria

1. New `tests/crown_jewels/test_cj_003_strict_verify.py` with 7 tests covering pass + 5 specific rejections + synthesis-claim escape hatch.
2. `docs/crown_jewels.md` row 3 updated.
3. All 7 tests pass.
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
