#!/usr/bin/env python3
"""I-arch-011 PR-b behavioral replay-harness — the Argus keep-all CORROBORATION-RENDER proof (§-1.4, FAIL LOUD).

Acceptance is BEHAVIORAL: the per-claim basket-corroboration block (PR-b) must ACTUALLY
APPEAR in the REAL rendered ``report.md`` bibliography output, driven by the PRODUCTION
``PG_BASKET_CORROBORATION_RENDER`` env flag — not "Codex approved the diff" and not "tests
are green" (CLAUDE.md §-1.4). This closes the Codex P1 on the prior PR-b commit (2849a29f),
which had the render work correct but lacked the §-1.4 behavioral replay over a real-shaped
ClaimBasket through the REAL render path.

Why no real on-disk corpus_snapshot.json: the I-arch-007/010 corpus backups
(``outputs/corpus_backups/extracted/<slug>/corpus_snapshot.json``) are gitignored and NOT
checked out into a fresh worktree (verified absent at build time). The I-arch-010
replay-harness handles the identical situation by SYNTHESIZING the real-shaped objects and
driving the REAL production functions through them; this harness follows that sanctioned
fallback. The objects are real ``ClaimBasket`` / ``BasketMember`` instances (NOT hand-baked
dicts) flowing through the REAL ``resolve_provenance_to_citations_with_count`` ->
``_basket_for_biblio`` projection -> ``_render_bibliography_lines`` chain — the same call
chain ``multi_section_generator`` uses for ``report.md`` — so the EFFECT is exercised in the
production render path, not mocked.

The wiring proof (the heart of the Codex P1): the harness does NOT pass
``corroboration_render=True`` literally. It sets ``PG_BASKET_CORROBORATION_RENDER=1`` and
reads the flag through ``sweep._env_flag(sweep._BASKET_CORROBORATION_RENDER_ENV, ...)`` — the
EXACT helper + identifier the LIVE call site (run_one_query) uses — then passes that resolved
bool into ``_render_bibliography_lines``. So the assertions prove env-flag -> real output, the
§-1.4 "fired in the output, not config" property, not merely that the function accepts a kwarg.

FAITHFULNESS: this harness adds NO production code. It reads-only. ``strict_verify`` /
``_classify_member_tier`` / the verified-support invariant (only ENTAILMENT_VERIFIED counts)
are untouched. The basket is constructed with a DETERMINISTIC_ONLY weak member, an UNVERIFIED
garbage member, and a contradict/refuter reference so the harness PROVES, in the rendered
output, that a weak member is surfaced LABELED-weak but NEVER counted as verified support and
NEVER rendered as a verified citation (no inflation).

Run: ``python scripts/iarch011_prb_corroboration_replay_harness.py`` -> exit 0 if every
assertion fires, non-zero + the failing assertion on any miss.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the repo root importable so the harness runs standalone (§-1.4: run directly, not
# only under pytest). scripts/ is one level under the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.run_honest_sweep_r3 as sweep
from src.polaris_graph.generator.provenance_generator import (
    SentenceVerification,
    parse_provenance_tokens,
    resolve_provenance_to_citations_with_count,
)
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_DETERMINISTIC_ONLY,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    MEMBER_TIER_UNVERIFIED,
    BasketMember,
    ClaimBasket,
)

# The weak (DETERMINISTIC_ONLY) and garbage (UNVERIFIED) source URLs — referenced in the
# inflation assertions so they are single-sourced.
_WEAK_URL = "https://preprint.org/c"
_UNVERIFIED_URL = "https://blog.example/d"
_SUPPORT_URL_A = "https://nejm.org/a"
_SUPPORT_URL_B = "https://lancet.com/b"


def _fail(case: str, detail: str) -> None:
    print(f"FAIL [{case}]: {detail}", file=sys.stderr)
    sys.exit(1)


def _build_real_basket_inputs():
    """Build REAL ``ClaimBasket`` / ``BasketMember`` objects (not dicts) for ONE multi-source
    claim cluster ``c1``:
      - TWO ENTAILMENT_VERIFIED members (genuine verified support -> counted, rendered SUPPORT).
      - ONE DETERMINISTIC_ONLY member (grounded-but-weak -> surfaced LABELED-weak, NOT counted).
      - ONE UNVERIFIED member (deterministic garbage -> never surfaced).
      - a refuter reference (``refuter_cluster_ids=("c9",)`` + ``basket_verdict="contested"``)
        so the cluster-level CONTRADICT label fires.
    ``verified_support_origin_count=2`` is the basket's OWN invariant count (the I-arch-010
    no-leak guarantee: only the two ENTAILMENT_VERIFIED members), distinct from the 4 raw
    members. Returns ``(kept_sentences, evidence_pool, baskets, cluster_id_by_evidence)`` in
    the exact shape the REAL resolver consumes."""
    evidence_pool = {
        "ev_a": {"source_url": _SUPPORT_URL_A, "tier": "T1", "statement": "HbA1c cut 2.1%"},
        "ev_b": {"source_url": _SUPPORT_URL_B, "tier": "T1", "statement": "2.1% drop"},
        "ev_c": {"source_url": _WEAK_URL, "tier": "T4", "statement": "improved"},
        "ev_d": {"source_url": _UNVERIFIED_URL, "tier": "T7", "statement": "news"},
    }
    sent = "Tirzepatide reduced HbA1c by 2.1% at 40 weeks [#ev:ev_a:0-13]."
    kept = [
        SentenceVerification(
            sentence=sent,
            tokens=parse_provenance_tokens(sent),
            is_verified=True,
            failure_reasons=[],
            soft_warnings=[],
        )
    ]
    members = [
        BasketMember("ev_a", _SUPPORT_URL_A, "T1", "o1", 0.95, 0.9, (0, 13),
                     "HbA1c cut 2.1%", "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        BasketMember("ev_b", _SUPPORT_URL_B, "T1", "o2", 0.88, 0.85, (0, 8),
                     "2.1% drop", "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        BasketMember("ev_c", _WEAK_URL, "T4", "o3", 0.40, 0.3, (0, 8),
                     "improved", "UNSUPPORTED", MEMBER_TIER_DETERMINISTIC_ONLY),
        BasketMember("ev_d", _UNVERIFIED_URL, "T7", "o4", 0.05, 0.05, (0, 4),
                     "news", "UNSUPPORTED", MEMBER_TIER_UNVERIFIED),
    ]
    basket = ClaimBasket(
        "c1", "Tirzepatide reduced HbA1c by 2.1% at 40 weeks", "Tirzepatide",
        "reduced HbA1c", members, ("c9",), 2.7, 4, 2, "contested",
    )
    cluster_id_by_evidence = {"ev_a": ["c1"], "ev_b": ["c1"], "ev_c": ["c1"], "ev_d": ["c1"]}
    return kept, evidence_pool, [basket], cluster_id_by_evidence


def main() -> int:
    kept, evidence_pool, baskets, cluster_id_by_evidence = _build_real_basket_inputs()

    # ── Drive the REAL resolver: it attaches row["baskets"] via _basket_for_biblio exactly as
    # the live report.md path (multi_section_generator) does. NOT a hand-baked row dict. ──
    _text, biblio, _emitted = resolve_provenance_to_citations_with_count(
        kept, evidence_pool, baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
    )
    if not biblio:
        _fail("resolver", "the REAL resolver produced an EMPTY bibliography — the attach->render "
                          "chain cannot be exercised.")
    if "baskets" not in biblio[0]:
        _fail("resolver", "the REAL resolver did NOT attach row['baskets'] — _basket_for_biblio "
                          "projection did not fire (basket data lost before render).")
    # the member_tier seam (I-arch-010) must survive the projection — it is what the render reads
    # to distinguish verified support from grounded-but-weak.
    proj_tiers = [m.get("member_tier") for m in biblio[0]["baskets"][0]["supporting_members"]]
    expected_tiers = ["ENTAILMENT_VERIFIED", "ENTAILMENT_VERIFIED",
                      "DETERMINISTIC_ONLY", "UNVERIFIED"]
    if proj_tiers != expected_tiers:
        _fail("projection", f"projected member_tier order {proj_tiers!r} != expected "
                            f"{expected_tiers!r} — the I-arch-010 seam was not carried through.")

    # ── WIRING (the §-1.4 heart, the Codex P1): drive the render through the PRODUCTION env
    # flag, NOT a literal True. Set the flag, read it through the EXACT helper + identifier the
    # LIVE call site uses, and pass the RESOLVED bool into the real render. ──
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    os.environ[sweep._BASKET_CORROBORATION_RENDER_ENV] = "1"
    corro_flag = sweep._env_flag(sweep._BASKET_CORROBORATION_RENDER_ENV, default=False)
    if corro_flag is not True:
        _fail("wiring", "the PRODUCTION env flag PG_BASKET_CORROBORATION_RENDER read through "
                        "sweep._env_flag did NOT resolve to True after being set — the env->render "
                        "wiring is broken (the §-1.4 'fired in config not output' trap).")

    # The REAL render path (the same function the live report.md assembly calls), driven by the
    # ENV-RESOLVED flag (corro_flag), not a hardcoded True.
    rendered = sweep._render_bibliography_lines(
        biblio, require_locator=False, corroboration_render=corro_flag,
    )

    # ── ASSERTION 1: the multi-source basket shows the corroboration COUNT (the basket's own
    # verified_support_origin_count=2, NEVER the 4 raw members). ──
    if "## Source corroboration (per claim)" not in rendered:
        _fail("assert1_count", "the per-claim corroboration block header is ABSENT from the "
                              "rendered output — the env-driven render did not fire.")
    if "2 verified independent source(s)" not in rendered:
        _fail("assert1_count", "the corroboration COUNT '2 verified independent source(s)' "
                              "(verified_support_origin_count) is ABSENT from the rendered output.")

    # ── ASSERTION 2: per-source SUPPORT weight lines appear (each ENTAILMENT_VERIFIED member,
    # carrying its credibility weight + tier). ──
    if f"SUPPORT: {_SUPPORT_URL_A} (tier T1, weight 0.95)" not in rendered:
        _fail("assert2_weights", f"the SUPPORT weight line for {_SUPPORT_URL_A} (weight 0.95) is "
                                "ABSENT — per-source credibility weights did not render.")
    if f"SUPPORT: {_SUPPORT_URL_B} (tier T1, weight 0.88)" not in rendered:
        _fail("assert2_weights", f"the SUPPORT weight line for {_SUPPORT_URL_B} (weight 0.88) is "
                                "ABSENT — per-source credibility weights did not render.")

    # ── ASSERTION 3: the CONTRADICT/contested label appears (cluster-level, from
    # basket_verdict==contested / refuter_cluster_ids). ──
    if "CONTRADICTED" not in rendered:
        _fail("assert3_contradict", "the cluster-level CONTRADICT label is ABSENT from the "
                                    "rendered output — a contested basket did not surface its "
                                    "contradiction (faithfulness: a contested claim must show it).")

    # ── ASSERTION 4: the DETERMINISTIC_ONLY member appears under a labeled-weak disclosure
    # (grounded-but-weak), DISTINCT from verified support. ──
    if "GROUNDED-BUT-WEAK" not in rendered or _WEAK_URL not in rendered:
        _fail("assert4_weak_disclosed", "the DETERMINISTIC_ONLY member was NOT surfaced under a "
                                       "GROUNDED-BUT-WEAK disclosure — the I-arch-010 weak seam is "
                                       "not consumed in the render (LAW II: disclose, don't hide).")

    # ── ASSERTION 5: NO inflation — the weak/unverified members are NEVER counted in
    # verified_support_origin_count and NEVER rendered as verified support/citation. ──
    # 5a: the weak member is never on a SUPPORT line (only verified members are support).
    if f"SUPPORT: {_WEAK_URL}" in rendered:
        _fail("assert5_no_inflation", f"the DETERMINISTIC_ONLY member {_WEAK_URL} appears on a "
                                     "SUPPORT line — a weak member was rendered as VERIFIED "
                                     "support (INFLATION / faithfulness violation).")
    # 5b: the count was NOT inflated to 3 or 4 by the weak/garbage members.
    if "3 verified independent source(s)" in rendered or "4 verified independent source(s)" in rendered:
        _fail("assert5_no_inflation", "the verified-support COUNT was inflated to 3 or 4 — a "
                                     "weak/unverified member leaked into verified_support_origin_count.")
    # 5c: the UNVERIFIED garbage member is never surfaced at all (not even as weak).
    if _UNVERIFIED_URL in rendered:
        _fail("assert5_no_inflation", f"the UNVERIFIED garbage member {_UNVERIFIED_URL} appears in the "
                                     "rendered output — deterministic garbage was surfaced (the "
                                     "member_tier contract requires it stay hidden).")

    # ── WIRING belt-and-suspenders: the LIVE call site reads the env flag via _env_flag, so a
    # silent regression that drops the env read (reverting to config-only) fails loud here. ──
    import inspect
    src = inspect.getsource(sweep)
    if "biblio_section = _render_bibliography_lines(" not in src:
        _fail("wiring_source", "the live report.md call site biblio_section = "
                              "_render_bibliography_lines(...) is GONE — the render is unwired.")
    call_start = src.index("biblio_section = _render_bibliography_lines(")
    call_block = src[call_start:call_start + 800]
    if "corroboration_render=_env_flag(" not in call_block:
        _fail("wiring_source", "the live call site no longer passes "
                              "corroboration_render=_env_flag(...) — the env->render wiring was "
                              "dropped (§-1.4 fired-in-config-not-output regression).")
    if "_BASKET_CORROBORATION_RENDER_ENV" not in call_block:
        _fail("wiring_source", "the live call site no longer references the "
                              "_BASKET_CORROBORATION_RENDER_ENV identifier — the wiring is broken.")

    print(
        "PASS iarch011 PR-b corroboration-render harness: REAL resolver attached row['baskets'] "
        "(member_tier seam carried: ENTAILMENT_VERIFIED x2 / DETERMINISTIC_ONLY / UNVERIFIED); "
        "the PRODUCTION env flag PG_BASKET_CORROBORATION_RENDER read through sweep._env_flag "
        "drove the REAL _render_bibliography_lines path; in the RENDERED output: "
        "(1) COUNT='2 verified independent source(s)' (verified_support_origin_count, NOT 4 members); "
        "(2) per-source SUPPORT weight lines (0.95 / 0.88); "
        "(3) cluster-level CONTRADICTED label; "
        "(4) DETERMINISTIC_ONLY member under GROUNDED-BUT-WEAK disclosure; "
        "(5) NO inflation — weak member never on a SUPPORT line, count never 3/4, UNVERIFIED "
        "garbage never surfaced; live call site still wires corroboration_render=_env_flag(...). "
        "Faithfulness untouched (read-only harness)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
