"""S0 safety-floor coverage binder (I-perm-020 #1212) — DEFAULT-OFF, additive credit.

PURE FUNCTION, NO NETWORK, NO SPEND. This module credits a required S0 SAFETY category to an
ALREADY-VERIFIED claim AFTER per-claim verification (never inside generation), so the D8
safety-floor (``release_policy.apply_d8_release_policy``) sees the credited category. It exists to
fix the measured drb_76 false hold: a VERIFIED contraindication claim ("not recommended"/"should be
avoided" for an immunocompromised population, citing the exact CDC source) carried
``s0_categories=[]`` because its text never used the literal token "contraindicated", so D8 coverage
stayed < 0.70 and the run safety-floored as ``released_insufficient_safety_evidence`` despite a
faithful safety claim.

WHAT IT DOES (and just as importantly, what it does NOT):

* It ADDS coverage/credit on TOP of verification. It NEVER relaxes a faithfulness gate, NEVER
  changes the D8 decision threshold, and NEVER changes the release rule. A category it credits at
  build time is STILL gated downstream by the 4-role ``verdict == VERIFIED`` check in
  ``release_policy`` (a claim the 4-role rejects earns NO S0 credit) — so this is an additive credit,
  not a gate relaxation.

* The credit rule mirrors the design ruling in ``docs/drb76_downstream_solutions.md`` (hurdle #2):
  ``credit(category) = strict_verify VERIFIED AND assertion is a contraindication DIRECTION (not its
  negation) AND semantic_relation maps to the required category AND entity slots bound AND polarity
  not ABSENT``. Concretely it reuses the WHOLE I-perm-002 conjunction (NOT contraindication-direction
  alone): (a) the claim must cite evidence whose canonical identifier EXACTLY matches the entity's
  (``_entity_canonical_match``); AND (b) every non-concept content token (e.g. the population anchor
  "immunocompromised") must be literal-exact present; AND (c) the contraindication CONCEPT token must
  be satisfied by a high-precision contraindication-DIRECTION phrase; AND (d) the deterministic
  negation guard must pass (a negated/inverted/absent phrase earns NO credit). Crediting on direction
  WITHOUT the population anchor + canonical evidence match is the over-credit failure this avoids.

* DIRECTION OF ERROR (binding, §-1.1): over-crediting a contraindication is LETHAL (a report that
  wrongly believes it warned). UNDER-crediting is a SAFE disclosed gap under always-release
  (I-perm-001). Every branch errs toward refusing credit.

The binder forces the I-perm-002 SEMANTIC recognition ON internally (it is the whole point of the
binder) WITHOUT mutating the ``PG_SWEEP_SEMANTIC_CONTRAINDICATION`` global — it calls the shared
matcher with ``semantic=True``. The binder's own activation is the SEPARATE, default-OFF
``PG_S0_COVERAGE_BINDER`` flag, read at CALL TIME by the caller seam in ``native_gate_b_inputs`` (so
flag-OFF means no import and no call — byte-identical legacy behavior).
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

# The recognizer + canonical-match primitives live in native_gate_b_inputs (I-perm-002). Import them
# here at MODULE scope: this module is only ever imported by the caller seam AFTER the
# PG_S0_COVERAGE_BINDER flag is found truthy at call time, so flag-OFF never imports this module and
# never pulls these symbols (no import-time cost, no cycle — native_gate_b_inputs imports THIS module
# only via a function-local lazy import inside the seam).
from src.polaris_graph.roles.native_gate_b_inputs import (
    _KEY_ENTITY_ID,
    _content_requirements_satisfied_impl,
    _entity_canonical_match,
)

# Validated-entity tuple shape produced by native_gate_b_inputs.build_native_gate_b_inputs:
# (entity_dict, severity, s0_category_or_None). Only S0 entities (s0_category is not None) are
# credit-eligible here; non-S0 coverage is handled by the existing _claim_covers_entity path and is
# intentionally NOT touched by this binder.
_SEVERITY_S0 = "S0"

# Default-OFF activation flag. ON only on an EXPLICIT truthy token (a stray value like "garbage" must
# NOT silently enable it) — mirrors the _ON_VALUES discipline in release_policy.always_release_enabled.
_ENV_S0_COVERAGE_BINDER = "PG_S0_COVERAGE_BINDER"
_ON_VALUES = frozenset({"1", "true", "yes", "on"})


def s0_coverage_binder_enabled() -> bool:
    """``PG_S0_COVERAGE_BINDER`` (default OFF). Read at CALL TIME (never cached at import).

    ON only on an explicit truthy token ('1'/'true'/'yes'/'on'); any other value (unset, '0',
    'false', 'no', 'off', or a stray 'garbage') keeps the binder OFF and the legacy path byte-identical.
    """
    return os.environ.get(_ENV_S0_COVERAGE_BINDER, "").strip().lower() in _ON_VALUES


def _claim_satisfies_s0_entity(
    claim_text: str,
    claim_evidence_records: Sequence[Mapping[str, Any]],
    entity: Mapping[str, Any],
) -> bool:
    """The full S0 credit conjunction for ONE already-verified claim against ONE S0 entity.

    Both halves must hold (fail-closed otherwise):
      (a) CANONICAL evidence match — the claim cites evidence whose DOI/PMID/full-URL EXACTLY matches
          the entity's declared canonical identifier (``_entity_canonical_match``). Citing the entity's
          source is the binding that ties the warning to the right substance/population pair.
      (b) CONTENT requirements satisfied with SEMANTIC recognition forced ON — every non-concept token
          (population anchor) literal-exact AND the contraindication concept token satisfied by a
          negation-guarded contraindication-DIRECTION phrase. ``semantic=True`` is passed explicitly so
          the binder does NOT depend on the global PG_SWEEP_SEMANTIC_CONTRAINDICATION flag, and does NOT
          mutate it.
    """
    if not any(_entity_canonical_match(dict(entity), rec) for rec in claim_evidence_records):
        return False
    return _content_requirements_satisfied_impl(claim_text, dict(entity), semantic=True)


def bind_s0_coverage(
    *,
    claim_text: str,
    claim_evidence_records: Sequence[Mapping[str, Any]],
    validated_entities: Sequence[tuple[Mapping[str, Any], str, str | None]],
) -> tuple[set[str], set[str]]:
    """Credit S0 safety categories to ONE ALREADY-VERIFIED claim. Pure, additive, fail-closed.

    The CALLER must invoke this ONLY for a strict_verify-VERIFIED claim (the ``verdict == VERIFIED``
    predicate in the credit rule is the caller's responsibility — the build seam only reaches this
    function for ``verification.is_verified`` sentences). This function then applies the remaining
    conjunction (canonical match + population anchor + contraindication-direction + negation guard)
    per S0 entity.

    Returns ``(credited_categories, credited_element_ids)``:
      * ``credited_categories`` — the set of S0 ``s0_category`` strings this claim earns. The caller
        UNIONs these into the claim's ``s0_categories`` (idempotent set-union: harmless if a category
        is already present from the existing literal path or from PG_SWEEP_SEMANTIC_CONTRAINDICATION).
      * ``credited_element_ids`` — the S0 entity ids whose coverage this claim earns, so the caller can
        UNION them into ``covered_element_ids`` (keeping the D8 coverage fraction and the S0 must-cover
        gate in agreement — an S0 category credited as covered should also count its element as covered).

    Crediting NOTHING (two empty sets) is the safe default for any claim that does not satisfy the full
    conjunction — never raised, never a silent over-credit.
    """
    credited_categories: set[str] = set()
    credited_element_ids: set[str] = set()
    for entity, severity, s0_category in validated_entities:
        if severity != _SEVERITY_S0 or s0_category is None:
            continue
        if _claim_satisfies_s0_entity(claim_text, claim_evidence_records, entity):
            credited_categories.add(s0_category)
            credited_element_ids.add(entity[_KEY_ENTITY_ID])
    return credited_categories, credited_element_ids
