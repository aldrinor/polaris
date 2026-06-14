"""F06 (P1, GH I-arch-004) — Sentinel atom-decomposition completeness floor.

THE BUG: `parse_sentinel_decomposition` gates a GROUNDED ("supported") verdict on the model's OWN
atom bookkeeping (non-empty atoms + unsupported_atoms==0 + no per-atom "unsupported" status) but
NEVER checks that the atoms COVER every assertion in the cited sentence. A half-decomposed clinical
claim — efficacy clause atomized + supported, contraindication clause silently dropped (never
atomized, never checked) — therefore passes as GROUNDED. The dropped clause carries the clinical
risk (§-1.1 lethal: a missed contraindication).

THE FIX (F06): an INDEPENDENT atom-coverage cross-check derives clauses FROM THE CLAIM SENTENCE
(not the model's verdict/atoms) and requires every substantive clause to be represented by an atom.
An uncovered clause -> the Sentinel verdict is DOWNGRADED to UNGROUNDED (STRICTER), and the LOCKED
fail-closed composition then downgrades a Judge VERIFIED/PARTIAL to UNSUPPORTED.

Gated behind `PG_SENTINEL_ATOM_COVERAGE` (default OFF -> byte-identical; the cert run slate turns it
ON). Pure logic, no model, no network.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.role_pipeline import run_claim_pipeline
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sentinel_contract import (
    SentinelResult,
    SentinelVerdict,
    atom_coverage_complete,
    parse_sentinel_decomposition,
    sentinel_atom_coverage_enabled,
)

_COVERAGE_FLAG = "PG_SENTINEL_ATOM_COVERAGE"

# A 2-assertion clinical claim: an efficacy clause AND a contraindication clause. This is the exact
# shape the bug hides in — the model atomizes only the efficacy clause and drops the contraindication.
_TWO_CLAUSE_CLAIM = (
    "Tirzepatide reduced HbA1c by 2.3 percentage points, "
    "but it is contraindicated in patients with pancreatitis."
)

# Decomposition output that ONLY atomized the EFFICACY clause (the contraindication clause is
# silently dropped — never atomized, never checked). The model's own bookkeeping is clean:
# unsupported_atoms == 0, the one atom is "supported". The OLD parser passes this as GROUNDED.
_HALF_DECOMPOSED_RAW = json.dumps(
    {
        "verdict": "supported",
        "unsupported_atoms": 0,
        "atoms": [
            {
                "atom": "Tirzepatide reduced HbA1c by 2.3 percentage points",
                "type": "mechanism",
                "status": "supported",
                "why": "span states the HbA1c reduction",
            }
        ],
    }
)

# The COMPLETE decomposition: BOTH the efficacy clause AND the contraindication clause are atomized
# and supported. The no-false-drop control.
_FULLY_DECOMPOSED_RAW = json.dumps(
    {
        "verdict": "supported",
        "unsupported_atoms": 0,
        "atoms": [
            {
                "atom": "Tirzepatide reduced HbA1c by 2.3 percentage points",
                "type": "mechanism",
                "status": "supported",
                "why": "span states the HbA1c reduction",
            },
            {
                "atom": "Tirzepatide is contraindicated in patients with pancreatitis",
                "type": "mechanism",
                "status": "supported",
                "why": "span states the pancreatitis contraindication",
            },
        ],
    }
)


# ===========================================================================================
# Part 1 — the PURE coverage helper (`atom_coverage_complete`): the heart of the cross-check.
# ===========================================================================================
def test_helper_uncovered_clause_is_incomplete() -> None:
    """THE BUG, isolated: a 2-clause claim whose atoms cover ONLY clause 1 is INCOMPLETE."""
    atoms = json.loads(_HALF_DECOMPOSED_RAW)["atoms"]
    assert atom_coverage_complete(_TWO_CLAUSE_CLAIM, atoms) is False


def test_helper_all_clauses_covered_is_complete() -> None:
    """THE NO-FALSE-DROP control: both clauses atomized -> coverage is complete."""
    atoms = json.loads(_FULLY_DECOMPOSED_RAW)["atoms"]
    assert atom_coverage_complete(_TWO_CLAUSE_CLAIM, atoms) is True


def test_helper_single_clause_claim_fully_covered() -> None:
    """A single-clause claim whose one atom covers it is complete (no false-drop on simple claims)."""
    claim = "Tirzepatide reduced HbA1c by 2.3 percentage points."
    atoms = [{"atom": "Tirzepatide reduced HbA1c by 2.3 percentage points", "status": "supported"}]
    assert atom_coverage_complete(claim, atoms) is True


def test_helper_none_atoms_against_substantive_claim_is_incomplete() -> None:
    """FAIL-CLOSED: no atom set at all, against a claim with a real assertion -> incomplete."""
    assert atom_coverage_complete(_TWO_CLAUSE_CLAIM, None) is False
    assert atom_coverage_complete(_TWO_CLAUSE_CLAIM, []) is False


def test_helper_non_substantive_claim_imposes_no_constraint() -> None:
    """A claim with no checkable assertion (bare numeral / function words) -> coverage adds nothing."""
    assert atom_coverage_complete("5.0", None) is True
    assert atom_coverage_complete("It is.", []) is True
    assert atom_coverage_complete("", None) is True


def test_helper_numeric_list_not_oversplit_no_false_drop() -> None:
    """Comma is NOT a clause split marker: a dose list stays ONE clause and is covered by one atom
    (guards against the over-split false-drop the advisor flagged)."""
    claim = "Tirzepatide was dosed at 5 mg, 10 mg, and 15 mg in the trial."
    atoms = [{"atom": "Tirzepatide was dosed at 5 mg, 10 mg, and 15 mg", "status": "supported"}]
    assert atom_coverage_complete(claim, atoms) is True


def test_helper_subordinating_connective_splits_clause() -> None:
    """An 'although' subordinating clause is split out and must be covered independently."""
    claim = (
        "The drug lowered blood pressure significantly, "
        "although it increased the risk of hyperkalemia."
    )
    # Atoms cover only the blood-pressure clause -> the hyperkalemia clause is uncovered.
    half = [{"atom": "The drug lowered blood pressure significantly", "status": "supported"}]
    assert atom_coverage_complete(claim, half) is False
    # Both clauses atomized -> complete.
    full = half + [{"atom": "the drug increased the risk of hyperkalemia", "status": "supported"}]
    assert atom_coverage_complete(claim, full) is True


def test_helper_malformed_atom_entries_ignored_safely() -> None:
    """Non-dict atom entries contribute nothing and never crash; an uncovered clause still fails."""
    atoms = ["not a dict", {"atom": "Tirzepatide reduced HbA1c by 2.3 percentage points"}, None]
    assert atom_coverage_complete(_TWO_CLAUSE_CLAIM, atoms) is False  # contraindication uncovered


# --- Codex diff-gate iter-1 P1.1: shared-backbone clauses cannot launder a dropped clause ----------
def test_helper_codex_p1_1_shared_backbone_dropped_clause_is_incomplete() -> None:
    """Codex iter-1 P1.1 (exact wording): 'an omitted contraindication clause that repeats the same
    drug/population terms as the supported efficacy atom can still be treated as covered.' The two
    clauses SHARE the drug+population backbone (tirzepatide / patients); the efficacy-only atom must
    NOT cover the contraindication clause, because distinctive-word coverage discounts the backbone and
    the contraindication's OWN risk terms (contraindicated/pancreatitis) are absent from the atom."""
    claim = (
        "Tirzepatide reduced HbA1c in patients with diabetes, "
        "but tirzepatide is contraindicated in patients with pancreatitis."
    )
    efficacy_only = [
        {"atom": "Tirzepatide reduced HbA1c in patients with diabetes", "status": "supported"}
    ]
    assert atom_coverage_complete(claim, efficacy_only) is False
    # Control: atomize the contraindication clause too -> covered.
    full = efficacy_only + [
        {"atom": "tirzepatide is contraindicated in patients with pancreatitis", "status": "supported"}
    ]
    assert atom_coverage_complete(claim, full) is True


