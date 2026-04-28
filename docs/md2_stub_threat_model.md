# M-D2 Stub (Keyword Inductor) — Threat Model & Coverage Boundary

**Status**: locked 2026-04-27 (asymptoting after round 4)
**Module**: `src/polaris_graph/auto_induction/keyword_inductor.py`
**Tests**: `tests/polaris_graph/test_md2_keyword_inductor.py` (20 tests)
**Tracks**: `outputs/codex_findings/md2_stub_review/` (round 1) → `md2_stub_round{2,3,4}/` (rounds 2-4)

---

## What this is

The M-D2 stub keyword inductor is the **rule-based first iteration** of Phase D auto-induction. It implements `InductorProtocol` so it plugs into the M-D1 benchmark harness and gives Phase D a concrete induction baseline before the LLM-augmented version (M-D2 phase b) is built.

Per `docs/phase_d_milestones.md` M-D2: rule-based FIRST, LLM-augmented SECOND. The stub unblocks pipeline integration; it is **explicitly meant to be replaced**, not perfected.

## What's in scope

- Routing queries to one of the existing curator-reviewed contract slugs (`clinical_tirzepatide_t2dm`, `policy_medicare_drug_price`) when keyword profiles match strongly.
- Abstaining when:
  - No anchor keyword matches (high-precision identifiers — drug brand names, named programs, named statutes)
  - Total hits below `accept_count_floor=2`
  - Margin to runner-up below `margin_count_floor=1`
  - A disqualifier keyword matches (device-specific, employer-plan-specific)
- Producing `InductorVerdict(decision, confidence, abstain_reason)` with validated shape.

## What's NOT in scope (documented limitations)

After 4 Codex review rounds, the asymptoting pattern is clear: each round finds 2-4 additional keyword variants (plurals, hyphenations, paraphrases, near-domain adversarials) that the previous round missed. Keyword matching is fundamentally fuzzy; there is no fixed point. The stub accepts these limitations:

| Limitation | Why | Defended by |
|---|---|---|
| **Novel paraphrase** (queries using new vocabulary not in profiles) | Keyword profiles are hand-curated and finite. Cannot anticipate every phrasing. | M-D2 LLM-augmented (embedding similarity + LLM template-affinity) — coverage gap is the intended motivation for M-D2 phase b. |
| **Hyphenation / spacing variants** (`insulin pump` vs `insulin-pump`) | Word-boundary regex distinguishes these. | Add as separate disqualifier. Codex round 4 caught this; v5 fixed with explicit hyphen variants. |
| **Plural / morphological variants** (`commercial plan` vs `commercial plans`) | Same as above. | Add explicit plural. |
| **IRA-non-drug-pricing queries that mention IRA + Part D without "drug"** | "IRA" and "Part D" both have non-drug-pricing scope (clean energy, EVs, MA plan rules). The stub abstains by design when the word "drug" is absent. | Operator review queue. The user reformulating with "drug pricing" routes correctly. |
| **Single-anchor clinical queries with no support context** (e.g. "Mounjaro side effects in elderly") | Conservative abstain — could be safety scope rather than T2DM-efficacy scope. | Operator scopes further. |
| **On-domain queries to a different contract** (semaglutide for non-diabetic obesity) | Keyword overlaps with curator profile but topic is different. Disqualifier keywords help but won't cover all cases. | M-D2 LLM-augmented + operator review. |

## Coverage (M-D1.5 validation set)

| Metric | Value | M-D1 acceptance threshold |
|---|---:|---|
| precision | **1.000** | ≥ 0.80 ✓ |
| silent_disagreement_rate | **0.000** | ≤ 0.05 ✓ |
| abstain_recall | **1.000** | ≥ 0.95 ✓ |
| abstain_precision | **1.000** | ≥ 0.80 ✓ |
| operator_review_load | 0.674 | ≤ 0.30 ✗ — set is intentionally negative-heavy |

The operator-review-load failure is a **set-composition artifact**, not an inductor weakness: 29 of the 43 validation cases are negative (ambiguous + out-of-scope) by design, to stress-test abstain behavior. A balanced 100-200-case set (M-D1.5 follow-on) with realistic in-scope:negative ratio would drop this metric to ~0.30.

## Why we stopped at round 4

After 4 Codex review rounds:

- **Round 1**: 4 substantive defects (substring double-count, no anchor requirement, missing disqualifiers, case_results inconsistency) — structural fixes.
- **Round 2**: 2 edge cases (IRA over-broad anchor, hospital reimbursement disqualifier too blunt) — keyword-tuning fixes.
- **Round 3**: 2 edge cases (IRA narrow under-fit, plural insulin pump) — keyword-tuning fixes.
- **Round 4**: 3 edge cases (IRA provisions still over-broad, plural commercial plans, hyphenated insulin-pump) — keyword-tuning fixes.

The pattern matches `feedback_adversarial_review_stop_criterion.md` precisely: rounds 2-4 each fix 2-3 keyword variants without touching structure. The marginal cost of each round (Codex compute + commit churn) exceeds the marginal gain. Per the advisor consult before round 4, this is the asymptoting pattern that justifies a documented hard-stop.

If round 5 / 6 / 7 found NEW classes of defect (structural bugs, missed acceptance criteria), the loop should resume. So far each round has found incremental keyword tuning only. The advisor's recommendation: lock with this document, move forward to M-D2 LLM-augmented (which fundamentally avoids the keyword-edge-case class via embedding similarity).

## How to use this document

**Before adding a new keyword to `keyword_inductor.py`:**

1. Confirm the keyword closes a real bypass (Codex repro or production query).
2. Distinguish anchor (high-precision) vs support (broad context). Don't put broad terms in anchor.
3. Add explicit plural / hyphen / morphological variants if applicable.
4. Add a regression test under `test_round{N}_*` naming so the variant doesn't regress.

**Before claiming "the inductor has a bug":**

1. Verify the query produces wrong result (run inductor.induce(query) directly).
2. Check whether the documented limitations table above already covers the case. If yes, this is by design — abstain is the right behavior.
3. If genuinely uncovered, add to the validation set as ambiguous/oos OR add the missing keyword. Don't expand anchors blindly.

**M-D2 LLM-augmented version (when shipped):**

Should subsume this stub. Embedding similarity + LLM template-affinity scoring fundamentally avoids the keyword-edge-case class. The stub's keyword profiles will become a soft prior (ontology hints) rather than the hard routing rule. M-D1 harness stays the same — the inductor swap is the only delta.

## Test count

42 tests as of v5 lock:
- 8 validation-set loader tests
- 11 contract comparison tests
- 4 InductorVerdict validation tests
- 9 KeywordInductor unit tests (routing, abstention, disqualifiers, word-boundary)
- 5 round-1 regression tests (loader bug, seed slug, type/required_fields, disqualifier)
- 1 round-2 (already covered by general suite)
- 4 round-3/4 regression tests (IRA scope, plural disqualifiers, hyphen disqualifier)

All 42 pass. The test naming (`test_round{N}_*`) preserves the round-by-round fix history.
