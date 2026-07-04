"""I-deepfix-001 D2 behavioral test — the engine-gated "extension" cross-source relation.

ISOLATED + OFFLINE + $0: no paid API, no GPU, no model download. The certified directional-entailment
engine (``consolidation_nli.entails_directional``) is FAKED via the ``entail_fn`` injection seam the
composer exposes, so no cross-encoder loads. The two verified atoms flow through the DETERMINISTIC short
writer (``build_short_member_sentence``, no LLM) + the production ``verify_sentence_provenance`` (offline
with ``PG_VERIFICATION_MODE=off``), exactly as the non-abstractive render-probe path does in production.

Contract under test (D2 licenses a NEW relation WORD "extension"/"...extending this..." between two atoms
that each ALREADY strict_verify-PASSED and keep their own ``[#ev]`` token):
  (a) a POSITIVE certified directional-entailment verdict -> the connective renders as "extension";
  (b) NEGATIVE CONTROL: no entailment signal (engine returns None/False) -> "neutral", NEVER "extending";
  (c) ENGINE-GATED proof: flip the SAME pair's signal off (verdict False, OR the PG_CROSS_SOURCE_EXTENSION
      flag off) -> downgrades to "neutral" — proving the word is engine-licensed, never free-form/LLM;
  (d) CONFLICT PRECEDENCE: a pair with BOTH a ContradictionEdge and an entailment signal -> "conflict";
  (e) FAITHFULNESS + KEEP-ALL: both atoms still strict_verify-PASS and keep their [#ev]; the extension
      unit cites a member of BOTH baskets (no basket dropped).

Certified signal cited: ``consolidation_nli.entails_directional(premise, hypothesis)`` (consolidation_nli.py
~:346) — the one-directional NLI counterpart to the bidirectional consolidation merge, reading ONLY the
forward logits at the same entailment-argmax threshold ``_entails``. The composer asks it "does clause_b
(the elaborating, second clause) entail clause_a?" so the rendered "A; extending this, B" is faithful.

RED on the pre-D2 snapshot: ``license_relation`` had no ``directional_entails`` kwarg and the composer had
no ``entail_fn`` kwarg, so every call below raises ``TypeError`` (unexpected keyword argument) or asserts
"neutral" where D2 now yields "extension" — the module cannot license "extension" at all pre-change.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# Repo root on path.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no judge calls, no network entailment on the per-clause verify.
os.environ["PG_VERIFICATION_MODE"] = "off"
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

from src.polaris_graph.generator.cross_source_synthesis import (  # noqa: E402
    LICENSED_CONNECTIVES,
    compose_cross_source_analytical_units,
    cross_source_extension_enabled,
    license_relation,
)
from src.polaris_graph.generator.verified_compose import (  # noqa: E402
    build_short_member_sentence,
    _resolved_spans,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
)

# ── Connective phrase constants (asserted verbatim so a phrase drift is caught) ───────────────────────
_EXTENSION_PHRASE = LICENSED_CONNECTIVES["extension"].strip()   # "extending this,"
_NEUTRAL_PHRASE = LICENSED_CONNECTIVES["neutral"].strip()       # "separately,"
_CONFLICT_PHRASE = LICENSED_CONNECTIVES["conflict"].strip()     # "in contrast,"
_AGREEMENT_PHRASE = LICENSED_CONNECTIVES["agreement"].strip()   # "consistent with this,"

# ── Synthetic shared-anchor pair: clause_b is a proper SUPERSET/elaboration of clause_a ───────────────
# The two pool rows are single, verbatim, self-grounding sentences (the short writer emits a verbatim
# prefix carrying the member's real global offsets, so each clause strict_verify-PASSES trivially).
_EV_A = "d2_ev_base"
_EV_B = "d2_ev_extended"
_QUOTE_A = "Automation raised manufacturing productivity."
_QUOTE_B = "Automation raised manufacturing productivity by fifteen percent across 2024."


def _pool() -> dict:
    return {
        _EV_A: {"direct_quote": _QUOTE_A, "statement": _QUOTE_A},
        _EV_B: {"direct_quote": _QUOTE_B, "statement": _QUOTE_B},
    }


def _member(evidence_id: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=f"origin::{evidence_id}",
        credibility_weight=1.0,
        authority_score=1.0,
        span=(0, len(quote)),
        direct_quote=quote,
        span_verdict="SUPPORTS",
        member_tier="ENTAILMENT_VERIFIED",
    )


def _basket(cluster_id: str, evidence_id: str, quote: str) -> ClaimBasket:
    # SHARED subject+predicate anchor so the two baskets are pairing CANDIDATES; DISTINCT clusters so the
    # composer treats them as a real cross-SOURCE pair.
    return ClaimBasket(
        claim_cluster_id=cluster_id,
        claim_text=quote,
        subject="automation productivity",
        predicate="raised",
        supporting_members=[_member(evidence_id, quote)],
        refuter_cluster_ids=(),
        weight_mass=1.0,
        total_clustered_origin_count=1,
        verified_support_origin_count=1,
        basket_verdict="SUPPORTED",
    )


_CID_A = "d2_cluster_a"
_CID_B = "d2_cluster_b"


def _section() -> list:
    return [_basket(_CID_A, _EV_A, _QUOTE_A), _basket(_CID_B, _EV_B, _QUOTE_B)]


def _short_writer(basket, pool):
    """DETERMINISTIC no-LLM short writer (the production render-probe writer)."""
    return build_short_member_sentence(basket, pool)


def _make_edge(a, b):
    class _E:
        claim_cluster_ids = (a, b)
        source = "semantic"
        severity = "review"
    return _E()


# Fake certified directional-entailment engines (the injection seam; NO GPU / NO model download).
def _content_words(text) -> set:
    return set(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _entail_superset(premise, hypothesis):
    """DIRECTIONAL fake NLI: ``premise`` entails ``hypothesis`` iff every content word of the hypothesis
    is present in the premise (a SUPERSET premise entails its SUBSET). Non-symmetric — mirrors real NLI
    on the synthetic pair here: clause_b ("...by fifteen percent across 2024") is a proper superset of
    clause_a, so FORWARD (b entails a)=True and REVERSE (a entails b)=False -> a PROPER extension."""
    return _content_words(hypothesis).issubset(_content_words(premise))


def _entail_equivalent(_premise, _hypothesis):
    return True   # BIDIRECTIONAL: True in BOTH directions -> equivalence (adds nothing) -> NOT extension


def _entail_no(_premise, _hypothesis):
    return False  # a CONFIDENT non-entailment


def _entail_unknown(_premise, _hypothesis):
    return None   # the fail-closed / infra-fault sentinel


def _compose(section, *, entail_fn=None, edges=None, agree_map=None):
    return compose_cross_source_analytical_units(
        section, _pool(),
        writer_fn=_short_writer, verify_fn=verify_sentence_provenance,
        edges=edges, equiv_clusters=None, agree_map=agree_map, entail_fn=entail_fn,
    )


# ── (a) POSITIVE directional entailment -> the connective renders as "extension". ─────────────────────
def test_a_positive_directional_entailment_renders_extension():
    # Unit level: license_relation returns "extension" ONLY on directional_entails=True.
    assert license_relation(_CID_A, _CID_B, directional_entails=True) == "extension"
    # Composer level: the rendered analytical sentence carries the "extending this" connective.
    units = _compose(_section(), entail_fn=_entail_superset)
    assert units, "a positive directional-entailment pair must yield an analytical unit"
    unit = units[0]
    assert _EXTENSION_PHRASE in unit, f"expected extension connective; got: {unit!r}"
    # It must NOT masquerade as any other relation word.
    assert _NEUTRAL_PHRASE not in unit
    assert _CONFLICT_PHRASE not in unit
    assert _AGREEMENT_PHRASE not in unit


# ── (b) NEGATIVE CONTROL: no entailment signal -> "neutral", NEVER "extending". ───────────────────────
def test_b_no_signal_is_neutral_never_extends():
    # license_relation: None and False must NOT license extension.
    assert license_relation(_CID_A, _CID_B, directional_entails=None) == "neutral"
    assert license_relation(_CID_A, _CID_B, directional_entails=False) == "neutral"
    # Composer: an engine that returns None -> neutral connective, never "extending this".
    units_none = _compose(_section(), entail_fn=_entail_unknown)
    assert units_none, "the pair still yields a (neutral) unit"
    assert _EXTENSION_PHRASE not in units_none[0]
    assert _NEUTRAL_PHRASE in units_none[0]
    # A confident non-entailment (False) is likewise neutral, never an extension.
    units_false = _compose(_section(), entail_fn=_entail_no)
    assert units_false
    assert _EXTENSION_PHRASE not in units_false[0]
    assert _NEUTRAL_PHRASE in units_false[0]


# ── (c) ENGINE-GATED proof: a pair that HAD extension downgrades to neutral when the signal is off. ───
def test_c_engine_gated_flip_downgrades_to_neutral():
    # Baseline: a PROPER directional signal (forward True, reverse False) -> extension.
    on = _compose(_section(), entail_fn=_entail_superset)
    assert on and _EXTENSION_PHRASE in on[0]

    # Flip the ENGINE verdict off (same pair, same anchors) -> neutral. Proves it is the engine's verdict
    # that licenses the word, not a free-form / LLM guess baked into the composer.
    off_engine = _compose(_section(), entail_fn=_entail_no)
    assert off_engine and _EXTENSION_PHRASE not in off_engine[0]
    assert _NEUTRAL_PHRASE in off_engine[0]

    # Flip the CONFIG flag off (PG_CROSS_SOURCE_EXTENSION=0): even a True-returning engine cannot license
    # extension — the composer never asks it. Restores the pre-D2 behavior exactly.
    _prev = os.environ.get("PG_CROSS_SOURCE_EXTENSION")
    os.environ["PG_CROSS_SOURCE_EXTENSION"] = "0"
    try:
        assert cross_source_extension_enabled() is False
        off_flag = _compose(_section(), entail_fn=_entail_superset)
    finally:
        if _prev is None:
            os.environ.pop("PG_CROSS_SOURCE_EXTENSION", None)
        else:
            os.environ["PG_CROSS_SOURCE_EXTENSION"] = _prev
    assert off_flag and _EXTENSION_PHRASE not in off_flag[0]
    assert _NEUTRAL_PHRASE in off_flag[0]
    # And the flag is back ON by default.
    assert cross_source_extension_enabled() is True


# ── (d) CONFLICT PRECEDENCE: a ContradictionEdge beats an entailment signal. ──────────────────────────
def test_d_conflict_beats_extension():
    # Unit level: edge + directional_entails=True -> conflict wins.
    assert license_relation(
        _CID_A, _CID_B, edges=[_make_edge(_CID_A, _CID_B)], directional_entails=True,
    ) == "conflict"
    # Composer level: the rendered sentence is a conflict, never an extension — even though the
    # directional signal would license extension on its own (forward True, reverse False).
    units = _compose(_section(), entail_fn=_entail_superset, edges=[_make_edge(_CID_A, _CID_B)])
    assert units
    assert _CONFLICT_PHRASE in units[0]
    assert _EXTENSION_PHRASE not in units[0]


# ── Agreement precedence: a bidirectional-equivalence agreement is "consistent with", not "extension". ─
def test_d2_agreement_beats_extension():
    assert license_relation(
        _CID_A, _CID_B, agree_map={_CID_A: {_CID_B}}, directional_entails=True,
    ) == "agreement"


# ── (f) EQUIVALENCE: a bidirectional paraphrase is AGREEMENT (L3), never "extending this". ────────────
def test_f_equivalence_reverse_also_entails_is_agreement_never_extends():
    """A pair where B entails A AND A entails B (an equivalent paraphrase) adds NOTHING NEW — the faithful
    word is AGREEMENT ("consistent with this"), never "extending this". The extension equivalence guard
    still requires the REVERSE direction to be a CONFIDENT non-entailment, so a reverse also-True must NOT
    license extension. Before L3 the composer had no live bidirectional-agreement signal, so an equivalence
    fell to neutral; L3 (COVERAGE) wires the explicit both-directions-entail signal, so the SAME equivalence
    now renders AGREEMENT. This is the exact fabrication class the gate exists for: a wrong relation word
    between two verified facts is never rendered — the equivalence is surfaced as the faithful agreement."""
    from src.polaris_graph.generator.cross_source_synthesis import (
        _directional_extension_signal,
        _bidirectional_agreement_signal,
    )
    # Signal level: both directions True (equivalence) MUST NOT license extension...
    sig = _directional_extension_signal(_QUOTE_A, _QUOTE_B, _entail_equivalent)
    assert sig is not True, "equivalence (reverse also entails) must not license extension"
    # ...but it DOES license the L3 bidirectional-equivalence agreement.
    agr = _bidirectional_agreement_signal(_QUOTE_A, _QUOTE_B, _entail_equivalent)
    assert agr is True, "equivalence (both directions entail) must license agreement"
    # Composer level: an equivalence engine renders AGREEMENT, never "extending this", never neutral.
    units = _compose(_section(), entail_fn=_entail_equivalent)
    assert units, "the pair still yields an (agreement) unit"
    assert _EXTENSION_PHRASE not in units[0]
    assert _AGREEMENT_PHRASE in units[0]
    assert _NEUTRAL_PHRASE not in units[0]
    # Contrast: the PROPER one-way signal DOES license extension on the SAME pair (the signals are mutually
    # exclusive — extension excludes the equivalence case, agreement excludes the proper-superset case).
    proper = _compose(_section(), entail_fn=_entail_superset)
    assert proper and _EXTENSION_PHRASE in proper[0]
    assert _AGREEMENT_PHRASE not in proper[0]


# ── (e) FAITHFULNESS + KEEP-ALL: both atoms strict_verify-PASS, keep [#ev], both baskets cited. ───────
def test_e_faithfulness_and_keep_all_on_extension_unit():
    units = _compose(_section(), entail_fn=_entail_superset)
    assert units and _EXTENSION_PHRASE in units[0]
    unit = units[0]

    # TWO distinct [#ev] tokens from the TWO baskets survive in the extension sentence.
    spans = _resolved_spans(unit)
    ev_ids = {t[0] for t in spans}
    assert ev_ids == {_EV_A, _EV_B}, f"extension unit must cite BOTH baskets; got {sorted(ev_ids)}"

    # Each atom's own clause still strict_verify-PASSES (rebuild each token into a standalone sentence and
    # re-run the UNCHANGED production verifier). The extension connective carries NO token, so the gate is
    # exactly per-clause as before.
    import re as _re
    tok_re = _re.compile(r"\[#ev:(?P<ev>[A-Za-z0-9_]+):(?P<s>\d+)-(?P<e>\d+)\]")
    toks = list(tok_re.finditer(unit))
    assert len(toks) >= 2, f"expected >=2 [#ev] tokens; got {len(toks)}"
    pool = _pool()
    for mt in toks:
        ev, s, e = mt.group("ev"), int(mt.group("s")), int(mt.group("e"))
        span_text = str(pool[ev]["direct_quote"])[s:e]
        clause_sentence = f"{span_text.strip()} [#ev:{ev}:{s}-{e}]."
        res = verify_sentence_provenance(clause_sentence, pool)
        assert bool(getattr(res, "is_verified", False)), (
            f"atom clause for {ev} must re-pass strict_verify: {clause_sentence!r}"
        )

    # A foreign-span citation still FAILS the UNCHANGED engine (D2 did not relax it).
    bad = "Some fabricated extension [#ev:__not_in_pool__:0-40]."
    bad_res = verify_sentence_provenance(bad, pool)
    assert not bool(getattr(bad_res, "is_verified", False)), "foreign-id sentence must be rejected"

    # KEEP-ALL: both baskets' members are cited (nothing dropped to render the relation).
    assert _EV_A in ev_ids and _EV_B in ev_ids


# ── Production wiring: the default engine IS the certified directional-entailment function. ────────────
def test_default_engine_is_certified_entails_directional():
    from src.polaris_graph.generator.cross_source_synthesis import _default_entail_fn
    from src.polaris_graph.synthesis import consolidation_nli
    fn = _default_entail_fn()
    # Import-only (lazy model): the default signal is the certified engine, not a free-form judge.
    assert fn is consolidation_nli.entails_directional


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