# --- Codex diff-gate iter-1 P1.2: coordinating 'and' must split coordinated predicates -------------
def test_helper_codex_p1_2_coordinating_and_splits_predicate() -> None:
    """Codex iter-1 P1.2 (exact wording): 'Drug reduced HbA1c and is contraindicated in pancreatitis
    remains one clause and can pass coverage with only the efficacy atom.' The predicate-bearing 'and'
    now splits the conjunct, so the efficacy-only atom leaves the contraindication conjunct uncovered."""
    claim = "The drug reduced HbA1c and is contraindicated in pancreatitis."
    efficacy_only = [{"atom": "The drug reduced HbA1c", "status": "supported"}]
    assert atom_coverage_complete(claim, efficacy_only) is False
    # Control: both conjuncts atomized -> covered.
    full = efficacy_only + [
        {"atom": "the drug is contraindicated in pancreatitis", "status": "supported"}
    ]
    assert atom_coverage_complete(claim, full) is True


def test_helper_noun_coordination_and_not_oversplit() -> None:
    """A NOUN coordination 'HbA1c and body weight' (no leading finite verb after 'and') is NOT split,
    so one atom covering the whole assertion keeps it GROUNDED — guards the predicate-and constraint
    against re-breaking noun/numeric 'and' (the false-drop the P1.2 fix must avoid)."""
    claim = "The drug reduced HbA1c and body weight significantly."
    atom = [{"atom": "The drug reduced HbA1c and body weight significantly", "status": "supported"}]
    assert atom_coverage_complete(claim, atom) is True


