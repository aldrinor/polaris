"""I-deepfix-001 Wave 2b-WIRING (#1344) — the minimal-citation-set minimizer wired into the CWF
render/weight seam (``run_honest_sweep_r3._basket_corroboration_block``).

Design: ``.codex/I-deepfix-001/wave2b_wiring_brief.md``. Fully offline — the entailment cross-encoder
is stubbed by monkeypatching the module's ``_default_entail_fn`` seam (span-keyed), so the REAL
minimizer + the REAL render path run with NO GPU, NO model download, NO OpenRouter spend.

Asserts:
  1. OFF (``PG_MIN_CITE_SET`` unset) => byte-identical legacy render; ``minimize_citation_set`` NEVER
     called (the render path is unchanged, the minimizer is not invoked).
  2. ON => a non-entailing member is PRUNED and an MVC-redundant corroborator is DEMOTED out of the
     inline ``[N]`` set into the weight channel; the demoted members still render as SUPPORT bullets
     with tier+weight (keep-all: inline ∪ weight == all original members), just without an inline ``[N]``.
  3. ON runtime fault in the minimizer => fail-open: all members stay inline, the render never crashes.
"""
from __future__ import annotations

import pytest

from scripts.run_honest_sweep_r3 import _basket_corroboration_block
from src.polaris_graph.generator import citation_set_minimizer as csm


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────
_CLAIM = "Generative AI assistants raise measured worker productivity in support tasks."


def _member(ev_id: str, url: str, tier: str, quote: str, weight: float) -> dict:
    """One verified basket member in the render dict shape (== provenance_generator._basket_for_biblio)."""
    return {
        "member_tier": "ENTAILMENT_VERIFIED",
        "evidence_id": ev_id,
        "source_url": url,
        "source_tier": tier,
        "credibility_weight": weight,
        "authority_score": weight,
        "origin_cluster_id": "oc_" + ev_id,   # distinct origin per member
        "span_verdict": "SUPPORTS",
        "direct_quote": quote,                 # the minimizer's prune-leg span
    }


def _bibliography(members: list[dict]) -> list[dict]:
    """A 3-source corroborated basket attached to a numbered bibliography (nums 1/2/3)."""
    basket = {
        "claim_cluster_id": "clm_labor_productivity",
        "claim_text": _CLAIM,
        "subject": "Generative AI assistants",
        "predicate": "raise measured worker productivity",
        "supporting_members": members,
        "verified_support_origin_count": len(members),
        "basket_verdict": "corroborated",
        "refuter_cluster_ids": [],
    }
    rows = []
    for i, m in enumerate(members, start=1):
        rows.append({
            "evidence_id": m["evidence_id"],
            "num": i,
            "url": m["source_url"],
            "statement": f"Source {i}",
            "baskets": [basket] if i == 1 else [],
        })
    return rows


def _members_keep_off_redundant() -> list[dict]:
    """Three distinct-origin members (weight desc): an entailing load-bearer, an OFFTOPIC (non-entailing)
    member, and a lower-weight entailing corroborator."""
    return [
        _member("ev1", "https://example.org/src1", "T1",
                "genai raises measured worker productivity in support tasks", 0.9),
        _member("ev2", "https://example.org/src2", "T2",
                "OFFTOPIC cookie consent banner navigation chrome", 0.7),
        _member("ev3", "https://example.org/src3", "T3",
                "a second source corroborating the productivity finding", 0.5),
    ]


