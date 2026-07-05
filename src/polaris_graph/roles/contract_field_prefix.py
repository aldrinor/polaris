"""Contract-field label-prefix normalizer (I-deepfix-001 tail-B1 #1344, finding #10). LEAF, PURE.

THE BUG (drb_72, claim 01-002 vs 01-007): two claims carry the IDENTICAL verbatim Acemoglu-Restrepo
robots figure, but one carries a LEAKED per-trial-subsection CONTRACT-FIELD LABEL prefix — the model
echoed the M50 subsection prompt's element label ("Effect estimate WITH uncertainty (CI, SD, or
p-value)") into the sentence as ``Effect estimate with uncertainty: One more robot per thousand
workers reduces ...``. Because the downstream ``_normalize_sentence`` only lowercases + collapses
whitespace, the label survives into (a) the deterministic ``claim_id`` hash (so the twin gets a
DIFFERENT id) and (b) the four-role D8 entailment input (so the two twins can settle to DIVERGENT
verdicts: 01-007 VERIFIED, 01-002 UNSUPPORTED). Consolidation/dedup also never collapses them.

THE FIX: strip a RECOGNIZED contract-field label that appears as a leading ``LABEL:`` prefix at the
START of the claim, BEFORE the claim_id hash and BEFORE the entailment input, and normalize the same
prefix out of the four-role dedup key + the fact-dedup exact-duplicate check. Stripping the label
recovers the ACTUAL claim (the verbatim figure the source stated) — the SAME text the VERIFIED twin
carries — so the twins collapse to one representative + one consistent verdict.

FAITHFULNESS-SAFE (never relaxes the ONE hard gate): the stripped text is a NON-CLAIM contract-field
label, not evidence. Only a CURATED set of labels is recognized, and ONLY when it sits at the very
start of the claim immediately followed by a colon — so legitimate prose that merely contains one of
these words is never touched, and NO number, citation, or claim content is ever removed. The residual
text still passes the UNCHANGED strict_verify / NLI / provenance / span-grounding engine.
"""
from __future__ import annotations

import re

# The M50 per-trial-subsection contract's 7 element labels (multi_section_generator.
# _M50_SUBSECTION_SYSTEM_PROMPT) plus their common natural-language spellings. A leaked label is the
# model echoing one of these as a ``LABEL:`` sentence prefix. Curated + anchored (see module note) so
# a stray occurrence in real prose is never matched. Longest-first is enforced by the regex build.
_CONTRACT_FIELD_LABELS = (
    "effect estimate with uncertainty",
    "effect estimate",
    "primary endpoint",
    "primary outcome",
    "secondary endpoint",
    "baseline characteristics",
    "sample size",
    "population",
    "comparator",
    "timepoint",
    "safety caveat",
    "safety signal",
)

# Build ONE anchored, case-insensitive alternation, longest label first (so "effect estimate with
# uncertainty" wins over "effect estimate"). Matches ``^<ws><LABEL><ws>:<ws>`` only — the leading
# ``^`` anchor is what keeps a mid-sentence mention of a label word untouched.
_LABEL_ALTERNATION = "|".join(
    re.escape(lbl) for lbl in sorted(_CONTRACT_FIELD_LABELS, key=len, reverse=True)
)
_CONTRACT_FIELD_PREFIX_RE = re.compile(
    r"^\s*(?:" + _LABEL_ALTERNATION + r")\s*:\s*",
    re.IGNORECASE,
)


def strip_contract_field_prefix(sentence: str) -> str:
    """Remove a leading recognized contract-field ``LABEL:`` prefix from ``sentence``. PURE.

    Strips at most ONE such prefix (the labels do not chain in the observed leak). Returns the
    input UNCHANGED (byte-identical) when no recognized label prefixes the claim — so a normal
    sentence, or a sentence that merely mentions a label word later on, is never altered. Never
    removes a number, citation, or claim content: the match is anchored to the start and ends at
    the first colon's trailing whitespace."""
    if not sentence:
        return sentence
    return _CONTRACT_FIELD_PREFIX_RE.sub("", sentence, count=1)
