"""N2 (I-deepfix-001 wave-2) — contract fragment-prose CONSOLIDATION dedup.

Pure Python, no GPU/LLM/network. Reproduces report_wave2.md line 27 (Acemoglu &
Restrepo): four deterministic "<Label>: value [ev]." fragments plus the narrative
prose restatements that carry the identical values + citation.
"""
from dataclasses import dataclass, field

import pytest

from src.polaris_graph.generator.contract_section_runner import (
    _dedup_fragment_prose_restatements,
    _fragment_prose_dedup_enabled,
)

_ENT = "acemoglu_restrepo_robots_jobs"


@dataclass
class _Tok:
    evidence_id: str
    start: int = 0
    end: int = 688


@dataclass
class _SV:
    sentence: str
    tokens: list = field(default_factory=list)
    reanchor_original_slot_id: str = None


def _sv(text, eid=_ENT):
    return _SV(sentence=text, tokens=[_Tok(eid)])


def _known_labels():
    # As render_slot_prose builds them from required_fields.
    fields = [
        "identification_strategy", "population",
        "effect_estimate_with_uncertainty", "outcome", "sample_size",
    ]
    out = set()
    for f in fields:
        lbl = f.replace("_", " ")
        out.add(lbl[:1].upper() + lbl[1:])
    return out


# The report_wave2.md line 27 fragments + prose.
def _fixture():
    F1 = _sv(
        "Identification strategy: variation in exposure to robots—defined from "
        "industry-level advances in robotics and local industry employment "
        f"[#ev:{_ENT}:0-688]."
    )
    F2 = _sv(f"Population: US labor markets [#ev:{_ENT}:0-688].")
    F3 = _sv(
        "Effect estimate with uncertainty: One more robot per thousand workers "
        "reduces the employment-to-population ratio by 0.2 percentage points and "
        f"wages by 0.42% [#ev:{_ENT}:0-688]."
    )
    F4 = _sv(f"Outcome: employment and wages [#ev:{_ENT}:0-688].")
    P1 = _sv(
        "Acemoglu and Restrepo examined US labor markets, leveraging variation in "
        "exposure to robots—defined from industry-level advances in robotics and "
        f"local industry employment [#ev:{_ENT}:0-688]."
    )
    P2 = _sv(
        "The study found that one more robot per thousand workers reduces the "
        "employment-to-population ratio by 0.2 percentage points and wages by "
        f"0.42% [#ev:{_ENT}:0-688]."
    )
    P3 = _sv(
        "Their identification strategy exploited this variation in exposure to "
        f"estimate effects on employment and wages [#ev:{_ENT}:0-688]."
    )
    return [F1, F2, F3, F4, P1, P2, P3]


def _det_ids(fixture, n_frag=4):
    # First n_frag are deterministic-stream fragments.
    return {id(sv) for sv in fixture[:n_frag]}


def _entity_to_slot(fixture):
    return {_ENT: "slot_a", "other_entity": "slot_a", "e2": "slot_a"}


# (1) DUP-DROP: all four fragments dropped, all three prose survive.
def test_dup_drop():
    fx = _fixture()
    new_kept, tel = _dedup_fragment_prose_restatements(
        fx, _det_ids(fx), _known_labels(), _entity_to_slot(fx),
    )
    kept_text = " || ".join(sv.sentence for sv in new_kept)
    assert tel["n_fragments_dropped"] == 4
    assert "Identification strategy:" not in kept_text
    assert "Population:" not in kept_text
    assert "Effect estimate with uncertainty:" not in kept_text
    assert "Outcome:" not in kept_text
    # All three prose sentences survive (each fact renders once).
    assert sum(1 for sv in new_kept if "Acemoglu and Restrepo examined" in sv.sentence) == 1
    assert sum(1 for sv in new_kept if "The study found that" in sv.sentence) == 1
    assert sum(1 for sv in new_kept if "Their identification strategy" in sv.sentence) == 1


# (2) DISTINCT-KEPT: a fragment with no containing prose is kept.
def test_distinct_kept():
    fx = _fixture()
    F5 = _sv(f"Sample size: 722 commuting zones [#ev:{_ENT}:0-688].")
    fx2 = fx[:4] + [F5] + fx[4:]
    det = {id(sv) for sv in fx2[:5]}
    new_kept, tel = _dedup_fragment_prose_restatements(
        fx2, det, _known_labels(), _entity_to_slot(fx2),
    )
    assert any("Sample size: 722 commuting zones" in sv.sentence for sv in new_kept)


