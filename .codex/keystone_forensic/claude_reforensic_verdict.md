# Claude re-forensic verdict — keystone RECALL gap (#1217)

## §-1.1 FAITHFULNESS: VERIFIED — zero fabrication
Kept distill sentence "Colibactin induces double-strand breaks in cultured cells [colibactin_pks_ecoli_mechanism]." is a near-verbatim, correctly-attributed, correctly-scoped restatement of the source direct_quote (~offset 5772: "...and induces double-strand breaks in cultured cells3."). Hedge handling faithful (source's "is believed to" scopes to the alkylation clause, which the distiller dropped; the DSB clause is stated as fact by the source). No number distortion (claim carries no numbers). The keystone fix introduced NO fabrication; it only collapsed recall.

## RECALL ROOT CAUSE
MAP filter `_validate_finding` judges each finding against the model's NARROW `support_quote`, but that quote never reaches the final output. REDUCE writes fresh prose citing [ev_XXX]; filter strips finding markers; unchanged legacy `_rewrite_draft_with_spans` -> `_find_best_span_for_sentence` (live_deepseek_generator.py:244) re-fits the span by sliding an 800-char window over the entire ~24,663-char direct_quote, and strict_verify checks that WIDE span.

Asymmetric spans:
- Final gate (legacy + distill): claim vs an 800-char re-fit window over the whole source — generous.
- MAP step 4 `_all_numbers_in_span` (evidence_distiller.py:584): every claim number must sit inside the model's NARROW support_quote — strict.
- MAP step 1 `_locate_span_in_source` (:468): the narrow quote must be locatable (paraphrase -> reject).

Every step-1/step-4 rejection is pure recall loss with ZERO faithfulness benefit (final independent gate re-checks the prose against the full source anyway). Evidence step-4-dominant: legacy's 6 verified are numeric-heavy (OR 14, CI 4-44, 22%/10, 37%/17, 5,876 genomes); the lone distill survivor is the ONLY non-numeric claim.

Honesty caveat: step-1-vs-step-4 dominance reasoned from redundancy + non-numeric-survivor pattern; could NOT measure per-step reject counts from read-only artifacts.

## THE ONE FIX — candidate (b)
Make step 4 NON-BLOCKING at evidence_distiller.py:584 — compute `_all_numbers_in_span(...)` (keep for logging) but do NOT `return None` on it. Mirrors step-6 entailment (lines 624-635: computed, never gates).
- Step 4 docstring (:417-425) says its only purpose is a "cheap local pre-filter before the (more expensive) entailment call." Entailment is now non-blocking, so that rationale is dead.
- Brings distill to parity with legacy (zero numeric checking at extraction) WITHOUT weakening strict_verify (strict_verify re-checks every number vs the wide final span).
- (b) is DIAGNOSTIC: after it, step-1 (locate) is the only substantive rejector left; if recall still < legacy, residual is step-1 paraphrase rejection -> (c) fuzzy locate is the surgical follow-up.
- Rejected: (a) wider MAP quote (prompt change, makes step-1 harder); (d) multiple findings/source (doesn't address rejection); (c) fuzzy locate (larger new mechanism, own false-accept surface) — hold as follow-up.

Constraint satisfied: (b) edits only `_validate_finding`; strict_verify / 4-role / D8 byte-untouched.
