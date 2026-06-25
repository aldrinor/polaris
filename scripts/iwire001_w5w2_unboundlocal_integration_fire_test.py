#!/usr/bin/env python3
"""I-wire-001 (Codex P1#1) — §-1.4 BEHAVIORAL integration fire-test.

PROVES the W5/W2 collision fix by driving the REAL ``run_live_retrieval`` per-source
loop with PG_CREDIBILITY_LLM_TIERING=1 (the path that raised UnboundLocalError at
``tier_result.tier.value`` ~L4890 because the W5 ON-path never bound ``tier_result``).

This is the INTEGRATION proof the existing module fire-test
(``iwire001_w5_credibility_llm_tiering_fire_test.py``) does NOT give: that one drives
``classify_sources_llm_tiering`` in isolation, so it never executes the live_retriever
loop where the crash lives.

Faithful §-1.4 harness rules:
  * The REAL ``run_live_retrieval`` runs — NOT a copied loop (a copy would prove a copy
    fired, the exact §-1.4 trap).
  * Only the NETWORK LEAVES are monkeypatched: ``_fetch_content`` returns banked text,
    OpenAlex enrich is OFF, discovery is bypassed via ``seed_only`` + ``seed_urls``.
  * The W5 LLM leaf (``credibility_llm_tiering._default_caller``) is swapped for an
    injected caller returning a tier DIFFERENT from the deterministic rules-floor for
    the seed source. This is NOT circular: the discriminating assertion is that the
    injected tier (!= floor) reaches the EVIDENCE row the generator reads — if the
    loop never ran L4890, or the else-path ran, or the back-fill never reached the
    evidence-row surface, the tier would be the floor (or rows empty) => FAIL LOUD.

Fail-loud (non-zero exit) if ANY of:
  1. run_live_retrieval raises (the UnboundLocalError regression).
  2. no evidence rows produced.
  3. the evidence row's tier is the rules-floor, not the injected W5 tier
     (the silent-no-op: W5 reached classified_sources but NOT the generator surface).
  4. the W5 tier + W2 content_relevance_weight do not COEXIST on the classified source.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fail(msg: str) -> None:
    print(f"FIRE-TEST FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    # A real, non-social journal-ish URL so the rules-floor lands on a definite,
    # non-T7 tier; the injected W5 tier is chosen to DIFFER from it below.
    seed_url = "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183"
    banked_body = (
        "BACKGROUND In this randomized, controlled phase 3 trial, tirzepatide "
        "reduced glycated hemoglobin by 2.07 percentage points versus placebo. "
        "METHODS Adults with type 2 diabetes were randomly assigned. RESULTS The "
        "mean change in body weight was -9.5 kg in the 15-mg group. CONCLUSIONS "
        "Tirzepatide produced clinically meaningful reductions in HbA1c and weight. "
        * 6
    )

    from src.polaris_graph.retrieval import live_retriever as lr
    from src.polaris_graph.retrieval import credibility_llm_tiering as w5
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        _classify_source_tier_rules,
    )

    # Determine the deterministic rules-floor tier for the seed source, so the injected
    # W5 tier can be chosen DIFFERENT (the discriminating value).
    floor_sig = ClassificationSignals(
        url=seed_url, title="Tirzepatide trial", fetched_content_length=len(banked_body)
    )
    floor_tier = _classify_source_tier_rules(floor_sig).tier.value
    # Pick an injected tier guaranteed != floor (cycle through the scheme).
    _scheme = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
    injected_tier = next(t for t in _scheme if t != floor_tier)
    print(f"  floor_tier={floor_tier}  injected_W5_tier={injected_tier}")

    # ── Monkeypatch ONLY the leaves ──────────────────────────────────────────
    # 1) network fetch leaf -> banked body (ok=True full text).
    def _stub_fetch_content(url, max_chars, doi_hint="", pmid_hint=""):  # noqa: ANN001
        return (banked_body[:max_chars], True, "Tirzepatide trial", "", "")

    lr._fetch_content = _stub_fetch_content  # type: ignore[attr-defined]

    # 2) W5 LLM leaf -> injected tier (!= floor). Keeps the REAL batch + back-fill.
    def _injected_caller():
        def _call(_prompt: str) -> str:
            return f'{{"tier": "{injected_tier}", "rationale": "injected fire-test"}}'

        return _call

    w5._default_caller = _injected_caller  # type: ignore[attr-defined]

    # ── Winner flags ON (W5 + W2 fields exercised); W2 GPU reranker stays OFF
    # (the content_relevance_weight/_label defaults 1.0/"" are set at the append
    # sites regardless, so "W5+W2 coexist" is provable without loading Qwen). ──
    os.environ["PG_CREDIBILITY_LLM_TIERING"] = "1"
    os.environ["PG_TIER_LLM_WORKERS"] = "2"
    os.environ.setdefault("PG_USE_PARALLEL_FETCH", "1")

    try:
        result = lr.run_live_retrieval(
            research_question="tirzepatide HbA1c reduction in type 2 diabetes",
            seed_urls=[seed_url],
            seed_only=True,
            seed_source="agentic_seed",
            enable_openalex_enrich=False,
            enable_prefetch_filter=False,
        )
    except UnboundLocalError as exc:
        _fail(
            f"run_live_retrieval raised UnboundLocalError — the W5/W2 regression is "
            f"NOT fixed: {exc}"
        )
    except Exception as exc:  # noqa: BLE001
        _fail(f"run_live_retrieval raised unexpectedly ({type(exc).__name__}): {exc}")

    # 1) COMPLETES (we are here) + 2) evidence rows produced.
    ev_rows = result.evidence_rows
    if not ev_rows:
        _fail("no evidence rows produced — cannot prove the W5 tier reached the report")

    # 3) the injected W5 tier (!= floor) reached the EVIDENCE row the generator reads.
    seed_rows = [r for r in ev_rows if r.get("source_url") == seed_url]
    if not seed_rows:
        _fail(f"seed url {seed_url} not present in evidence_rows")
    ev_tier = seed_rows[0].get("tier", "")
    if ev_tier != injected_tier:
        _fail(
            f"evidence_row tier={ev_tier!r} != injected W5 tier {injected_tier!r} "
            f"(floor={floor_tier!r}). W5 SILENTLY NO-OPPED on the generator surface "
            f"(reached classified_sources only, not the evidence row)."
        )
    # The temp key must not leak into the persisted row.
    if "_w5_tier_batch_idx" in seed_rows[0]:
        _fail("_w5_tier_batch_idx leaked into the persisted evidence row")

    # 4) W5 tier + W2 content_relevance_weight COEXIST on the classified source.
    cs = [s for s in result.classified_sources if s.url == seed_url]
    if not cs:
        _fail(f"seed url {seed_url} not in classified_sources")
    src = cs[0]
    if src.tier != injected_tier:
        _fail(
            f"classified_source tier={src.tier!r} != injected W5 tier "
            f"{injected_tier!r} (back-fill did not reach classified_sources)"
        )
    if not hasattr(src, "content_relevance_weight"):
        _fail("classified_source missing W2 content_relevance_weight field")
    _ = float(src.content_relevance_weight)  # must be present + numeric (W2)
    _ = src.content_relevance_label  # W2 label coexists

    print(
        "FIRE-TEST PASS: run_live_retrieval COMPLETED with PG_CREDIBILITY_LLM_TIERING=1 "
        "(no UnboundLocalError); evidence_row tier="
        f"{ev_tier} == injected W5 tier (!= floor {floor_tier}) => W5 FIRED on the "
        "generator surface; W5 tier + W2 content_relevance_weight="
        f"{src.content_relevance_weight} COEXIST on the classified source; "
        "faithfulness engine untouched (tier is placement metadata)."
    )


if __name__ == "__main__":
    main()
