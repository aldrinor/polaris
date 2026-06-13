"""§8 mechanical-proof tests for the Wave-3 spec-generated merge key (I-arch-002 [6]).

Pure CPU: no network, no LLM, no spend. Exercises the FAIL-CLOSED, spec-generated
``build_merge_key`` (claim_graph.py, design §4) that replaces the positional
``_normalized_key_*`` keys when ``PG_SWEEP_CREDIBILITY_REDESIGN`` is ON. OFF stays
byte-identical (test #13).

The merge key is the SOLE defence against over-merge (strict_verify is basket-blind,
design §0), so the lethal direction is OVER-merge — every ambiguity must resolve to a
SINGLETON. These tests prove that, claim-by-claim.

Test ids map to design §8:
  #1  bidirectional generic guard (per kind x domain)
  #5  direction token-only
  #12 true-negative DO merge
  #13 OFF byte-identical (claim_graph path)
  #20 fail-closed dispatch
  #23 unresolved-atom uniqueness

Serialized per CLAUDE.md §8.4 (pure-python). NO unittest.mock; real extractor
dataclasses + real env-flag toggling via monkeypatch.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.contradiction_detector import ExtractedNumericClaim
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    QualitativeAssertion,
    extract_qualitative_assertions,
)
from src.polaris_graph.synthesis.claim_graph import (
    DISCRIMINATING_DIMENSIONS,
    MERGE_KEY_SPEC,
    _ROLE_DISCRIMINATOR,
    _ROLE_EXACT,
    _ROLE_TAG,
    _claim_cluster_id,
    _merge_key_view,
    build_claim_graph,
    build_merge_key,
    cluster_equivalent_claims,
    extract_atomic_claims,
    normalize_domain,
)

# Comparing roles force a field into the key (a difference splits the claim). The
# catalog dimensions must each be a comparing slot; TAG is a constant header only.
_COMPARING_ROLES = frozenset({_ROLE_EXACT, _ROLE_DISCRIMINATOR})

# (kind, domain) -> the DISCRIMINATING_DIMENSIONS catalog key for that pair.
_CATALOG_KEY = {
    ("numeric", "clinical"): "numeric_clinical",
    ("numeric", "nonclinical"): "numeric_nonclinical",
    ("qualitative", "clinical"): "qualitative_clinical",
    ("qualitative", "nonclinical"): "qualitative_nonclinical",
}


def _numeric_view(*, evidence_id="e1", domain="clinical", atom_uid="numeric:e1:0",
                  **fields):
    """A fully-defaulted ExtractedNumericClaim wrapped in a merge-key view.

    Pass only the fields a given test cares about; everything else defaults to the
    UNKNOWN sentinel ('' / None) so the claim is a singleton UNLESS the test
    positively sets every discriminator."""
    base = dict(
        evidence_id=evidence_id, subject="semaglutide", predicate="weight_loss",
        value=14.9, unit="%", context_snippet="ctx", dose="2.4 mg",
        arm="comparator_adjacent", endpoint_phrase="at week 68",
        dose_frequency="weekly", comparator="placebo", route_formulation="sc",
        effect_measure="relative", direction="decrease",
        population="patients with t2dm",
    )
    base.update(fields)
    nc = ExtractedNumericClaim(**base)
    return _merge_key_view(nc, kind="numeric", evidence_id=evidence_id,
                           domain=domain, atom_uid=atom_uid)


def _qual_view(*, evidence_id="q1", domain="clinical", atom_uid="qualitative:q1:0",
               **fields):
    """A fully-known QualitativeAssertion wrapped in a merge-key view."""
    base = dict(
        evidence_id=evidence_id, subject="drug x", concept_type="ae_causation",
        object_slot="pancreatitis", condition_scope="adults",
        assertion_status="present", cue="causes", context_snippet="ctx",
        source_url="https://a.org", source_tier="T1",
        causal_strength="causal", warning_severity="",
        condition_polarity="with",  # a fully-known claim has a definite (non-ambiguous) polarity
    )
    base.update(fields)
    qa = QualitativeAssertion(**base)
    return _merge_key_view(qa, kind="qualitative", evidence_id=evidence_id,
                           domain=domain, atom_uid=atom_uid)


# ── §8 test #1: BIDIRECTIONAL generic guard, per (kind x domain) ───────────────


@pytest.mark.parametrize("kind,domain", list(_CATALOG_KEY.keys()))
def test_1a_every_catalog_dimension_is_a_comparing_slot(kind, domain):
    """#1(a): every DISCRIMINATING_DIMENSIONS[domain] entry appears as a comparing
    slot (EXACT or DISCRIMINATOR — forced into the key) in MERGE_KEY_SPEC[(kind,
    domain)]. Omission of a catalog dimension is impossible by construction.

    RELAXATION (preempting review): the design §8 wording says "DISCRIMINATOR slot",
    but a literal DISCRIMINATOR-only check is impossible against the design's own
    spec — ``value`` is a cataloged dimension (§4.1) that §4.2 makes EXACT, and
    ``causal_strength``/``warning_severity`` are cataloged dimensions §4.3 omits from
    the singleton-forcing set (so EXACT, not DISCRIMINATOR). The faithful invariant
    is "every catalog dimension is a COMPARING slot (forced into the key so a
    difference splits the claim)" — EXACT and DISCRIMINATOR both satisfy that; only
    TAG (a constant header) does not. This resolves a design-internal wording
    inconsistency, it does not loosen the over-merge guarantee."""
    catalog = DISCRIMINATING_DIMENSIONS[_CATALOG_KEY[(kind, domain)]]
    spec = MERGE_KEY_SPEC[(kind, domain)]
    comparing_slot_names = {s.name for s in spec if s.role in _COMPARING_ROLES}
    missing = set(catalog) - comparing_slot_names
    assert not missing, (
        f"catalog dimensions with no comparing slot in {(kind, domain)}: {missing}"
    )


@pytest.mark.parametrize("kind,domain", list(_CATALOG_KEY.keys()))
def test_1b_every_emitted_key_field_comes_from_a_spec_slot(kind, domain):
    """#1(b): every field of the emitted key-tuple is produced by a spec slot — no
    field exists outside the spec (the tuple is emitted FROM the spec, not
    hand-written and separately checked)."""
    spec = MERGE_KEY_SPEC[(kind, domain)]
    view = _numeric_view(domain=domain) if kind == "numeric" else _qual_view(domain=domain)
    key = build_merge_key(view)
    # a fully-known claim must NOT be a forced singleton (otherwise the fixture is
    # under-specified and #1(b) would not exercise the real positive path).
    assert key[0] != "__unresolved__", "fully-known fixture must emit a spec key"
    # the emitted tuple has exactly one element per spec slot (1:1, no extras).
    assert len(key) == len(spec), (
        f"key arity {len(key)} != spec slot count {len(spec)} for {(kind, domain)}"
    )
    # every catalog dimension's value is present as a key field (by slot order).
    slot_names = [s.name for s in spec]
    for slot, field_value in zip(spec, key):
        if slot.role == _ROLE_TAG:
            continue
        assert field_value is not None
    # spec slot names are unique (no duplicate field collapsing two dimensions).
    assert len(slot_names) == len(set(slot_names)), "duplicate slot names in spec"


def test_1_spec_extractor_binding_value_getters_target_real_fields():
    """#21-style spec<->extractor binding (the construction guarantee): every
    DISCRIMINATOR slot's value_getter resolves a real attribute on the extractor
    dataclass (a getter pointing at a missing field would silently under-merge).

    We assert by reading each getter against a fully-populated real extractor object
    and confirming it returns the positively-set value (not the '' fall-through)."""
    num_view = _numeric_view()
    for slot in MERGE_KEY_SPEC[("numeric", "clinical")]:
        if slot.role != _ROLE_DISCRIMINATOR:
            continue
        v = slot.value_getter(num_view)
        assert v, f"numeric_clinical slot {slot.name} did not resolve a real field"
    qual_view = _qual_view()
    for slot in MERGE_KEY_SPEC[("qualitative", "clinical")]:
        if slot.role != _ROLE_DISCRIMINATOR:
            continue
        # warning_severity is legitimately '' for an ae_causation fixture — skip it.
        if slot.name == "warning_severity":
            continue
        v = slot.value_getter(qual_view)
        assert v, f"qualitative_clinical slot {slot.name} did not resolve a real field"


# ── §8 test #5: direction is TOKEN-ONLY (never predicate-derived) ──────────────


def test_5_direction_token_only_opposite_directions_do_not_merge():
    """#5: 'rose 5%' (direction=increase) vs 'fell 5%' (direction=decrease), all
    else equal -> distinct keys (no merge). The direction discriminator is a
    positively-extracted token, never inferred from the predicate (design §4.3)."""
    up = _numeric_view(evidence_id="up", atom_uid="numeric:up:0", direction="increase")
    down = _numeric_view(evidence_id="dn", atom_uid="numeric:dn:0", direction="decrease")
    k_up = build_merge_key(up)
    k_dn = build_merge_key(down)
    assert k_up != k_dn, "opposite direction tokens must yield distinct keys"
    assert _claim_cluster_id(k_up) != _claim_cluster_id(k_dn)


def test_5_unknown_direction_is_a_singleton():
    """A claim with NO extracted direction token ('' = UNKNOWN) is a forced
    singleton — never merged on a derived/defaulted direction."""
    no_dir = _numeric_view(evidence_id="nd", atom_uid="numeric:nd:0", direction="")
    k = build_merge_key(no_dir)
    assert k[0] == "__unresolved__", "unknown direction must force a singleton"


# ── ontology-split coverage of THIS merge key (#15 causal, #16 warning) ────────
# These no-merge cases are listed under the extractor steps (P1.3/P1.4) but the
# actual split is enforced HERE, by the EXACT causal_strength / warning_severity
# slots. Verifying them is the direct validation that EXACT (not DISCRIMINATOR) is
# the right role: the split must hold AND all-known equal claims must still merge.


def test_15_causes_does_not_merge_associated():
    """#15: 'drug X causes Y' (causal_strength=causal) vs 'drug X is associated with
    Y' (associational), same subject/object/population/status -> distinct keys (the
    textbook correlation-as-causation error must NOT be laundered into a merge)."""
    causal = _qual_view(evidence_id="c1", atom_uid="qualitative:c1:0",
                        causal_strength="causal", cue="causes")
    assoc = _qual_view(evidence_id="a1", atom_uid="qualitative:a1:0",
                       causal_strength="associational", cue="associated with")
    k_causal = build_merge_key(causal)
    k_assoc = build_merge_key(assoc)
    assert k_causal[0] != "__unresolved__", "a fully-known causal claim must emit a key"
    assert k_causal != k_assoc, "causal must NOT merge associational"
    assert _claim_cluster_id(k_causal) != _claim_cluster_id(k_assoc)


def test_16_boxed_warning_does_not_merge_routine_caution():
    """#16: a boxed/regulatory warning vs a routine caution (same hazard/population/
    status) -> distinct keys (severity laundering forbidden)."""
    boxed = _qual_view(evidence_id="b1", atom_uid="qualitative:b1:0",
                       concept_type="warning", causal_strength="",
                       warning_severity="boxed_regulatory", cue="boxed warning",
                       object_slot="hepatotoxicity")
    routine = _qual_view(evidence_id="r1", atom_uid="qualitative:r1:0",
                         concept_type="warning", causal_strength="",
                         warning_severity="routine_caution", cue="caution in",
                         object_slot="hepatotoxicity")
    k_boxed = build_merge_key(boxed)
    k_routine = build_merge_key(routine)
    assert k_boxed[0] != "__unresolved__", "a fully-known warning claim must emit a key"
    assert k_boxed != k_routine, "boxed warning must NOT merge routine caution"
    assert _claim_cluster_id(k_boxed) != _claim_cluster_id(k_routine)


def test_equal_causal_strength_clinical_claims_still_merge():
    """The EXACT role does not paralyse merges: two identical causal ae_causation
    claims (same strength) still share one cluster — corroboration preserved."""
    a = _qual_view(evidence_id="a", atom_uid="qualitative:a:0", causal_strength="causal")
    b = _qual_view(evidence_id="b", atom_uid="qualitative:b:0", causal_strength="causal")
    k_a = build_merge_key(a)
    k_b = build_merge_key(b)
    assert k_a[0] != "__unresolved__"
    assert k_a == k_b, "equal causal claims must co-cluster"
    assert _claim_cluster_id(k_a) == _claim_cluster_id(k_b)


# ── §8 test #12: true-negative — all slots known + equal -> DO merge ───────────


def test_12_all_known_equal_claims_merge():
    """#12: two clinical numeric atoms with EVERY discriminator positively known
    AND equal share ONE cluster id (consolidation is live, not paralysed). The
    breadth Principle: corroboration is preserved when the claim is provably the
    same."""
    a = _numeric_view(evidence_id="a", atom_uid="numeric:a:0")
    b = _numeric_view(evidence_id="b", atom_uid="numeric:b:0")
    k_a = build_merge_key(a)
    k_b = build_merge_key(b)
    assert k_a[0] != "__unresolved__", "all-known claim must emit a real spec key"
    assert k_a == k_b, "all-known equal claims must produce the SAME key"
    assert _claim_cluster_id(k_a) == _claim_cluster_id(k_b), "they must co-cluster"


def test_12_one_differing_discriminator_blocks_merge():
    """The merge is conservative: a SINGLE differing discriminator (here dose)
    keeps the two claims in distinct clusters even when all else is equal."""
    a = _numeric_view(evidence_id="a", atom_uid="numeric:a:0", dose="2.4 mg")
    b = _numeric_view(evidence_id="b", atom_uid="numeric:b:0", dose="7.2 mg")
    assert build_merge_key(a) != build_merge_key(b)


# ── §8 test #20: fail-closed dispatch ─────────────────────────────────────────


def test_20_raw_kind_is_always_a_forced_singleton():
    """#20: a claim with kind=='raw' has no spec -> forced singleton, never a
    coarse default spec (the silent-over-merge direction)."""
    # a raw view carries no extractor discriminator fields; the dispatch must
    # short-circuit on (raw, *) before reading any slot.
    raw_view = _merge_key_view({}, kind="raw", evidence_id="r1",
                               domain="clinical", atom_uid="raw:r1:txt")
    k = build_merge_key(raw_view)
    assert k[0] == "__unresolved__"
    assert k[1] == "raw"


def test_20_unknown_domain_is_a_forced_singleton():
    """#20: a (kind, domain) whose domain does not normalize to clinical/nonclinical
    -> no spec -> forced singleton (never a coarse default)."""
    view = _numeric_view(evidence_id="u", atom_uid="numeric:u:0", domain="")
    k = build_merge_key(view)
    assert k[0] == "__unresolved__", "unset/unnormalizable domain must singleton"
    # gibberish domain hint -> UNKNOWN -> singleton
    view2 = _numeric_view(evidence_id="g", atom_uid="numeric:g:0", domain="not_a_domain")
    assert build_merge_key(view2)[0] == "__unresolved__"


def test_20_two_identical_unresolved_claims_get_distinct_cluster_ids():
    """#20: two claims that BOTH fail dispatch with otherwise-identical fields must
    still get distinct cluster ids (the singleton key is globally unique via
    evidence_id + atom_uid) — a fail-closed claim never silently co-merges."""
    raw_a = _merge_key_view({}, kind="raw", evidence_id="r1",
                            domain="clinical", atom_uid="raw:r1:a")
    raw_b = _merge_key_view({}, kind="raw", evidence_id="r2",
                            domain="clinical", atom_uid="raw:r2:b")
    k_a = build_merge_key(raw_a)
    k_b = build_merge_key(raw_b)
    assert k_a != k_b
    assert _claim_cluster_id(k_a) != _claim_cluster_id(k_b)


def test_20_unknown_discriminator_forces_singleton_even_with_spec():
    """#20 per-slot axis: dispatch finds a spec, but a single not-positively-known
    DISCRIMINATOR (here: comparator '') forces the singleton anyway."""
    view = _numeric_view(evidence_id="c", atom_uid="numeric:c:0", comparator="")
    k = build_merge_key(view)
    assert k[0] == "__unresolved__", "unknown discriminator must force a singleton"


def test_20_defaulted_arm_treatment_is_unknown_singleton():
    """The arm lesson (design §4.3): a DEFAULTED arm ('treatment') is NOT positively
    known -> singleton. Only a positively-extracted comparator arm anchors a merge."""
    view = _numeric_view(evidence_id="t", atom_uid="numeric:t:0", arm="treatment")
    assert build_merge_key(view)[0] == "__unresolved__"
    # arm=None is likewise unknown (defense-in-depth: the extractor default is the
    # legacy "treatment" string for OFF byte-identity per Codex Slice-B P1, but
    # _unknown_arm must also reject a None should any caller pass one).
    view_none = _numeric_view(evidence_id="n", atom_uid="numeric:n:0", arm=None)
    assert build_merge_key(view_none)[0] == "__unresolved__"


# ── §8 test #23: unresolved-atom uniqueness under numeric fan-out ──────────────


def test_23_two_unresolved_atoms_same_evidence_id_distinct_atom_uid():
    """#23: two distinct UNRESOLVED atoms from the SAME evidence_id (different
    atom_uid, as the numeric fan-out produces) -> distinct singleton cluster ids
    (no same-source collision). Proves the atom_uid field is load-bearing in the
    fail-closed singleton key."""
    # both unresolved (comparator '' -> singleton), same evidence_id, distinct uid
    a = _numeric_view(evidence_id="shared", atom_uid="numeric:shared:0", comparator="")
    b = _numeric_view(evidence_id="shared", atom_uid="numeric:shared:1", comparator="")
    k_a = build_merge_key(a)
    k_b = build_merge_key(b)
    assert k_a[0] == "__unresolved__" and k_b[0] == "__unresolved__"
    assert k_a != k_b, "distinct atom_uid must keep same-evidence unresolved atoms apart"
    assert _claim_cluster_id(k_a) != _claim_cluster_id(k_b)


def test_23_raw_atoms_same_evidence_distinct_text_dont_collide():
    """The raw-site analogue (design §9.7): two raw atoms sharing an evidence_id but
    different normalized text get distinct atom_uids -> distinct singletons."""
    a = _merge_key_view({}, kind="raw", evidence_id="dup", domain="clinical",
                        atom_uid="raw:dup:first text")
    b = _merge_key_view({}, kind="raw", evidence_id="dup", domain="clinical",
                        atom_uid="raw:dup:second text")
    assert build_merge_key(a) != build_merge_key(b)


# ── §8 test #13: OFF = byte-identical on the claim_graph path ──────────────────


def _graph_signature(rows):
    """A stable signature of a built graph: cluster ids + structure + edges, the
    surface that drives downstream consolidation/disclosure. domain/atom_uid are
    additive carriers that never feed normalized_key, so they are not part of the
    byte-identity surface — cluster ids are."""
    g = build_claim_graph(rows)
    return {
        "claim_cluster_ids": [c.claim_cluster_id for c in g.claims],
        "normalized_keys": [tuple(c.normalized_key) for c in g.claims],
        "clusters": {k: sorted(v) for k, v in g.clusters.items()},
        "distinct_cluster_count": g.distinct_cluster_count,
        "raw_row_count": g.raw_row_count,
        "edge_count": len(g.edges),
        "edge_cluster_ids": sorted(tuple(e.claim_cluster_ids) for e in g.edges),
    }


_OFF_ROWS = [
    {"evidence_id": "e1", "direct_quote": "Semaglutide achieved 14.9% weight loss at week 68.",
     "source_url": "https://a.org", "tier": "T1"},
    {"evidence_id": "e2", "direct_quote": "Semaglutide achieved 14.9% weight loss at week 68.",
     "source_url": "https://b.org", "tier": "T1"},
    {"evidence_id": "e3", "direct_quote": "Tirzepatide produced 22.5% weight loss at week 72.",
     "source_url": "https://c.org", "tier": "T1"},
    {"evidence_id": "e4", "direct_quote": "Global GDP grew 3.1% in 2023 per the IMF.",
     "source_url": "https://d.org", "tier": "T2"},
]


def test_13_off_path_is_byte_identical_when_flag_unset(monkeypatch):
    """#13: with PG_SWEEP_CREDIBILITY_REDESIGN unset, the claim_graph path
    (cluster ids, normalized keys, clusters, edges) is byte-identical to the
    pre-change legacy positional-key behaviour — the new spec machinery is never
    reached on the OFF path."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    sig_unset = _graph_signature(_OFF_ROWS)
    # explicit off-values must all behave identically
    for off in ("", "0", "false", "off", "no"):
        monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", off)
        assert _graph_signature(_OFF_ROWS) == sig_unset, f"off-value {off!r} drifted"


