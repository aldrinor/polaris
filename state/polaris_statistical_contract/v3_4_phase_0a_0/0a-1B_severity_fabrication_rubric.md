# 0a.-1.B — Severity + Fabrication Rubric (draft for Codex review)

**Deliverable**: Phase 0a.0 / 0a.-1.B — severity operational rubric + fabrication taxonomy + injection protocol + ground-truth resolution.
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock 0a.-1.B" after 3 rounds: 8 findings + 2 consistency fixes, all closed; pending operator sign-off).
**Parent**: contract v3.3 §2 (severity scale); depends on D1a (6 domains).
**Plan**: `PHASE_0a_0_PLAN.md`. Must precede adjudicator calibration (0a.-1.A §note).
**Codex review**: `.codex/I-safety-001b/codex_0a1B_review.txt` + `codex_0a1B_confirm{,2}.txt`.
**Version**: 1 (LOCKED)

**Why this exists**: contract §2 gives 1-line severity definitions. Adjudicators cannot apply 1-liners reproducibly. This deliverable gives operational decision criteria + worked examples per domain, the fabrication taxonomy constructors inject, the injection protocol, and how constructor-intent vs blinded-adjudication vs consensus labels resolve.

---

## §1. Severity operational rubric (decision criteria)

Severity is assigned to a **fabrication** (a claim/facet adjudicated CONTRADICTION or UNSUPPORTED). SUPPORTED claims carry no severity. Severity = the harm if a decision-maker acted on the false claim as if true.

### §1.1 Cross-domain severity decision tree (applied per fabrication)

```
S0 (critical): acting on the false claim could cause harm that is ALL THREE of
   DIRECT (not mediated by further independent decisions), NEAR-TERM, and
   HARD-TO-REVERSE — via one of the S0 trigger categories: patient harm,
   binding regulatory non-compliance, binding legal liability, or safety failure.
S1 (high): acting could MATERIALLY MISLEAD a consequential decision, but harm is
   indirect / mediated / reversible (any one of direct/near-term/hard-to-reverse is absent).
S2 (medium): misleading but unlikely to alter a material decision.
S3 (low): stylistic / non-decision-relevant / immaterial.
```