# (3) CITE-GUARD: fragment citing a different entity is kept.
def test_cite_guard():
    fx = _fixture()
    frag = _sv(
        "Effect estimate with uncertainty: One more robot per thousand workers "
        "reduces the employment-to-population ratio by 0.2 percentage points and "
        "wages by 0.42% [#ev:other_entity:0-100].",
        eid="other_entity",
    )
    # P2 cites only acemoglu; fragment cites other_entity -> cite-subset fails.
    P2 = fx[5]
    lst = [frag, P2]
    det = {id(frag)}
    new_kept, tel = _dedup_fragment_prose_restatements(
        lst, det, _known_labels(), _entity_to_slot(lst),
    )
    assert tel["n_fragments_dropped"] == 0
    assert frag in new_kept


# (4) NUMBER-GUARD: fragment carrying a number the prose lacks is kept.
def test_number_guard():
    frag = _sv(
        "Effect estimate with uncertainty: reduces wages by 0.42% [#ev:e2:0-50].",
        eid="e2",
    )
    prose = _sv(
        "The study reported that wages fell somewhat under automation pressure "
        "[#ev:e2:0-50].",
        eid="e2",
    )
    lst = [frag, prose]
    det = {id(frag)}
    new_kept, tel = _dedup_fragment_prose_restatements(
        lst, det, _known_labels(), {"e2": "slot_a"},
    )
    assert tel["n_fragments_dropped"] == 0
    assert frag in new_kept


# (5) PROSE-NEVER-DROPPED.
def test_prose_never_dropped():
    fx = _fixture()
    new_kept, _tel = _dedup_fragment_prose_restatements(
        fx, _det_ids(fx), _known_labels(), _entity_to_slot(fx),
    )
    # None of the prose sentences (indices 4,5,6) removed.
    for prose in fx[4:]:
        assert prose in new_kept


# (6) MIN-RETENTION: the fragment is its entity's sole substantive kept -> KEPT.
def test_min_retention():
    # Prose attributed tokens[0] to a DIFFERENT entity but cite-superset holds.
    frag = _sv(f"Population: US labor markets [#ev:{_ENT}:0-688].")
    prose = _SV(
        sentence=(
            "Acemoglu and Restrepo examined US labor markets in detail "
            f"[#ev:other:0-10][#ev:{_ENT}:0-688]."
        ),
        tokens=[_Tok("other"), _Tok(_ENT)],
    )
    lst = [frag, prose]
    det = {id(frag)}
    new_kept, tel = _dedup_fragment_prose_restatements(
        lst, det, _known_labels(), {_ENT: "slot_a", "other": "slot_a"},
    )
    assert tel["n_fragments_dropped"] == 0, "min-retention keeps the sole substantive SV"
    assert frag in new_kept


# (7) OFF byte-identical: with the flag unset, the runner never calls the pass.
def test_off_flag_disabled(monkeypatch):
    monkeypatch.delenv("PG_CONTRACT_FRAGMENT_PROSE_DEDUP", raising=False)
    assert _fragment_prose_dedup_enabled() is False
    monkeypatch.setenv("PG_CONTRACT_FRAGMENT_PROSE_DEDUP", "0")
    assert _fragment_prose_dedup_enabled() is False
    # And the pure function called directly with det_sv_ids empty is a no-op.
    fx = _fixture()
    new_kept, tel = _dedup_fragment_prose_restatements(
        fx, set(), _known_labels(), _entity_to_slot(fx),
    )
    assert new_kept is fx and tel["n_fragments_dropped"] == 0


# (8) LABEL-EXACTNESS: "In contrast: ..." is not a known label -> never a fragment.
def test_label_exactness():
    frag = _sv(f"In contrast: US labor markets [#ev:{_ENT}:0-688].")
    prose = _sv(
        f"The study examined US labor markets in detail [#ev:{_ENT}:0-688]."
    )
    lst = [frag, prose]
    det = {id(frag)}
    new_kept, tel = _dedup_fragment_prose_restatements(
        lst, det, _known_labels(), {_ENT: "slot_a"},
    )
    assert tel["n_fragments_dropped"] == 0
    assert frag in new_kept


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