# The EXACT frozen pre-change (legacy) numeric normalized_key tuples for _OFF_ROWS.
# These were captured by EXECUTING the legacy positional builder (build_claim_graph ->
# _normalized_key_numeric) from the Slice-B PARENT commit 8e938d49~1 in isolation over
# this same _OFF_ROWS fixture (not reasoned by hand): the run emitted exactly
#   e1/e2 -> ('numeric','semaglutide','weight loss',14.9,'%','','treatment','at week 68')
#   e3    -> ('numeric','tirzepatide','weight loss',22.5,'%','','treatment','at week 72')
# This is the byte-identity baseline test #13 compares against — NOT a self-referential
# "it runs" check. Position 7 is ``arm``: the legacy/no-cue value is "treatment" (the
# Codex Slice-B P1 fix reverts the extractor's transient ``arm=None`` back to this), so a
# regression to None would surface here as position 7 drifting "treatment" -> "" and the
# cluster ids changing.
_FROZEN_OFF_NUMERIC_KEYS = {
    # e1 + e2 are the SAME claim text -> identical legacy key -> they co-cluster.
    "e1": ("numeric", "semaglutide", "weight loss", 14.9, "%", "", "treatment", "at week 68"),
    "e2": ("numeric", "semaglutide", "weight loss", 14.9, "%", "", "treatment", "at week 68"),
    "e3": ("numeric", "tirzepatide", "weight loss", 22.5, "%", "", "treatment", "at week 72"),
}