def test_helper_incidental_word_tolerance_no_false_drop() -> None:
    """Case-5 canary: a faithful atom may drop ONE incidental distinctive word ('trial') and the
    clause still counts covered (the miss tolerance). This is the constant that must stay green while
    the dropped-contraindication cases (2 missing risk words) fail."""
    claim = "Tirzepatide was dosed at 5 mg, 10 mg, and 15 mg in the trial."
    # Atom omits "trial" (1 incidental distinctive miss) but covers dose/drug.
    atom = [{"atom": "Tirzepatide was dosed at 5 mg, 10 mg, and 15 mg", "status": "supported"}]
    assert atom_coverage_complete(claim, atom) is True


# --- Codex diff-gate iter-2 P1: a single-distinctive-word safety predicate cannot be waived --------
def test_helper_codex_p1_iter2_one_word_contraindication_not_waived() -> None:
    """Codex iter-2 P1 (exact case): 'The drug reduced HbA1c and is contraindicated.' The
    contraindication conjunct's only distinctive word is 'contraindicated'. It must NOT be (a) skipped
    by the min-content threshold nor (b) waived by the incidental-miss tolerance. A SINGLE-distinctive-
    word clause gets ZERO tolerance, so an efficacy-only atom leaves it uncovered -> incomplete."""
    claim = "The drug reduced HbA1c and is contraindicated."
    efficacy_only = [{"atom": "The drug reduced HbA1c", "status": "supported"}]
    assert atom_coverage_complete(claim, efficacy_only) is False
    # Control: atomize the contraindication conjunct too -> covered.
    full = efficacy_only + [{"atom": "the drug is contraindicated", "status": "supported"}]
    assert atom_coverage_complete(claim, full) is True


def test_helper_codex_p1_iter2_one_word_shared_condition_variant() -> None:
    """Codex iter-2 P1 'shared-condition variant where only contraindicated is distinctive': both
    clauses share the drug+condition backbone, leaving 'contraindicated' as the contraindication
    clause's sole distinctive word. ZERO tolerance on the size-1 distinctive set -> efficacy-only atom
    -> incomplete."""
    claim = (
        "Metformin is recommended in patients with diabetes "
        "but metformin is contraindicated in patients with diabetes and renal failure."
    )
    # Atom covers only the recommended clause; "contraindicated" (+ "renal", "failure") are the
    # contraindication clause's distinctive words and are absent.
    efficacy_only = [
        {"atom": "Metformin is recommended in patients with diabetes", "status": "supported"}
    ]
    assert atom_coverage_complete(claim, efficacy_only) is False


# ===========================================================================================
# Part 2 — flag helper.
# ===========================================================================================
def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv(_COVERAGE_FLAG, raising=False)
    assert sentinel_atom_coverage_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", "On"])
def test_flag_truthy_values_enable(monkeypatch, val) -> None:
    monkeypatch.setenv(_COVERAGE_FLAG, val)
    assert sentinel_atom_coverage_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_flag_falsy_values_disabled(monkeypatch, val) -> None:
    monkeypatch.setenv(_COVERAGE_FLAG, val)
    assert sentinel_atom_coverage_enabled() is False


# ===========================================================================================
# Part 3 — the parser is UNCHANGED: the half-decomposed claim STILL parses GROUNDED at the
# contract level (proving F06 is an INDEPENDENT cross-check layered above, not a parser edit).
# ===========================================================================================
def test_parser_still_passes_half_decomposed_as_grounded() -> None:
    """The decomposition CONTRACT (model bookkeeping) cannot see the dropped clause — it still
    returns GROUNDED. THAT is precisely why the F06 coverage cross-check is needed downstream."""
    result = parse_sentinel_decomposition(_HALF_DECOMPOSED_RAW)
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    assert result.atoms is not None and len(result.atoms) == 1


# ===========================================================================================
# Part 4 — END-TO-END through run_claim_pipeline: the ACCEPT criterion.
# A MockTransport that emits the half-decomposed Sentinel output + a Judge VERIFIED. With the flag
# ON the claim must resolve UNGROUNDED (final_verdict NOT VERIFIED); with the flag OFF it stays
# VERIFIED (byte-identical).
# ===========================================================================================
_MODEL_SLUGS = {
    "mirror": "cohere/command-a-plus",
    "sentinel": "minimax/minimax-m2",
    "judge": "qwen/qwen3.6-35b-a3b",
}
_EVIDENCE = [
    EvidenceDocument(
        doc_id="doc1",
        text=(
            "Tirzepatide reduced HbA1c by 2.3 percentage points. "
            "It is contraindicated in patients with pancreatitis."
        ),
    )
]
_TIMESTAMP = "2026-06-14T00:00:00Z"


