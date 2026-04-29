# Codex round 1 — M-D5 phase 2 v1

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md5_phase2_llm_classifier.py`
- DO NOT run rg/find — read directly:
  - `src/polaris_graph/audit_ir/scope_classifier_llm.py`
  - `tests/polaris_graph/test_md5_phase2_llm_classifier.py`
  - `docs/md5_phase2_threat_model.md`
- DO NOT run Python verification scripts that print Unicode

## Scope
Concrete LLM-augmented classifier filling M-D5 phase 1's
ScopeEligibilityClassifier Protocol slot. Mirrors M-D2 phase b
(LLMAugmentedInductor) pattern.

## Public API

```python
class ScopeAffinityLLM(Protocol):
    def classify(
        self, question: str, supported_domains: tuple[str, ...]
    ) -> LLMVerdict: ...

@dataclass(frozen=True)
class LLMVerdict:
    verdict: str  # "in_scope" | "out_of_scope" | "uncertain"
    confidence: float  # [0, 1]
    domain: str | None
    rationale: str

@dataclass(frozen=True)
class LLMScopeEligibilityClassifierConfig:
    supported_domains: tuple[str, ...]
    min_confidence_floor: float = 0.0

class LLMScopeEligibilityClassifier:
    def __init__(self, llm, config): ...
    def classify(self, question: str) -> ScopeClassification: ...

class MockScopeAffinityLLM:
    def __init__(self, profiles=...): ...
    def classify(self, question, supported_domains): ...

def build_question_block(question: str) -> tuple[str, str, str]: ...
```

## Boundaries (7 documented)

1. Pure substrate (no OpenRouter coupling)
2. Closed verdict-string taxonomy (case-insensitive adapt)
3. Domain validation tied to supported_domains
4. Confidence range enforced at adapter time
5. min_confidence_floor demotes IN_SCOPE → UNCERTAIN
6. LLM-side exception → UNCERTAIN with rationale (fail loud)
7. Prompt-injection defense (per-call random delimiters,
   mirrors M-D2 phase b)

## Tests (34/34 passing)

- Construction validation (5 negatives)
- classify() input validation (non-string, empty)
- Verdict adaptation (in_scope, out_of_scope, uncertain,
  case-insensitive)
- Bad LLM output (invalid verdict, out-of-range confidence,
  non-numeric, missing domain, unsupported domain, non-None
  domain on non-IN_SCOPE, wrong-shape return)
- LLM exception handling (RuntimeError → UNCERTAIN;
  LLMScopeClassifierError → re-raise)
- min_confidence_floor demotion (low → UNCERTAIN; high →
  preserved; floor doesn't demote OUT_OF_SCOPE)
- MockScopeAffinityLLM (clinical, policy, no-match,
  empty, unsupported-domains, deterministic)
- End-to-end (clinical, off-topic)
- Prompt-injection delimiters (random per call,
  static-pattern stripped, safe text preserved)

## What might Codex probe

- Verdict-string normalization (LOWER + STRIP) — case
  variants pinned but does it leak `"In Scope "` (with space)?
  Test only covers `"IN_SCOPE"` — gap could be an issue.
- min_confidence_floor=0.0 edge: low-conf in_scope at
  exactly confidence=0.0 — does floor=0.0 demote? Per
  `< floor` strict-less-than, no. But edge case.
- LLMVerdict frozen=True — but LLM sub-impls might return
  fresh instances, no mutation concern.
- Prompt-injection: `secrets.token_hex(16)` is 32 hex chars
  not 16. Code says "16 hex chars" in docstring; actual call
  produces 32. Minor doc/code mismatch.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure substrate
- [x/ ] Verdict taxonomy enforced
- [x/ ] Domain validation correct
- [x/ ] Floor demotion correct
- [x/ ] Prompt-injection delimiters

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