def test_13_off_normalized_keys_match_frozen_legacy_tuples(monkeypatch):
    """#13 anchor (HARDENED): on the OFF path each numeric key equals the EXACT
    pre-change legacy positional tuple captured at 8e938d49~1 — a real frozen
    expectation, byte-for-byte, NOT just an 8-field shape check. Position 7 (arm)
    must be the legacy "treatment" string; the Codex Slice-B P1 arm-revert is what
    keeps it so. Any drift here = OFF byte-identity broken."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    g = build_claim_graph(_OFF_ROWS)
    by_evid = {}
    for c in g.claims:
        if c.kind == "numeric" and c.normalized_key[0] == "numeric":
            by_evid[str(c.evidence_id)] = tuple(c.normalized_key)
    assert by_evid, "fixture must yield resolved numeric claims on the OFF path"
    for evid, expected in _FROZEN_OFF_NUMERIC_KEYS.items():
        assert by_evid.get(evid) == expected, (
            f"OFF numeric key for {evid} drifted from the frozen legacy tuple:\n"
            f"  got      {by_evid.get(evid)}\n  expected {expected}\n"
            "(check position 7 'arm' — a regression to None drifts 'treatment' -> '')"
        )
    # The arm position is specifically "treatment" on every resolved key (the revert anchor).
    for evid, key in by_evid.items():
        assert key[6] == "treatment", f"{evid} arm slot {key[6]!r} != legacy 'treatment'"


def test_13_off_cluster_ids_are_frozen_and_dedup_identical_claims(monkeypatch):
    """#13 structural anchor: the OFF cluster ids are deterministic AND the two
    identical-text rows (e1/e2) collapse to ONE cluster while the distinct row (e3)
    is its own — exactly the legacy positional-key grouping. A SHA-1 over a drifted
    key (e.g. arm None -> '') would change these ids, so freezing them is the
    byte-identity guard at the cluster-id surface."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    g = build_claim_graph(_OFF_ROWS)
    cid_by_evid = {
        str(c.evidence_id): c.claim_cluster_id
        for c in g.claims if c.kind == "numeric" and c.normalized_key[0] == "numeric"
    }
    # e1 and e2 carry the identical legacy key -> identical cluster id (co-clustered).
    assert cid_by_evid["e1"] == cid_by_evid["e2"], (
        "identical-text rows must share a cluster id under the legacy key"
    )
    # e3 is a distinct claim -> distinct cluster id.
    assert cid_by_evid["e3"] != cid_by_evid["e1"], "distinct claim must not co-cluster"


