"""I-deepfix-001 (#1369) DEPTH Step 1 — PROVE multi-source baskets form (the depth precondition).

The whole depth chain (analyst synthesis, cross-source comparison, debate) is starved unless
same-claim rows from DIFFERENT sources consolidate into one multi-origin basket. This proves
``dedup_by_finding`` groups (a) three distinct-source rows carrying the SAME qualitative finding
and (b) two distinct-source rows carrying the SAME numeric finding — on synthetic data, offline,
zero network. If this ever regresses to singletons, the deep report cannot form and this fails.
"""

import os

import pytest

from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding


def _row(eid: str, host: str, quote: str) -> dict:
    return {
        "evidence_id": eid,
        "source_url": f"https://{host}/x",
        "direct_quote": quote,
        "statement": quote,
        "authority_score": 0.8,
        "selection_relevance": 0.9,
    }


def test_qualitative_and_numeric_multisource_baskets(monkeypatch):
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE", "1")
    # 3 distinct sources, SAME qualitative finding (no numbers) -> one qualitative basket of >=3.
    q1 = _row("evq1", "a.org", "Generative AI complements skilled labor and raises demand for workers.")
    q2 = _row("evq2", "b.org", "Generative AI complements skilled labor and raises demand for workers.")
    q3 = _row("evq3", "c.org", "Generative AI complements skilled labor and raises demand for workers.")
    # 2 distinct sources, SAME numeric finding -> one numeric basket of >=2.
    n1 = _row("evn1", "d.org", "Robots reduce the employment-to-population ratio by 0.2 percentage points.")
    n2 = _row("evn2", "e.org", "Robots reduce the employment-to-population ratio by 0.2 percentage points.")
    # 1 unrelated singleton.
    s1 = _row("evs1", "f.org", "Occupational licensing raises entry barriers in some regulated trades.")

    result = dedup_by_finding([q1, q2, q3, n1, n2, s1], gov_suffixes=(), domain="workforce")

    # qualitative consolidation fired
    assert result.qualitative_basket_count > 0, "qualitative baskets did not form (singletonized)"
    # at least one representative consolidated >=3 origins (the qualitative trio) OR >=2 (numeric pair)
    corr = [int(r.get("corroboration_count", 1) or 1) for r in result.deduped_rows]
    assert max(corr) >= 3, f"no >=3-origin basket formed; corroboration_counts={corr}"
    assert sum(1 for c in corr if c >= 2) >= 2, (
        f"expected >=2 multi-origin baskets (qual trio + numeric pair); counts={corr}"
    )
    # NB: qualitative consolidation is CONSOLIDATE-KEEP-ALL (§-1.3) — it keeps every member row and
    # marks the representative's corroboration_count, it does NOT delete members. The proof of a
    # multi-source basket is therefore the corroboration_count (>=3 above) + qualitative_basket_count,
    # not a shrunk row list. A representative carrying >=2 origins is exactly what downstream depth
    # (analyst synthesis / cross-source comparison / debate) consumes.
    assert any(int(r.get("corroboration_count", 1) or 1) >= 3 for r in result.deduped_rows)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