class _EntailStub:
    """Span-keyed entailment stub: spans containing OFFTOPIC do NOT entail (False); UNKNOWN => None
    (infra-unavailable); everything else entails (True). Records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, premise: str, hypothesis: str):
        self.calls.append((premise, hypothesis))
        if "OFFTOPIC" in premise:
            return False
        if "UNKNOWN" in premise:
            return None
        return True


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts from a clean slate. Layer-2 cite is default-ON in production; pin it ON so the
    seam under test always runs, and clear every PG_MIN_CITE_SET knob."""
    monkeypatch.setenv("PG_CORROBORATION_LAYER2_CITE", "1")
    for var in (
        "PG_MIN_CITE_SET", "PG_MIN_CITE_SET_PRUNE", "PG_MIN_CITE_SET_MAX_INLINE", "PG_MIN_CITE_SET_MARGIN",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# 1. OFF => byte-identical legacy render + minimizer NEVER called
# ─────────────────────────────────────────────────────────────────────────────
def test_off_is_byte_identical_and_minimizer_not_called(monkeypatch):
    # spy: if the wiring ever calls the minimizer while OFF, this fails loudly.
    calls = {"n": 0}
    real = csm.minimize_citation_set

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(csm, "minimize_citation_set", _spy)
    # also spy the entail seam to prove no model touch on the OFF path.
    stub = _EntailStub()
    monkeypatch.setattr(csm, "_default_entail_fn", lambda margin: stub)

    out = _basket_corroboration_block(_bibliography(_members_keep_off_redundant()))

    assert out, "expected a rendered corroboration block"
    assert calls["n"] == 0, "OFF must not invoke the minimizer (render path unchanged)"
    assert stub.calls == [], "OFF must not touch the entailment model"
    # legacy render: the whole basket is cited inline on the claim, every bullet carries its [N].
    assert "[1][2][3]" in out, f"OFF header must cite the whole basket; got:\n{out}"
    assert "https://example.org/src1 [1] (tier" in out
    assert "https://example.org/src2 [2] (tier" in out
    assert "https://example.org/src3 [3] (tier" in out


# ─────────────────────────────────────────────────────────────────────────────
# 2. ON => prune non-entailing + demote MVC-redundant to the weight channel (keep-all)
# ─────────────────────────────────────────────────────────────────────────────
def test_on_prunes_and_demotes_to_weight_channel_keep_all(monkeypatch):
    monkeypatch.setenv("PG_MIN_CITE_SET", "1")
    monkeypatch.setenv("PG_MIN_CITE_SET_MAX_INLINE", "1")  # cover-only inline => redundant demotes
    stub = _EntailStub()
    monkeypatch.setattr(csm, "_default_entail_fn", lambda margin: stub)

    members = _members_keep_off_redundant()
    out = _basket_corroboration_block(_bibliography(members))
    assert out

    # INLINE set == the minimal load-bearing member only: ev1's [1]. ev2 (pruned, OFFTOPIC) and
    # ev3 (MVC-redundant corroborator) are demoted OUT of the inline citation set — their [N] appears
    # NOWHERE in the render.
    assert "[1]" in out, f"the load-bearing member must stay inline; got:\n{out}"
    assert "[2]" not in out, f"pruned non-entailing member must not render an inline [N]; got:\n{out}"
    assert "[3]" not in out, f"MVC-redundant corroborator must not render an inline [N]; got:\n{out}"

    # KEEP-ALL: every member still renders as a SUPPORT bullet with tier+weight (inline ∪ weight == all).
    assert "https://example.org/src1 [1] (tier" in out    # inline: carries its [N]
    assert "https://example.org/src2 (tier" in out        # weight channel: no inline [N]
    assert "https://example.org/src3 (tier" in out        # weight channel: no inline [N]
    assert out.count("SUPPORT:") == 3, "all three sources must remain visible (keep-all, no source dropped)"
    assert "weight " in out and "tier " in out, "the weight channel renders tier + weight"
    # the entailment seam WAS exercised (the minimizer actually ran on the ON path).
    assert stub.calls, "the ON path must invoke the entailment seam"


# ─────────────────────────────────────────────────────────────────────────────
# 3. ON runtime fault in the minimizer => fail-open (all inline, no crash)
# ─────────────────────────────────────────────────────────────────────────────
def test_on_minimizer_runtime_fault_fails_open(monkeypatch):
    monkeypatch.setenv("PG_MIN_CITE_SET", "1")

    def _boom(*_a, **_k):
        raise RuntimeError("simulated minimizer/cross-encoder fault")

    monkeypatch.setattr(csm, "minimize_citation_set", _boom)

    members = _members_keep_off_redundant()
    # must NOT raise — the wiring's fail-open guard keeps ALL members inline.
    out = _basket_corroboration_block(_bibliography(members))
    assert out

    # fail-open == the byte-identical legacy render: the whole basket cited inline, every bullet marked.
    assert "[1][2][3]" in out, f"fail-open must keep all members inline; got:\n{out}"
    assert "https://example.org/src1 [1] (tier" in out
    assert "https://example.org/src2 [2] (tier" in out
    assert "https://example.org/src3 [3] (tier" in out
    assert out.count("SUPPORT:") == 3