class _CoverageMockTransport:
    """Mock RoleTransport: Mirror grounds on doc1; Sentinel emits a configurable decomposition JSON;
    Judge returns VERIFIED. Forces decomposition mode via the minimax sentinel slug default."""

    def __init__(self, *, sentinel_raw: str) -> None:
        self._sentinel_raw = sentinel_raw
        self.seen_roles: list[str] = []

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.seen_roles.append(request.role)
        if request.role == "mirror":
            if "pass2_input" in request.params:
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=("doc1",))],
            )
        if request.role == "sentinel":
            return RoleResponse(raw_text=self._sentinel_raw, served_model=request.model_slug)
        if request.role == "judge":
            return RoleResponse(raw_text="VERIFIED", served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


def _run(transport):
    return run_claim_pipeline(
        transport,
        claim_id="claim-f06",
        claim=_TWO_CLAUSE_CLAIM,
        evidence_documents=_EVIDENCE,
        severity="S0",
        s0_categories=[],
        model_slugs=_MODEL_SLUGS,
        timestamp=_TIMESTAMP,
    )


@pytest.fixture
def _decomposition_env(monkeypatch):
    """Pin the decomposition Sentinel mode (the minimax lock default) so `atoms` is populated."""
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "decomposition")
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)


def test_accept_half_decomposed_resolves_ungrounded_flag_on(monkeypatch, _decomposition_env) -> None:
    """THE ACCEPT CRITERION: a 2-assertion sentence where the contraindication clause is unsupported/
    un-atomized and the Sentinel returned only the efficacy atom -> resolves UNGROUNDED (NOT
    GROUNDED): final_verdict is downgraded away from VERIFIED."""
    monkeypatch.setenv(_COVERAGE_FLAG, "1")
    transport = _CoverageMockTransport(sentinel_raw=_HALF_DECOMPOSED_RAW)
    result = _run(transport)
    # The Sentinel parsed GROUNDED but the coverage cross-check downgraded it to UNGROUNDED.
    assert result.sentinel_result is not None
    assert result.sentinel_result.verdict is SentinelVerdict.UNGROUNDED
    assert result.sentinel_result.parsed_ok is True  # it parsed cleanly; it is ungrounded by coverage
    # The Judge said VERIFIED, but the UNGROUNDED Sentinel downgrades it to UNSUPPORTED.
    assert result.raw_judge_verdict == "VERIFIED"
    assert result.final_verdict == "UNSUPPORTED"
    assert result.final_verdict != "VERIFIED"
    assert result.d8_row.verdict == "UNSUPPORTED"


def test_no_false_drop_fully_decomposed_stays_grounded_flag_on(monkeypatch, _decomposition_env) -> None:
    """NO FALSE DROP: the SAME 2-clause claim, with BOTH clauses atomized + supported, stays
    GROUNDED and composes to VERIFIED even with the flag ON."""
    monkeypatch.setenv(_COVERAGE_FLAG, "1")
    transport = _CoverageMockTransport(sentinel_raw=_FULLY_DECOMPOSED_RAW)
    result = _run(transport)
    assert result.sentinel_result is not None
    assert result.sentinel_result.verdict is SentinelVerdict.GROUNDED
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"


def test_flag_off_half_decomposed_stays_verified_byte_identical(monkeypatch, _decomposition_env) -> None:
    """FLAG OFF: the half-decomposed claim is NOT downgraded — behavior is byte-identical to pre-F06
    (the Sentinel GROUNDED verdict stands, Judge VERIFIED composes to VERIFIED). This proves the fix
    is fully gated."""
    monkeypatch.delenv(_COVERAGE_FLAG, raising=False)
    transport = _CoverageMockTransport(sentinel_raw=_HALF_DECOMPOSED_RAW)
    result = _run(transport)
    assert result.sentinel_result is not None
    assert result.sentinel_result.verdict is SentinelVerdict.GROUNDED  # NOT downgraded (flag off)
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"


def test_non_decomposition_mode_unaffected_flag_on(monkeypatch) -> None:
    """SCOPE GUARD: guardian/noninverted modes return atoms=None. With the flag ON, a GROUNDED
    non-decomposition Sentinel must NOT be downgraded (the coverage check is skipped on atoms=None) —
    otherwise every non-decomposition GROUNDED claim would wrongly flip to UNSUPPORTED."""
    monkeypatch.setenv(_COVERAGE_FLAG, "1")
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "noninverted")
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    # Non-inverted Sentinel emits the one-word GROUNDED token -> parsed GROUNDED, atoms=None.
    transport = _CoverageMockTransport(sentinel_raw="GROUNDED")
    result = _run(transport)
    assert result.sentinel_result is not None
    assert result.sentinel_result.atoms is None
    assert result.sentinel_result.verdict is SentinelVerdict.GROUNDED  # untouched (atoms=None skip)
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"
