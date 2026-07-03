"""I-deepfix-001 C2 (#1344) — qualitative NLI union scores ALL member pairs.

FAIL-LOUD behavioral proof of the C2 EFFECT: the qualitative-basket NLI union now
links two candidate clusters when ANY cross-cluster MEMBER pair bidirectionally
entails — not only when the REPRESENTATIVES do. A large paraphrase cluster whose
representatives are worded too differently to entail still FULLY unions through a
non-representative member. The representative-level edges remain a floor, so the
union is monotone (never merges LESS than the pre-C2 rep-only behavior).

Over-merge canaries (§-1.1 clinical-lethal if a false 'corroborated' renders):
  * ONE-DIRECTIONAL entailment (hedged-vs-flat / scope / causal-direction /
    temporality) is HARD-BLOCKED by the strict bidirectional requirement.
  * OPPOSITE POLARITY (antonym / negation flip) is HARD-BLOCKED by the polarity
    guard even when the cross-encoder scored the member pair entailing.

Plus the C2 wall-headroom bump (90 -> 180s default, env-overridable).

Deterministic injected ``predict_fn`` — no GPU, no model download, offline / $0.
Serialized per CLAUDE.md §8.4 (pure-python).
"""
from __future__ import annotations

from src.polaris_graph.generator.fact_dedup import (
    _polarity_signature,
    _prose_shingles,
)
from src.polaris_graph.synthesis import consolidation_nli as cn
from src.polaris_graph.synthesis.consolidation_nli import score_pairs
from src.polaris_graph.synthesis.finding_dedup import _apply_qualitative_nli_union

# The claim phrase two independent sources assert; a text ENTAILS another (in the
# injected model) iff BOTH carry this phrase. The cluster-0 representative is worded
# WITHOUT the phrase, so rep-only scoring cannot link the clusters — only an
# all-member scan reaches the phrase-bearing non-representative member.
_PHRASE = "concentrated among large firms"

_ENTAIL = [0.0, 5.0, 0.0]   # [contradiction, entailment, neutral] — entailment argmax
_NEUTRAL = [0.0, 0.0, 5.0]  # neutral argmax => not an entailment


def _row(eid: str, quote: str) -> dict:
    return {"evidence_id": eid, "source_url": f"https://{eid}.example/x", "direct_quote": quote}


def _cluster(rows: list[dict], member_ris: list[int]) -> list:
    """A candidate cluster triple [rep_shingles, rep_polarity, [member_ris]] keyed on
    the lowest-index member as representative (the shape ``_build_qualitative_groups``
    emits)."""
    rep_body = rows[member_ris[0]]["direct_quote"]
    return [_prose_shingles(rep_body), _polarity_signature(rep_body), list(member_ris)]


def _bidirectional_phrase_predict(batch):
    """Entail iff BOTH premise and hypothesis carry the claim phrase (symmetric)."""
    return [
        _ENTAIL if (_PHRASE in prem and _PHRASE in hyp) else _NEUTRAL
        for (prem, hyp) in batch
    ]


def test_c2_all_member_scan_unions_when_reps_do_not_entail():
    """GREEN: cluster-0 rep does NOT entail cluster-1 rep, but cluster-0's second
    MEMBER does — the all-member scan links the two clusters into one basket."""
    rows = [
        _row("a", "Market leaders capture most of the deployment value overall."),  # c0 rep (no phrase)
        _row("b", "AI adoption is concentrated among large firms."),                # c0 member (phrase)
        _row("c", "AI adoption is concentrated among large firms, analysts note."),  # c1 rep (phrase)
    ]
    clusters = [_cluster(rows, [0, 1]), _cluster(rows, [2])]

    # Control: the REPRESENTATIVES alone do NOT entail (rep-only scoring finds no edge),
    # so any union MUST come from the C2 all-member scan.
    rep_texts = [rows[0]["direct_quote"], rows[2]["direct_quote"]]
    assert score_pairs(rep_texts, predict_fn=_bidirectional_phrase_predict) == []

    merged = _apply_qualitative_nli_union(
        rows, [c[:] for c in clusters], predict_fn=_bidirectional_phrase_predict,
    )
    assert len(merged) == 1, "the all-member scan must union the two clusters"
    assert merged[0][2] == [0, 1, 2], (
        f"the merged basket must keep ALL members (got {merged[0][2]})"
    )


def test_c2_no_union_when_no_member_pair_entails():
    """A cluster carrying a genuinely different claim (no phrase in ANY member) stays
    separate — no over-merge on a shared topic word."""
    rows = [
        _row("a", "Market leaders capture most of the deployment value overall."),
        _row("b", "AI adoption is concentrated among large firms."),
        _row("c", "Open-source models improved reasoning benchmarks this year."),  # unrelated claim
    ]
    clusters = [_cluster(rows, [0, 1]), _cluster(rows, [2])]
    merged = _apply_qualitative_nli_union(
        rows, [c[:] for c in clusters], predict_fn=_bidirectional_phrase_predict,
    )
    assert len(merged) == 2, "an unrelated claim must NOT join the basket"


def test_c2_canary_one_directional_entailment_blocked():
    """OVER-MERGE CANARY: a ONE-DIRECTIONAL entailment (hedged-vs-flat / scope /
    causal-direction / temporality) never unions — the strict bidirectional
    requirement blocks it even though member A entails member B forward."""
    rows = [
        _row("a", "AI reduces routine task time in every studied firm."),   # c0 (flat)
        _row("b", "AI may reduce routine task time in some studied firms."),  # c1 (hedged)
    ]
    a_text, b_text = rows[0]["direct_quote"], rows[1]["direct_quote"]

    def _forward_only(batch):
        # Entail ONLY (flat -> hedged); the reverse (hedged -> flat) is not entailment.
        return [_ENTAIL if (prem == a_text and hyp == b_text) else _NEUTRAL for (prem, hyp) in batch]

    clusters = [_cluster(rows, [0]), _cluster(rows, [1])]
    merged = _apply_qualitative_nli_union(
        rows, [c[:] for c in clusters], predict_fn=_forward_only,
    )
    assert len(merged) == 2, "one-directional entailment must NOT union (certainty distortion)"


def test_c2_canary_opposite_polarity_blocked():
    """OVER-MERGE CANARY: even if the cross-encoder scored a member pair entailing,
    an opposite-polarity (antonym) pair is HARD-BLOCKED by the polarity guard."""
    rows = [
        _row("a", "AI adoption increased sharply concentrated among large firms."),
        _row("b", "AI adoption decreased sharply concentrated among large firms."),
    ]
    # Sanity: the two carry OPPOSITE polarity signatures (increase vs decrease).
    assert _polarity_signature(rows[0]["direct_quote"]) != _polarity_signature(rows[1]["direct_quote"])

    # A permissive model that would entail both directions (phrase shared) — the
    # polarity guard, not the model, must block the union.
    clusters = [_cluster(rows, [0]), _cluster(rows, [1])]
    merged = _apply_qualitative_nli_union(
        rows, [c[:] for c in clusters], predict_fn=_bidirectional_phrase_predict,
    )
    assert len(merged) == 2, "an antonym/polarity-flip pair must NEVER corroborate"


def test_c2_wall_headroom_default_raised(monkeypatch):
    """The per-section NLI wall default is raised to 180s (was 90) so large corpora
    are not starved into an under-merge; still fully env-overridable (LAW VI)."""
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_WALL_SECONDS", raising=False)
    assert cn._wall_seconds() == 180.0
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_WALL_SECONDS", "45")
    assert cn._wall_seconds() == 45.0
