---
target_bug: M-202
scope: contradiction detector domain coverage
verdict: confirmed
severity: medium
strategy_chosen: C
strategy_label: hybrid_generic_numeric_claim_mining_plus_domain_predicate_hints
tests_required: 6
rationale: |
  BUG-M-202 is confirmed. `extract_numeric_claims()` only attempts extraction after `_normalize_predicate()` matches one of the hard-coded obesity/cardiometabolic predicate strings. Because the clinical AF anticoagulation corpus discusses endpoints such as stroke, systemic embolism, major bleeding, intracranial hemorrhage, INR/TTR, CHA2DS2-VASc, and HAS-BLED rather than "weight loss" or "hba1c reduction", the detector returns `numeric_claims=0 contradictions=0` before any numeric values are considered. The fix should not replace deterministic numeric comparison with unconstrained LLM judgment. It should add generic numeric-claim mining, then use domain YAML predicate hints for normalization, unit policy, and endpoint aliases.
---

# M-202 Deep Dive: Contradiction Detector Coverage

## 1. Finding

BUG-M-202 is confirmed.

The detector is documented as a general numeric contradiction detector, but its extraction gate is domain-specific. In `src/polaris_graph/retrieval/contradiction_detector.py`, `_EFFICACY_PREDICATES` and `_SAFETY_PREDICATES` contain a narrow clinical-metabolic list: weight loss/body weight, HbA1c/A1c, blood pressure, LDL/cholesterol, MACE/mortality, nausea/vomiting, discontinuation, adverse events, pancreatitis, hypoglycemia, and thyroid C-cell (`:78-93`). `_normalize_predicate()` only returns a predicate if one of those literal substrings appears in the quote (`:134-140`).

That means a quote can contain clear numeric contradictions and still be invisible if it uses another domain's endpoint vocabulary. The current AF anticoagulation run demonstrates the failure: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt` logs `[contradict] numeric_claims=0 contradictions=0` even though the query domain naturally contains stroke, systemic embolism, bleeding, INR/TTR, risk-score, and hazard/relative-risk endpoints.

The orchestrator also calls the detector over the retrieved evidence rows without passing domain or question context (`scripts/run_honest_sweep_r3.py:753-754`), so the detector has no way to load domain-specific predicate vocabulary from the existing config bundle.

## 2. Current Controls

Hard-coded predicates:

| Control | Location | Coverage |
|---|---:|---|
| `_EFFICACY_PREDICATES` | `contradiction_detector.py:78-85` | Obesity/cardiometabolic efficacy terms. |
| `_SAFETY_PREDICATES` | `contradiction_detector.py:87-93` | GLP-1/metabolic safety terms. |
| `_normalize_predicate()` | `contradiction_detector.py:134-140` | Literal substring match only; no domain, query, or YAML input. |

Extraction rules:

| Rule | Location | Effect |
|---|---:|---|
| Predicate gate before numeric parsing | `contradiction_detector.py:409-412` | Quotes without hard-coded predicates are skipped entirely. |
| Percentage/HbA1c-first numeric parsing | `contradiction_detector.py:283-333` | Most extracted claims are percentages or HbA1c percentage points; dose/duration regexes exist but are not used for general endpoint mining. |
| Value-phrase verb required | `contradiction_detector.py:235-243`, `:320-326` | Reduces noise, but also misses valid formats such as `stroke rate 1.27 per 100 patient-years` unless the local wording matches the GLP-1-tuned verb list. |
| Reject patterns | `contradiction_detector.py:199-231`, `:365-384` | Filters placebo/comparator, threshold, trial acronym, and duration contexts. Useful, but tuned around obesity trial false positives. |
| Subject extraction from drug regex | `contradiction_detector.py:143-197` | Uses `_DRUG_NAME_RE`; non-drug subjects such as guideline populations, interventions, policy instruments, companies, or technologies can collapse to `unknown`. |
| Grouping key | `contradiction_detector.py:504-507` | Groups by `(subject, predicate, unit, dose)`, not endpoint denominator, time horizon, population, comparator, risk metric, or effect measure. |
| Thresholds | `contradiction_detector.py:465-473` | Uses global `PG_CONTRADICTION_REL_THRESHOLD=0.10` and `PG_CONTRADICTION_ABS_THRESHOLD=1.0`, regardless of endpoint scale. |

Cardinality caps and implicit caps:

| Cap | Location | Consequence |
|---|---:|---|
| One predicate per evidence row | `contradiction_detector.py:409-412` | `_normalize_predicate()` returns the first matching predicate, so multi-endpoint quotes cannot produce multiple predicate groups. |
| One numeric claim per evidence row | `contradiction_detector.py:416-443` | `_find_value_in_context()` returns the first eligible value, and `extract_numeric_claims()` appends exactly one `ExtractedNumericClaim` per evidence row. |
| One contradiction record per group | `contradiction_detector.py:510-532` | A group with many divergent values becomes one min/max record, not pairwise conflicts or endpoint-subgroup distinctions. |
| No explicit output cap in this module | `contradiction_detector.py:485-538` | Runtime is bounded mainly by the one-claim-per-row cap; widening extraction will require an explicit candidate/output limit. |