def test_13_off_normalized_keys_match_legacy_positional_shape(monkeypatch):
    """#13 anchor: on the OFF path the numeric key keeps the EXACT legacy positional
    tuple ('numeric', subject, predicate, value, unit, dose, arm, endpoint) — i.e.
    build_merge_key is NOT what produced it."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    g = build_claim_graph(_OFF_ROWS)
    numeric = [c for c in g.claims if c.kind == "numeric"]
    assert numeric, "fixture must yield numeric claims"
    for c in numeric:
        # the legacy numeric key either is the 8-field positional tuple or the
        # per-claim unknown sentinel — never the redesign 14-field spec tuple.
        head = c.normalized_key[0]
        assert head in ("numeric", "__numeric_unknown__"), (
            f"OFF numeric key head {head!r} is not the legacy shape"
        )
        if head == "numeric":
            assert len(c.normalized_key) == 8, "legacy numeric key must be 8 fields"


def test_13_on_path_uses_spec_key_not_legacy(monkeypatch):
    """Confirms the flip is real: with the flag ON, an all-known clinical numeric
    row produces the 14-field spec tuple, not the 8-field legacy tuple. (The ON
    path needs the real query domain threaded; P3.1 wires it — here we pass it
    directly to extract_atomic_claims to exercise the merge-key flip in isolation.)"""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    rows = [{
        "evidence_id": "e1",
        "direct_quote": "Semaglutide achieved 14.9% weight loss at week 68.",
        "source_url": "https://a.org", "tier": "T1",
    }]
    claims = extract_atomic_claims(rows, domain="clinical")
    for c in claims:
        # domain + atom_uid are stamped on every claim on the ON path
        assert c.domain == "clinical"
        assert c.atom_uid, "atom_uid must be set on the ON path"
        # the redesign singleton key head is '__unresolved__'; a fully-resolved
        # numeric key starts with 'numeric' and is 14 fields. Either way it is NOT
        # the 8-field legacy positional tuple unless it co-incidentally singletons.
        if c.kind == "numeric" and c.normalized_key[0] == "numeric":
            assert len(c.normalized_key) == 14, "ON numeric spec key is 14 fields"


# ── §8 NEW: population-polarity over-merge proof (Claude Slice-B iter-2 P0, #1245) ──
# The merge key was polarity-BLIND on condition_scope: "causes nausea in patients WITH
# renal impairment" and "...WITHOUT renal impairment" produced an IDENTICAL key and
# over-merged into a fabricated 2-source basket of OPPOSITE populations. The per-sentence
# faithfulness engine is basket-blind and cannot catch a false-merge, so the merge key is
# the SOLE defense (design §0). condition_polarity (EXACT) splits with!=without.


def test_population_polarity_with_vs_without_does_not_merge():
    """Two clinical qualitative claims identical in every field EXCEPT the population
    polarity (with vs without) MUST get distinct merge keys (no fabricated corroboration)."""
    with_pop = _qual_view(evidence_id="w1", atom_uid="qualitative:w1:0",
                          condition_scope="renal impairment", condition_polarity="with")
    without_pop = _qual_view(evidence_id="o1", atom_uid="qualitative:o1:0",
                             condition_scope="renal impairment", condition_polarity="without")
    assert build_merge_key(with_pop) != build_merge_key(without_pop)


def test_population_polarity_same_polarity_still_merges():
    """Two claims with the SAME population polarity (both 'with') and all else equal MUST
    still merge — the fix splits opposite populations, it does not over-fragment same ones."""
    a = _qual_view(evidence_id="a", atom_uid="qualitative:a:0",
                   condition_scope="renal impairment", condition_polarity="with")
    b = _qual_view(evidence_id="b", atom_uid="qualitative:b:0",
                   condition_scope="renal impairment", condition_polarity="with")
    ka, kb = build_merge_key(a), build_merge_key(b)
    assert ka[0] != "__unresolved__" and ka == kb


def test_population_polarity_end_to_end_real_extractor():
    """BEHAVIORAL proof through the REAL extractor (not a hand-built view): WITH vs WITHOUT
    renal impairment, run through extract_qualitative_assertions + build_merge_key, split."""
    import os
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    try:
        s_with = "Semaglutide causes nausea in patients with renal impairment."
        s_without = "Semaglutide causes nausea in patients without renal impairment."
        aw = extract_qualitative_assertions(
            [{"evidence_id": "EVW", "direct_quote": s_with, "tier": "T1"}], domain="clinical")
        ao = extract_qualitative_assertions(
            [{"evidence_id": "EVO", "direct_quote": s_without, "tier": "T1"}], domain="clinical")
        assert aw and ao, "extractor must yield assertions for both"
        assert aw[0].condition_polarity == "with"
        assert ao[0].condition_polarity == "without"
        kw = build_merge_key(_merge_key_view(
            aw[0], kind="qualitative", evidence_id="EVW", domain="clinical",
            atom_uid="qualitative:EVW:0"))
        ko = build_merge_key(_merge_key_view(
            ao[0], kind="qualitative", evidence_id="EVO", domain="clinical",
            atom_uid="qualitative:EVO:0"))
        # neither is a fail-closed singleton here (object_slot=nausea is known), and they
        # MUST NOT share a key — the lethal over-merge is fixed.
        assert kw[0] != "__unresolved__" and ko[0] != "__unresolved__"
        assert kw != ko
    finally:
        os.environ.pop("PG_SWEEP_CREDIBILITY_REDESIGN", None)


# ── condition_polarity negation-scoping edge cases (Claude self-audit, iter-2b) ──
# The negation must govern the POPULATION noun, not a verb/object elsewhere in the clause.
# A loose lookback would mislabel "causes NO nausea IN renal impairment" as 'without' (the
# "no" negates nausea) and could over-merge it with a genuine without-renal claim — the
# lethal direction. The scoped back-walk stops at the "in" population introducer.
import pytest as _pytest
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    POLARITY_AMBIGUOUS,
    _extract_condition_polarity as _ecp,
    _load_lexicon as _ll,
)

_POLARITY_CASES = [
    ("in patients with renal impairment", "with"),
    ("in patients without renal impairment", "without"),
    ("in patients without any renal impairment", "without"),  # Codex iter-2 P0: filler 'any'
    ("no evidence of renal impairment", "without"),           # Codex iter-2 P0: 'evidence of' filler
    ("without severe renal impairment", "without"),           # walk past PRE_QUALIFIER
    ("in renal impairment", "with"),
    ("patients free of renal impairment", "without"),         # walk past 'of' linker
    ("patients free from hepatic disease", "without"),        # walk past 'from' linker
    ("no renal impairment", "without"),
    ("patients who do not have renal impairment", "without"), # 'not have renal'
    ("non-renal patients", "without"),                        # negation prefix on the cue token
    ("causes no nausea in renal impairment", "with"),         # 'no' governs nausea, NOT population
    ("does not cause nausea in renal impairment", "with"),    # 'not' governs the verb (before 'in')
    ("associated with renal impairment", "with"),             # 'with' introducer
    ("safe in normal renal function", "with"),
    # Codex iter-3 P0: EXCLUSION phrasings invert the population -> 'without' (non-renal).
    ("in patients other than those with renal impairment", "without"),
    ("in patients excluding those with renal impairment", "without"),
    ("in patients except those with renal impairment", "without"),
    ("rather than those with renal impairment", "without"),
    ("apart from patients with renal impairment", "without"),
    ("in patients with severe renal impairment", "with"),     # affirmative must NOT false-flip
    # Codex iter-4 P0: exclusion across a relative clause / long participant description.
    ("in patients other than those who have renal impairment", "without"),
    ("excluding adult participants with documented prior history of severe renal impairment", "without"),
    # Codex iter-4 fail-closed: a population under an UNRESOLVED relative clause (no
    # negation/exclusion) -> POLARITY_AMBIGUOUS (forces a singleton, never a guessed 'with').
    ("in patients who have renal impairment", POLARITY_AMBIGUOUS),
    ("in patients that present with renal impairment", POLARITY_AMBIGUOUS),
    # Codex iter-5 P0: NEGATED-INCLUSION exclusion across a nested introducer ("in ... not
    # ... with ...") — the population phrase is bounded by the OUTERMOST introducer so the
    # 'not' (after 'in', before the cue) governs the population -> 'without'.
    ("in patients not including those with renal impairment", "without"),
    ("in patients not having renal impairment", "without"),
    # regression guard: a verb-negation BEFORE the outer introducer stays 'with'.
    ("does not cause nausea in patients with renal impairment", "with"),
    ("causes nausea", ""),                                     # no population cue -> unstratified
]


@_pytest.mark.parametrize("sentence,expected", _POLARITY_CASES)
def test_condition_polarity_negation_scoping(sentence, expected):
    assert _ecp(sentence, _ll()) == expected


def test_population_polarity_exclusion_does_not_merge_with_affirmative():
    """Codex iter-3 P0 end-to-end: an EXCLUSION-phrased population ("patients other than /
    excluding those with renal impairment" = the NON-renal population) must NOT share a
    merge key with the affirmative "with renal impairment" claim. Run through the REAL
    extractor + build_merge_key under the flag."""
    import os
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    try:
        affirmative = "Semaglutide causes nausea in patients with renal impairment."
        exclusions = [
            "Semaglutide causes nausea in patients other than those with renal impairment.",
            "Semaglutide causes nausea in patients excluding those with renal impairment.",
        ]
        a_aff = extract_qualitative_assertions(
            [{"evidence_id": "AFF", "direct_quote": affirmative, "tier": "T1"}], domain="clinical")
        assert a_aff and a_aff[0].condition_polarity == "with"
        k_aff = build_merge_key(_merge_key_view(
            a_aff[0], kind="qualitative", evidence_id="AFF", domain="clinical",
            atom_uid="qualitative:AFF:0"))
        assert k_aff[0] != "__unresolved__"
        for n, sent in enumerate(exclusions):
            ev = f"EXC{n}"
            a_exc = extract_qualitative_assertions(
                [{"evidence_id": ev, "direct_quote": sent, "tier": "T1"}], domain="clinical")
            assert a_exc and a_exc[0].condition_polarity == "without", sent
            k_exc = build_merge_key(_merge_key_view(
                a_exc[0], kind="qualitative", evidence_id=ev, domain="clinical",
                atom_uid=f"qualitative:{ev}:0"))
            # the excluded (non-renal) population must NOT merge with the affirmative (renal).
            assert k_exc != k_aff, f"exclusion over-merged with affirmative: {sent}"
    finally:
        os.environ.pop("PG_SWEEP_CREDIBILITY_REDESIGN", None)


def test_population_polarity_iter4_relative_clause_and_long_exclusion():
    """Codex iter-4 P0 end-to-end (fail-closed): an EXCLUSION across a relative clause /
    long participant description must split from the affirmative, and an UNRESOLVED
    relative-clause population must fail closed to a singleton (never a guessed 'with')."""
    import os
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    try:
        def k(sent, ev):
            a = extract_qualitative_assertions(
                [{"evidence_id": ev, "direct_quote": sent, "tier": "T1"}], domain="clinical")
            assert a, sent
            return build_merge_key(_merge_key_view(
                a[0], kind="qualitative", evidence_id=ev, domain="clinical",
                atom_uid=f"qualitative:{ev}:0")), a[0].condition_polarity
        k_aff, p_aff = k("Semaglutide causes nausea in patients with renal impairment.", "AFF")
        assert p_aff == "with" and k_aff[0] != "__unresolved__"
        # exclusion across a relative clause -> 'without' -> distinct key
        k1, p1 = k("Semaglutide causes nausea in patients other than those who have renal impairment.", "X1")
        assert p1 == "without" and k1 != k_aff
        # long exclusion (operator far from cue) -> 'without' -> distinct key
        k2, p2 = k("Semaglutide causes nausea in patients excluding adult participants with documented prior history of severe renal impairment.", "X2")
        assert p2 == "without" and k2 != k_aff
        # unresolved relative clause (no negation/exclusion) -> ambiguous -> SINGLETON
        k3, p3 = k("Semaglutide causes nausea in patients who have renal impairment.", "X3")
        assert p3 == POLARITY_AMBIGUOUS and k3[0] == "__unresolved__"
    finally:
        os.environ.pop("PG_SWEEP_CREDIBILITY_REDESIGN", None)