**S0 requires ALL THREE predicates** (direct AND near-term AND hard-to-reverse) — not any one. "Could cause legal liability / regulatory non-compliance" is read as BINDING-ACTION harm, NOT any bad downstream consequence (Codex round-1 #1).

**Mandatory S0-trigger record (Codex round-1 #1)**: to assign S0, the adjudicator MUST state, in the label rationale:
1. the acted-on DECISION (what a decision-maker would do relying on the false claim),
2. the concrete HARM PATH (the causal chain to harm),
3. that the harm is direct AND near-term AND hard-to-reverse,
4. the S0 trigger category (patient harm / binding regulatory / binding legal / safety failure).

If the adjudicator cannot state this S0 path, the label FALLS to S1. (No exception: a domain anchor in §1.2 is a guide to RECOGNIZING the S0 path, not a substitute for stating it — an S0 label always requires the stated path.)

Decision order: test S0 criteria first; if all-three + path not met, S1; etc. Assign the HIGHEST severity whose criteria are met. Fail-upward applies to FIRST-PASS triage only — see §1.3 for the gold-label discipline (fail-upward must NOT silently become gold over-severity).

### §1.2 Per-domain S0/S1 anchors (worked examples)

The S0/S1 boundary is the load-bearing safety line. Per-domain anchors (worked examples are illustrative, not exhaustive; the §1.1 tree governs):

**clinical** (S0 narrowed per Codex round-1 #2 — NOT every safety-related falsehood is S0)
- S0: wrong drug dose changing administration; false "no contraindication"; false "no serious interaction"; false "no boxed-warning risk"; inversion of a SERIOUS safety outcome; wrong indication population driving harmful prescribing; wrong route/frequency causing harm.
- S1: overstated efficacy magnitude (right direction); wrong trial attribution for a real effect; imprecise subgroup; **low-frequency tolerability/discontinuation negation** (e.g., the constipation/discontinuation case — `qualitative_negation`, clinically important but NOT automatic S0; it is S1 UNLESS the packet's decision context makes it likely to change prescribing/monitoring/discontinuation/urgent care in a way that creates DIRECT patient harm, in which case the §1.1 S0 path must be stated).
- S2: minor numeric imprecision not changing clinical decision; peripheral epidemiology stat.
- S3: citation formatting; non-clinical phrasing.

Rationale (Codex round-1 #2): auto-S0 on any safety/tolerability negation inflates S0 prevalence and miscalibrates SMEs to "every safety falsehood is critical," contradicting the §1.1 all-three-predicates harm definition. The constipation case is a real fabrication my regex validator missed (per `feedback_qualitative_negation_escapes_regex`) — its DETECTION matters, but its SEVERITY is S1 absent a direct-harm decision context.

**due_diligence** (separate legal/compliance exposure from ordinary valuation harm — Codex round-1 #3)
- S0: fabricated claim that DIRECTLY creates covenant-breach, solvency-misstatement, fraud, filing/disclosure, or legal-action exposure (binding legal/compliance harm).
- S1: a fabricated metric that changes VALUATION but does not directly create legal/compliance exposure; misattributed but real risk factor; over/understated financial metric within plausible range.
- S2: peripheral market-sizing imprecision.
- S3: formatting / non-material descriptor.

**policy**
- S0: fabricated legal obligation / inverted statutory requirement / wrong jurisdiction-binding rule that would drive a non-compliant or unlawful policy action.
- S1: misstated policy effect magnitude; wrong attribution of a real provision.
- S2: peripheral contextual stat.
- S3: stylistic.

**tech**
- S0: fabricated safety/security property (e.g., "meets standard X" when it fails); inverted compliance/certification claim driving an unsafe deployment.
- S1: overstated performance/capability within plausible range; wrong standard version for a real requirement.
- S2: peripheral spec imprecision.
- S3: stylistic.

**ai_sovereignty**
- S0: fabricated data-residency/jurisdiction claim (e.g., "data stays in Canada" when it does not); inverted sovereignty-compliance claim driving a non-compliant procurement.
- S1: overstated governance-control strength; wrong attribution of a real regulation.
- S2: peripheral context.
- S3: stylistic.

**canada_us** (expanded beyond trade per Codex round-1 #3)
- S0: inverted/fabricated BINDING cross-border obligation that drives a non-compliant action across these families: trade/treaty obligation; immigration/status requirement; defense/security control; energy/interconnection rule; tariff/customs obligation; binding bilateral-agreement provision.
- S1: misstated magnitude of a real cross-border effect; wrong attribution of a real provision; non-binding policy-effect overstatement.
- S2: peripheral comparative stat.
- S3: stylistic.

### §1.3 Severity uncertainty / escalation (fail-upward for triage, NOT for gold labels — Codex round-1 #4)

Fail-upward protects FIRST-PASS triage. It must NOT silently become gold over-severity (which would inflate Gate A's S0/S1 stratum denominators and drift them from production reality).

- **First-pass**: when an adjudicator is between two levels, they record the HIGHER as their first-pass label AND record the lower CANDIDATE in `severity_lower_candidate` AND flag `severity_uncertain = true`.
- **Gold-label discipline**: if `severity_uncertain = true` straddles a **Gate A boundary** (S0/S1 or S1/S2 — the boundaries Gate A sizes strata on), the claim does NOT resolve to the higher label by default. It MUST go to tiebreak/panel (0a.-1.A §6) OR carry both candidate labels into a **pre-outcome severity-migration audit** that resolves the gold label before any outcome exposure. Consensus gold must represent best adjudicated truth, not triage caution.
- Cross-level disagreement between adjudicators follows 0a.-1.A §6 (tuple-majority per field; 3-way ordinal split → panel; no median/average).
- The clinical MD/PharmD-in-path rule (0a.-1.A §3) applies to any clinical S0/S1 severity gold label.
- A **pre-outcome severity-migration audit** (before any Gate outcome is seen) reviews the distribution of `severity_uncertain` resolutions to confirm fail-upward did not systematically over-assign; logged per contract §P4.2 structural exposure.

## §2. Fabrication taxonomy (the kinds constructors inject)

Per `feedback_qualitative_negation_escapes_regex` — both quantitative AND qualitative fabrications must be represented. SEVEN locked types (7th added per Codex round-1 #5):

| Type | Definition | Example (clinical) |
|---|---|---|
| `quantitative` | Wrong number (dose, rate, CI, HR, n, %) | "15 mg" when evidence says 5 mg |
| `qualitative_negation` | A negation/affirmation that inverts a presence/absence finding | "did not lead to discontinuation" when 0.2-0.4% discontinued |
| `relation_direction` (NEW #5) | A non-numeric RELATION or DIRECTION inversion (not a negation) | "A outperformed B" when B outperformed A; "risk decreased" when it increased; "policy expands eligibility" when it narrows; "rule permits export" when it prohibits |
| `citation_swap` | The proposition is TRUE somewhere, but the cited source is wrong/nonexistent | correct effect attributed to a trial that didn't study it |
| `entity_swap` | Right structure, wrong entity | correct dose stated for the wrong drug |
| `temporal` | A claim ONCE true / source-valid, presented as current | a withdrawn indication cited as approved |
| `scope_overreach` | NARROW-to-BROAD generalization beyond the studied cohort | subgroup result generalized to the whole population |

### §2.1 Type-priority rules (Codex round-1 #6 — so `fabrication_type` is unambiguous for D8 stratification)

When a fabrication could match multiple types, classify in this priority order:
1. **Classify the FACTUAL MUTATION first.** If the proposition itself is false (quantitative / qualitative_negation / relation_direction / entity_swap / scope_overreach), that is the PRIMARY type. `citation_swap` is PRIMARY only when the proposition is true somewhere and only the source is wrong/nonexistent.
2. **`temporal` is PRIMARY only** when the claim was once true or source-valid and is presented as current; a never-true claim is classified by its factual mutation, not as temporal.
3. **`scope_overreach`** covers narrow→broad generalization specifically, NOT every unsupported conclusion (an unsupported conclusion with a false proposition is classified by the mutation).

Each fabrication carries a PRIMARY `fabrication_type` (one of the seven) + optional SECONDARY in `constructor_intent_labels` (sealed, per 0a.-1.C). D8 stratifies on PRIMARY.

## §3. Fabrication-injection protocol (production-plausible, not cartoonish)

- Fabrications must be PLAUSIBLE — the kind a frontier generator actually produces, not obvious nonsense. A cartoonish fake tests nothing.
- The constructor derives the fabrication from a REAL source claim, then mutates it per one taxonomy type (e.g., take a real "5 mg" and make it "15 mg").
- The injected fabrication must remain internally coherent with the surrounding packet (no tells).
- Per 0a.-1.A §5 label-symmetric packet construction: the packet is built identically for fabricated and non-fabricated claims — no spotlighting.
- **Matched supported controls (Codex round-1 #7 — anti-pattern-leakage)**: fabricated claims must NOT be the only edited claims. SUPPORTED claims receive an EQUIVALENT editing pass (same paraphrase/mutation-style transformations applied to a true value that stays true) so adjudicators cannot learn "edited = fake." Specifically: identical paraphrase/editing passes across fabricated and supported, neutral facet generation, no asymmetric contradiction spotlighting, and a matched-control ratio pre-registered in D8. A tidy one-token mutation on fakes only = a tell.
- Severity is assigned to the injected fabrication per §1 (constructor records intended severity in sealed `constructor_intent_labels`; this is NOT the gold truth — see §4).
- Distribution targets per stratum/cell + matched-control ratio come from D8 allocation (not this deliverable).

## §4. Ground-truth resolution (constructor-intent vs blinded vs consensus)

Three label layers (0a.-1.C), three distinct roles:

1. **`constructor_intent_labels`** (sealed): what the constructor INTENDED to inject (severity + fab_status + fabrication_type). Used for: injection bookkeeping + post-hoc analysis. NOT the gold truth. NOT shown to adjudicators.
2. **`blinded_adjudication_labels`** (first-pass): independent blinded adjudicator severity + fab_status. The IRR object (contract §7.3). This is what Gate E measures.
3. **`consensus_gold_labels`**: the adjudicated truth (agree / tiebreak / panel per 0a.-1.A §6). This is the gold-set truth Gates A/B/D measure against.

**Resolution rules**:
- Gold truth = `consensus_gold_labels` (adjudicator-derived), NOT constructor intent. A constructor who intended S1 but whom adjudicators unanimously rate S0 → gold = S0. The constructor's intent does not override blinded adjudication.
- If `constructor_intent` and `consensus_gold` DISAGREE on fab_status (constructor injected a fake but adjudicators rated it SUPPORTED, or vice versa), that is a recorded **construction-quality signal** (the fabrication wasn't convincing, or the constructor erred) — logged, surfaced for review, but `consensus_gold` still governs the gold set.
- **Preserve the signal without discarding it (Codex round-1 #8)**: record the full intent→gold MIGRATION matrix by `fab_status`, `severity`, and `fabrication_type`. High disagreement rates in a cell are a construction-quality flag: such cells are QUARANTINED and TOPPED-UP in D8 BEFORE outcome unblinding (so the gold set stays adjudicator-derived AND adequately populated). The migration matrix is structural exposure per contract §P4.2.
- IRR (Gate E) is computed on `blinded_adjudication_labels` first-pass ONLY — never on constructor intent or consensus.

## §5. Definition of done (0a.-1.B)

Locked: cross-domain severity decision tree (all-three-predicates S0 + mandatory path record), per-domain S0/S1 anchors, severity-uncertainty escalation (fail-upward triage-only + gold-label discipline), 7-type fabrication taxonomy + type-priority rules, injection protocol (plausibility + label-symmetry + matched controls), 3-layer ground-truth resolution + intent→gold migration matrix. Codex §-1.1 APPROVE. Hash-pin. Operator sign-off (operator/domain-SME may refine per-domain anchors — anchors are illustrative, the §1.1 tree + §1.3 escalation are binding).

## §6. Dependencies + forward notes

- Needs D1a (6 domains) — DONE.
- Precedes adjudicator CALIBRATION (0a.-1.A): SMEs calibrate against THIS rubric.
- `fabrication_type` enum feeds 0a.-1.C `constructor_intent_labels` + D8 stratification (fabrication-type is a D8 stratification axis).
- Per-domain S0/S1 anchors may be refined by domain SMEs during calibration (governed amendment per contract §P4; anchors are illustrative not binding, so refinement is Category-1/2 not Category-4).
