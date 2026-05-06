# Codex Brief Review — I-f3-002 (ITER 3 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-002 — Backend: data classification taxonomy
**Phase:** 1 / **Feature:** F3 (document upload + grounding)
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 (EXTERNAL_LEAK_FORBIDDEN under-blocking):** ADDRESSED. Verified `docs/carney_delivery_plan_v6_2.md:332`: "All non-PUBLIC_SYNTHETIC classifications blocked from external API". Pivoted policy:
- `EXTERNAL_LEAK_FORBIDDEN: frozenset[DataClassification] = frozenset({CAN_REAL, PRIVATE, CLIENT, UNKNOWN})`.
- Only PUBLIC_SYNTHETIC is allowed external. Default-deny on UNKNOWN.
- Cross-references both Carney plan §332 AND `src/polaris_v6/observability/log_redact.py:26` (which has the narrower `REDACT_KINDS = {CAN_REAL, PRIVATE, CLIENT}` for *log redaction* — UNKNOWN not in that set because logs preserve it for audit; external egress is stricter).

**P2 (substrate inventory incomplete):** ADDRESSED. Substrate section now mentions `src/polaris_v6/observability/log_redact.py:18-26` Literal type + REDACT_KINDS, and the canonical sovereignty policy at `docs/carney_delivery_plan_v6_2.md:332`.

## Mission

Add a canonical `DataClassification` enum + serializer at `src/polaris_graph/sovereignty/classification.py`. Five values per Carney v6.2 §F3 + breakdown: `PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN`. The taxonomy is consumed by I-f3-003 sovereignty router (next Issue) to gate CLIENT-tagged docs from external API calls.

## Substrate (HONEST)

- `web/lib/api.ts:83-88` already exports the same 5-value `DataClassification` TypeScript type. Backend Python equivalent does NOT yet exist as a canonical enum — only ad-hoc string usage:
  - `src/polaris_v6/api/upload.py:36` (`Form("UNKNOWN")`).
  - `src/polaris_v6/observability/log_redact.py:18-26` defines `DataClassification` as a `Literal[...]` (5 strings) + `REDACT_KINDS: set[...] = {"CAN_REAL", "PRIVATE", "CLIENT"}`.
- `docs/carney_delivery_plan_v6_2.md:332` is the controlling sovereignty policy: "All non-PUBLIC_SYNTHETIC classifications blocked from external API". This Issue codifies that policy as `EXTERNAL_LEAK_FORBIDDEN`.
- `src/polaris_graph/sovereignty/` directory does NOT yet exist. This Issue creates it. Subsequent F3-003+ Issues add `router.py`, etc.
- The enum needs to be JSON-serializable (per breakdown's "Acceptance: serializable to JSON") for use in `EvidenceContract`/manifest payloads.

## Acceptance criteria (binding)

1. **`src/polaris_graph/sovereignty/__init__.py`** (NEW): empty file (package marker). LOC: 0.

2. **`src/polaris_graph/sovereignty/classification.py`** (NEW):
   - `from enum import Enum` then:
     ```python
     class DataClassification(str, Enum):
         PUBLIC_SYNTHETIC = "PUBLIC_SYNTHETIC"
         CAN_REAL = "CAN_REAL"
         PRIVATE = "PRIVATE"
         CLIENT = "CLIENT"
         UNKNOWN = "UNKNOWN"
     ```
   - Inheriting from `str` (per stdlib pattern) makes `json.dumps(DataClassification.CLIENT)` produce `"CLIENT"` directly without needing a custom serializer.
   - Module constants: `ALL_CLASSIFICATIONS: tuple[DataClassification, ...] = tuple(DataClassification)`; `EXTERNAL_LEAK_FORBIDDEN: frozenset[DataClassification] = frozenset({DataClassification.CAN_REAL, DataClassification.PRIVATE, DataClassification.CLIENT, DataClassification.UNKNOWN})` — codifies `docs/carney_delivery_plan_v6_2.md:332` "all non-PUBLIC_SYNTHETIC blocked from external API"; consumed by I-f3-003 sovereignty router. Default-deny on UNKNOWN per defensive posture.
   - Helper `parse_classification(value: str | DataClassification | None) -> DataClassification`: accepts an enum instance, a string match, OR None (returns UNKNOWN). Raises ValueError on unknown string.
   - Helper `is_external_leak_forbidden(classification: DataClassification) -> bool`: returns `classification in EXTERNAL_LEAK_FORBIDDEN`.
   - LOC: ~30.

3. **`tests/polaris_graph/sovereignty/__init__.py`** (NEW): empty. LOC: 0.

4. **`tests/polaris_graph/sovereignty/test_classification.py`** (NEW): 7 tests:
   - `test_all_five_values_present`: asserts the 5 enum members exist with correct string values.
   - `test_str_inheritance_makes_json_serializable`: `json.dumps({"c": DataClassification.CLIENT})` produces `'{"c": "CLIENT"}'`.
   - `test_parse_classification_accepts_enum`: passing enum instance returns same.
   - `test_parse_classification_accepts_string`: `parse_classification("CAN_REAL") == DataClassification.CAN_REAL`.
   - `test_parse_classification_none_returns_unknown`: None → UNKNOWN.
   - `test_parse_classification_invalid_raises`: invalid string → ValueError.
   - `test_is_external_leak_forbidden`: PUBLIC_SYNTHETIC → False; CAN_REAL, PRIVATE, CLIENT, UNKNOWN → True (per Carney v6.2 §332 default-deny — only PUBLIC_SYNTHETIC allowed external).
   - LOC: ~50.

## Planned diff shape

```
src/polaris_graph/sovereignty/__init__.py             NEW +0
src/polaris_graph/sovereignty/classification.py       NEW +30
tests/polaris_graph/sovereignty/__init__.py           NEW +0
tests/polaris_graph/sovereignty/test_classification.py NEW +50
```

LOC: +80 net pre-Prettier (well under 100 budget AND CHARTER §1 200-cap).

## Out of scope (deferred)

- Sovereignty router (`router.py`) → I-f3-003 next.
- Sovereignty CI test → I-f3-004.
- Frontend mirror of the enum → already exists at `web/lib/api.ts:83-88`; no change needed.

## Risks for Codex Red-Team

1. **`str` + `Enum` multiple inheritance.** Python stdlib pattern; `class X(str, Enum)` makes members usable as strings AND as enum. Test 2 asserts JSON serializability via this property.

2. **`EXTERNAL_LEAK_FORBIDDEN` set membership.** Frozen set ensures immutability. Per Carney v6.2 §332: `{CAN_REAL, PRIVATE, CLIENT, UNKNOWN}` — every classification EXCEPT PUBLIC_SYNTHETIC is forbidden external egress (default-deny on UNKNOWN as defensive posture).

3. **`parse_classification` accepts None.** Returns UNKNOWN as defensive fallback. Caller can check `is None` upstream if they want to reject.

4. **Naming `EXTERNAL_LEAK_FORBIDDEN`.** Explicit + immediately readable. Alternatives like `FORBIDDEN_EXTERNAL` were considered; rejected for being passive-voice ambiguous.

5. **No new package.json / requirements.txt dep.**

6. **CHARTER §1 LOC cap.** 80 net; well under.

7. **`__init__.py` stub files.** Required for Python package import to work cleanly.

8. **Test coverage.** 7 tests cover: all 5 values, JSON-serialization, parse-from-enum/string/None/invalid, leak-forbidden membership.

9. **Frontend mirror at `web/lib/api.ts:83-88` IS the same 5 strings.** Cross-language consistency maintained — both sides use the same string identifiers.

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