## 3. Fix Choice

Choose **C: hybrid generic numeric-claim mining + domain-specific predicate hints**.

Do not choose a pure per-domain predicate table as the whole fix. YAML predicate lists would cover AF if someone adds stroke/bleeding terms, but the detector would still fail on the next new domain or endpoint family. It also preserves the current predicate-before-number gate, which is the root design error.

Do not choose generic LLM contradiction detection as the primary mechanism. The file's original rationale is correct that numeric contradictions should be compared deterministically. LLMs are useful for endpoint labeling and candidate extraction fallback, but they should not be the authority deciding whether `1.2%` and `2.4%` conflict.

The hybrid path keeps deterministic numeric comparison while moving extraction from "known predicate first" to "numeric claim first, then normalize endpoint/predicate with hints."

## 4. Fix Specification

Add a configurable claim-mining layer:

1. Introduce `ContradictionProfile` loaded by domain, probably from `docs/pipeline_audit_context/config_bundle/` initially and later from runtime config. Each profile should define endpoint aliases, unit patterns, effect-measure aliases, denominator rules, value verbs, reject patterns, subject hints, and endpoint-specific thresholds.
2. Change the public API to accept context: `extract_numeric_claims(evidence, *, domain=None, research_question=None, profile=None)`. Keep default behavior backward-compatible by loading a generic profile plus the current metabolic hints.
3. Mine all numeric spans first. Support at minimum `%`, `percent`, `per 100 patient-years`, rates, hazard ratios, relative risks, odds ratios, confidence intervals, score thresholds, counts, currency, time-to-event durations, and plain decimals when attached to an endpoint alias.
4. For each numeric span, derive a local window and classify endpoint/predicate from domain YAML aliases, query terms, and generic noun phrases near the number. If no known alias matches but the syntax is a plausible endpoint phrase, keep it as a normalized generic predicate instead of dropping it.
5. Emit multiple claims per evidence row. A single guideline quote may contain both stroke and major bleeding rates; both should be represented.
6. Expand grouping keys to include effect measure, denominator, comparator/arm, population, time horizon, and endpoint phrase where available. Dose should remain for drug trials.
7. Add explicit caps after widening extraction: max claims per evidence row, max groups, and max contradiction records. Caps must log dropped counts so `contradictions.json` does not silently imply full coverage.
8. Keep deterministic contradiction math. Compare only compatible units/effect measures, use endpoint-specific thresholds where configured, and fall back to global thresholds only for compatible native units.
9. Add clinical AF hints to the clinical profile: `stroke`, `ischemic stroke`, `systemic embolism`, `stroke/systemic embolism`, `major bleeding`, `clinically relevant non-major bleeding`, `intracranial hemorrhage`, `gastrointestinal bleeding`, `mortality`, `HAS-BLED`, `CHA2DS2-VASc`, `INR`, and `time in therapeutic range`.
10. Write manifest/run telemetry: profile name/version, claims extracted, claims dropped by reason, generic-vs-hinted predicate counts, cap hits, incompatible-comparison skips, and contradiction count.

The existing `docs/pipeline_audit_context/config_bundle/scope_templates/clinical.yaml` and `completeness_checklists/clinical.yaml` show the right place conceptually: domain behavior is already YAML-driven. Contradiction profiles should be a sibling config, not embedded constants in Python.

## 5. Test Specification

1. `test_m202_af_stroke_rates_extract_without_metabolic_predicate`: two AF anticoagulation evidence rows with `stroke or systemic embolism` percentages or rates should produce numeric claims even though no weight/HbA1c/LDL terms appear.
2. `test_m202_af_bleeding_contradiction_detected`: two rows for the same drug/intervention and `major bleeding` endpoint with compatible `%` values above threshold should produce one contradiction record.
3. `test_m202_multi_endpoint_quote_emits_multiple_claims`: one quote containing both `stroke/systemic embolism 1.3%` and `major bleeding 3.4%` should emit two claims, proving the one-claim-per-row cap is gone.
4. `test_m202_incompatible_effect_measures_not_grouped`: `hazard ratio 0.79` and `annual stroke rate 1.3%` for the same endpoint should not be compared as a contradiction because effect measure/unit differs.
5. `test_m202_domain_profile_loaded_by_orchestrator`: monkeypatch a clinical contradiction profile and assert `run_honest_sweep_r3` passes domain/profile context into `extract_numeric_claims()`, rather than calling it context-free.
6. `test_m202_extraction_caps_report_telemetry`: create an evidence row with more numeric candidates than the per-row cap and assert the detector returns bounded claims plus telemetry indicating cap hits/dropped candidates.

## 6. Residual Risk

Generic numeric mining will increase recall and false-positive pressure at the same time. The fix needs transparent telemetry and conservative grouping keys so new domains do not produce noisy contradiction disclosures. A profile-backed deterministic miner is the right first step because it can catch the AF anticoagulation failure without making contradiction detection depend on opaque LLM pair judgments.
