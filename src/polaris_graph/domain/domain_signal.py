"""B9 domain-generalization spine — the deterministic ``is_clinical`` backbone.

POLARIS is GENERAL by default; clinical rigor is a DETECTED specialization
layered on top (dual-agreed B1-B10 plan, B9 "the spine"). The historical
failure (the 2,738 junk clinical-contradiction flags on a labor-displacement
report) was NOT "a domain param wasn't read" alone — it was that the clinical
predicate/lexicon logic fired UNCONDITIONALLY on every domain. The fix is a
single, deterministic, NO-LLM ``is_clinical`` signal threaded into every
consumer (qualitative_conflict_detector, contradiction_detector, finding_dedup,
multi_section_generator). When ``is_clinical`` is False the clinical-only
predicate unions / NegEx lexicon / clinical few-shots do not apply; the
domain-agnostic path runs instead. The faithfulness engine (strict_verify /
span-grounding / NLI / 4-role) is unchanged and remains the only hard gate.

Design rules (operator-locked B9 constraints):

1. **DETERMINISTIC, NO LLM.** This is the backbone every consumer reads; it
   must be pure, offline, and cheap. The LLM domain/intent classifier in
   ``scope_gate`` is a SECONDARY augmentation that degrades to this signal.
2. **Clinical only on a POSITIVE signal.** ``is_clinical`` is True iff the
   domain is the explicit ``"clinical"`` token OR (when the domain is
   blank/unknown) a clinical intervention OR a clinical population marker is
   positively present in the supplied text. Any non-clinical KNOWN domain
   (workforce / policy / tech / economics / general / custom / ...) is
   ``False`` regardless of text — a labor report that happens to quote the
   word "mortality" must NOT route clinical.
3. **Byte-identity for clinical.** A clinical run today passes
   ``domain="clinical"`` (the sweep reads ``q["domain"]``) → this returns True →
   the clinical path is taken unchanged. The ``domain=None`` default (tests +
   legacy callers) falls back to the text-signal probe so a genuinely clinical
   corpus with no domain hint still routes clinical (no regression).
4. **Never abort.** This module only classifies; it never raises on input and
   never holds a report. Unknown → general.

LAW VI: the clinical recognizers reused here are config-driven (the
``scope_gate`` intervention recognizer reads
``config/clinical_safety/intervention_recognition.yaml``).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# The canonical clinical-domain token. The sweep supplies a per-query
# ``domain`` string; "clinical" is the ONE value that forces the clinical
# specialization. Everything else (incl. "" / None / "general" / "workforce" /
# "policy" / "tech" / "economics" / "custom") is non-clinical.
CLINICAL_DOMAIN = "clinical"

# The general default. A blank / unknown / unrecognised domain routes here —
# NEVER to clinical (operator-locked: "" -> general).
GENERAL_DOMAIN = "general"


def normalize_domain(domain: Optional[str]) -> str:
    """Lowercase + trim a domain string; blank/None -> ``GENERAL_DOMAIN``.

    Pure. Never raises. The single place "" -> general is enforced so no
    consumer accidentally falls back to clinical.
    """
    d = (domain or "").strip().lower()
    return d if d else GENERAL_DOMAIN


def _row_texts(evidence: Optional[Iterable[Any]]) -> list[str]:
    """Best-effort text fields from evidence rows (direct_quote/statement/text/
    title). Tolerates dicts and missing keys; never raises."""
    texts: list[str] = []
    for ev in evidence or []:
        if not isinstance(ev, dict):
            continue
        for key in ("direct_quote", "statement", "text", "title"):
            val = ev.get(key)
            if val:
                texts.append(str(val))
    return texts


# Clinical endpoint / safety vocabulary — a clinical SIGNAL even when no drug is
# named in the same span (e.g. "Achieved 14.9% weight loss from baseline.").
# These are clinical-SPECIFIC; a non-clinical economics / labor / policy corpus
# does not use them. Kept here (not imported from contradiction_detector) to
# avoid an import cycle. Lowercase substring match.
_CLINICAL_ENDPOINT_TERMS: tuple[str, ...] = (
    "weight loss", "hba1c", "a1c", "blood pressure", "ldl", "cholesterol",
    "mace", "all-cause mortality", "cardiovascular", "adverse event",
    "serious adverse event", "contraindicated", "contraindication",
    "drug interaction", "hypoglycemia", "pancreatitis",
    "discontinuation rate", "placebo-controlled", "randomized controlled",
    "double-blind", "phase 3 trial", "phase iii trial", "efficacy endpoint",
    "primary endpoint", "comorbidit",
)

# Clinical-SPECIFIC population markers (NOT generic "adults"/"children"/
# "elderly", which appear in non-clinical labor/policy corpora too — Codex P1.1).
# A disease/condition population is a positive clinical signal; a bare age band
# is not. Lowercase substring match.
_CLINICAL_POPULATION_TERMS: tuple[str, ...] = (
    "type 1 diabetes", "type 2 diabetes", "t1dm", "t2dm", "diabetic",
    "obesity", "overweight", "obese",
    "chronic kidney disease", "ckd", "renal impairment",
    "heart failure", "nafld", "nash", "mash", "masld",
    "pregnant", "postmenopausal", "premenopausal",
    "patients with", "in patients", "the patient",
)


def _has_clinical_text_signal(evidence: Optional[Iterable[Any]]) -> bool:
    """True iff a clinical INTERVENTION, clinical-SPECIFIC condition population,
    or clinical ENDPOINT/safety marker is positively present in the evidence
    text.

    Codex P1.1: a GENERIC age-band population ("adults"/"children"/"elderly")
    does NOT count — those appear in non-clinical labor/policy corpora too. A
    positive clinical signal requires a drug, a disease/condition population, or
    clinical endpoint vocabulary. Reuses the ``scope_gate`` config-driven
    intervention recognizer (INN stems + known-name seed list, LAW VI). Import
    is local to avoid a heavy import cycle; recognizer/config errors are
    swallowed (fail-soft, never clinical-by-error).
    """
    texts = _row_texts(evidence)
    if not texts:
        return False
    blob_l = "\n".join(texts).lower()
    # Clinical endpoint / safety vocabulary (cheap substring; no config).
    for term in _CLINICAL_ENDPOINT_TERMS:
        if term in blob_l:
            return True
    # Clinical-SPECIFIC condition population (NOT a bare age band).
    for term in _CLINICAL_POPULATION_TERMS:
        if term in blob_l:
            return True
    # Intervention (config-driven drug recognizer). Probe per-row so an early
    # hit short-circuits; recognizer/config errors are non-fatal.
    try:
        from src.polaris_graph.nodes.scope_gate import _intervention_present
        for text in texts:
            if _intervention_present(text):
                return True
    except Exception:
        return False
    return False


def is_clinical_domain(
    domain: Optional[str],
    evidence: Optional[Iterable[Any]] = None,
) -> bool:
    """Return True iff the run should take the CLINICAL specialization.

    Deterministic, no LLM, never raises. The single ``is_clinical`` signal
    every B9 consumer reads.

    Routing (in order):
      * ``domain == "clinical"`` (case/space-insensitive) -> True. This is the
        explicit positive route the sweep takes for clinical questions, so the
        clinical path is byte-identical to today.
      * Any OTHER known/non-blank domain (workforce/policy/tech/economics/
        general/custom/...) -> False. A non-clinical domain NEVER routes
        clinical even if the text mentions a clinical-sounding word.
      * Blank / None domain -> probe the evidence text for a positive clinical
        intervention or population signal; True only on a positive signal,
        else False. This keeps a genuinely-clinical corpus with no domain hint
        (tests / legacy callers that pass ``domain=None``) on the clinical
        path with no regression, while a blank non-clinical corpus stays
        general.
    """
    d = (domain or "").strip().lower()
    if d == CLINICAL_DOMAIN:
        return True
    if d:
        # A positively-named non-clinical domain is authoritative.
        return False
    # Blank/unknown domain: degrade to a positive text signal, never to
    # clinical-by-default.
    return _has_clinical_text_signal(evidence)
