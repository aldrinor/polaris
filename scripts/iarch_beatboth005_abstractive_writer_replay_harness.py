#!/usr/bin/env python3
"""I-beatboth-005 (#1282) — behavioral replay-harness for the FAITHFUL ABSTRACTIVE WRITER (§-1.4, FAIL LOUD).

Acceptance is BEHAVIORAL: the abstractive-writer effect must ACTUALLY APPEAR in the REAL post-tail
rendered text — clean prose on the happy path, the verbatim K-span whenever the writer misbehaves —
NOT "Codex approved the diff" and NOT "tests are green" (CLAUDE.md §-1.4). The headline §-1.4 trap
this closes: a paraphrase (unlike the deterministic stub) is NOT a substring of its span, so the
real render gate is the section TAIL ``_rewrite_draft_with_spans`` + strict_verify, not the internal
``_compose_one_basket`` loop. EVERY fixture therefore runs its compose output THROUGH
``_rewrite_draft_with_spans(raw, evidence_pool)`` and asserts the POST-TAIL text — a fixture that
passes the loop but is dropped/re-anchored-away at the tail FAILS LOUD.

What is FAKE (no network, no spend) vs REAL:
  * The WRITER is always FAKE — a fixture-controlled precomputed draft injected through the REAL
    ``make_abstractive_writer_fn`` (a pure dict lookup), exactly as the async pre-pass would hand it
    to the compose loop. No OpenRouter call.
  * For W6 ONLY a fake ENTAILMENT JUDGE is injected (``entailment_judge._JUDGE_SINGLETON``) — a
    transport ``judge_error`` cannot arise offline, so W6 scripts ``("ENTAILED","judge_error: ...")``
    to exercise the REAL ``verify_sentence_provenance`` advisory-keep path (sets ``is_verified=True,
    judge_error=True``) and then the REAL writer wrapper (which must FLIP it to ``is_verified=False``).
  * Because the WRITER VERIFY WRAPPER requires ``PG_STRICT_VERIFY_ENTAILMENT=enforce`` (the activation
    guard), the entailment leg runs on EVERY fixture that clears the content/numeric floor. Offline
    with no model the real judge would fail OPEN to ``judge_error`` and the wrapper would then demote
    even the HAPPY path (W1) to the K-span — killing the happy path. So a SCRIPTED fake judge is
    installed for ALL fixtures, keyed on the ``span`` text it receives: ENTAILED for a faithful
    paraphrase / a local window; NEUTRAL for a meaning-distorting paraphrase / a non-entailing full
    span; ``judge_error`` for W6's transport-failure marker. This is the ONLY way to exercise the
    enforce-mode wrapper offline; the REAL ``verify_sentence_provenance`` advisory/fail-closed logic,
    the REAL writer wrapper, the REAL compose loop, and the REAL tail are all under test.

EVERYTHING ELSE IS REAL: ``verify_sentence_provenance`` (strict_verify), ``make_writer_verify_fn``
(the wrapper under test), ``_compose_section_per_basket`` / ``_compose_one_basket`` /
``build_verified_span_draft`` / the region gate, and ``_rewrite_draft_with_spans`` (the tail). No
production code is modified; faithfulness is untouched.

FIXTURES (each asserts POST-TAIL text):
  W1  clean faithful paraphrase + verbatim token + every span numeric -> PASS -> clean prose renders.
  W2  paraphrase with a FABRICATED/ALTERED numeric                     -> FAIL strict_verify -> K-span.
  W3  paraphrase that drops/garbles the token (or cites a FOREIGN id)  -> FAIL region gate   -> K-span.
  W4  fluent paraphrase that DISTORTS meaning (real entailment NEUTRAL, NO judge fake)
                                                                        -> FAIL entailment   -> K-span.
  W5  garbage / empty                                                  -> K-span; NEVER empty.
  W6  clean paraphrase + a transport judge_error (advisory-kept by the engine)
                                                                        -> wrapper FLIPS -> K-span.
  W7  paraphrase that entails only a same-row LOCAL WINDOW, not the full span
                  -> PASS under allow_local_window_fallback=True (loophole exists) but FAIL under the
                     wrapper's allow_local_window_fallback=False                       -> K-span.
  W8  fluent paraphrase, sentence->span clean, but DROPS a substantive span numeric
                  -> PASS the bare engine (one-directional) but FAIL the wrapper completeness guard
                     (writer_numeric_dropped)                                          -> K-span.

Run: ``python scripts/iarch_beatboth005_abstractive_writer_replay_harness.py`` -> exit 0 iff every
fixture's POST-TAIL text is the expected clean-prose (W1) / K-span (W2-W8); non-zero + the failing
fixture otherwise.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# The activation guard + the entailment leg both require enforce; set it BEFORE any verify import.
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
# The I-arch-010 default: a transport judge_error is advisory-kept (is_verified=True, judge_error=True).
# W6 depends on this default so the wrapper is what flips it. Pin it explicitly.
os.environ["PG_ENTAILMENT_JUDGE_ERROR_ADVISORY"] = "1"
# Span resolver OFF (default) so the completeness guard reads the writer's OWN cited spans, not a
# re-anchored token.
os.environ.pop("PG_SPAN_RESOLVER", None)

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    _compose_section_per_basket,
    _rewrite_draft_with_spans,
    build_verified_span_draft,
)
from src.polaris_graph.generator.abstractive_writer import (  # noqa: E402
    make_abstractive_writer_fn,
    make_writer_verify_fn,
)
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
)
from src.polaris_graph.llm import entailment_judge  # noqa: E402


def _fail(case: str, detail: str) -> None:
    print(f"FAIL [{case}]: {detail}")
    sys.exit(1)


# ── the scripted fake entailment judge (keyed on the span text it is handed) ─────────────────────
#
# ``verify_sentence_provenance`` calls ``_get_judge().judge(sentence_clean, combined_span)``.
# We key the verdict on the SPAN text so a single installed judge drives every fixture:
#   * a span tagged W6-judge-error -> ("ENTAILED","judge_error: injected") (transport-failure marker)
#   * a span the fixtures mark NON-ENTAILING (W4 full span, W7 full span) -> NEUTRAL
#   * everything else (faithful paraphrases, W7's local window) -> ENTAILED
# The keying uses substring sentinels embedded in the fixture SPAN TEXT so the judge stays
# deterministic and offline.
_JUDGE_ERROR_SENTINEL = "ZZJUDGEERRORZZ"      # present in W6's span -> transport judge_error
_NEUTRAL_SENTINEL = "ZZNEUTRALZZ"             # present in a full span that should NOT entail (W4/W7)


class _ScriptedJudge:
    """A deterministic offline stand-in for ``_EntailmentJudge`` — same ``judge(sentence, span)``
    contract. Returns ENTAILED by default so faithful paraphrases pass; NEUTRAL when the span
    carries the neutral sentinel (the W4/W7 full-span non-entailment); and the transport
    ``judge_error`` sentinel when the span carries the judge-error sentinel (W6)."""

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        if _JUDGE_ERROR_SENTINEL in (span or ""):
            return "ENTAILED", "judge_error: injected"
        if _NEUTRAL_SENTINEL in (span or ""):
            return "NEUTRAL", "scripted_neutral"
        return "ENTAILED", "scripted_entailed"


def _install_scripted_judge() -> None:
    entailment_judge._JUDGE_SINGLETON = _ScriptedJudge()  # type: ignore[attr-defined]


# ── real-shaped object builders ──────────────────────────────────────────────────────────────────
def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url=f"https://example.org/{eid}", source_tier="T1",
        origin_cluster_id=f"o::{eid}", credibility_weight=0.9, authority_score=0.9,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )


def _basket(ccid: str, subject: str, quote: str, eid: str) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=ccid, claim_text=quote, subject=subject, predicate="finding",
        supporting_members=[_member(eid, quote)], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )


def _post_tail(basket: ClaimBasket, evidence_pool: dict, draft: str,
               verify_fn) -> str:
    """Drive ONE basket through the REAL compose loop (with the injected writer draft + the writer
    wrapper) AND THEN the REAL section TAIL ``_rewrite_draft_with_spans`` — the actual render gate.
    Returns the POST-TAIL text (what would render)."""
    writer_fn = make_abstractive_writer_fn({basket.claim_cluster_id: draft})
    composed = _compose_section_per_basket(
        [basket], evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
    )
    raw = "\n".join(c for c in composed if c and c.strip())
    rewritten, _converted, _unverifiable = _rewrite_draft_with_spans(raw, evidence_pool)
    return rewritten


def main() -> int:  # noqa: C901, PLR0915 — a linear fixture battery
    _install_scripted_judge()
    base_verify = verify_sentence_provenance
    writer_verify = make_writer_verify_fn(base_verify)

    # ── W1: clean faithful paraphrase carrying every span numeric + the verbatim token -> clean prose.
    w1_quote = "Total employment rose by 5.4 percentage points across the surveyed firms in 2024."
    w1 = _basket("w1", "employment effect", w1_quote, "ev_w1")
    pool1 = {"ev_w1": {"evidence_id": "ev_w1", "direct_quote": w1_quote}}
    w1_token = f"[#ev:ev_w1:0-{len(w1_quote)}]"
    # A faithful paraphrase: same numbers (5.4 and 2024), declarative, carries the token verbatim.
    w1_draft = f"Surveyed firms reported a 5.4 percentage-point rise in total employment during 2024. {w1_token}"
    out1 = _post_tail(w1, pool1, w1_draft, writer_verify)
    if "5.4" not in out1 or "[#ev:ev_w1:" not in out1:
        _fail("W1_clean_renders", f"the faithful paraphrase must render post-tail with its numbers + token; got {out1!r}")
    if "Surveyed firms reported" not in out1:
        _fail("W1_paraphrase_survives_tail",
              f"the CLEAN paraphrase (not the verbatim span) must survive the tail unchanged; got {out1!r}")
    k1 = build_verified_span_draft(w1, pool1)
    if k1 and out1.strip() == k1.strip():
        _fail("W1_not_kspan",
              f"W1 rendered the verbatim K-span, not the clean paraphrase — the writer silently no-opped; got {out1!r}")

    # ── W2: FABRICATED/ALTERED numeric -> number_not_in_any_cited_span -> K-span.
    w2_quote = "Adoption reached 13.0 percent of small enterprises by the end of the period."
    w2 = _basket("w2", "adoption rate", w2_quote, "ev_w2")
    pool2 = {"ev_w2": {"evidence_id": "ev_w2", "direct_quote": w2_quote}}
    w2_token = f"[#ev:ev_w2:0-{len(w2_quote)}]"
    w2_draft = f"Adoption reached 27.0 percent of small enterprises by the period's end. {w2_token}"  # 27.0 not in span
    out2 = _post_tail(w2, pool2, w2_draft, writer_verify)
    if "27.0" in out2:
        _fail("W2_fabricated_numeric", f"a FABRICATED numeric must NOT render; got {out2!r}")
    if "13.0" not in out2 or "[#ev:ev_w2:" not in out2:
        _fail("W2_kspan", f"W2 must fall back to its verbatim K-span (13.0 + token); got {out2!r}")

    # ── W3: drops/garbles the token (cites a FOREIGN id absent from the basket-scoped pool) -> K-span.
    w3_quote = "Regional output expanded steadily over the three consecutive fiscal quarters."
    w3 = _basket("w3", "regional output", w3_quote, "ev_w3")
    pool3 = {"ev_w3": {"evidence_id": "ev_w3", "direct_quote": w3_quote}}
    w3_draft = "Regional output expanded steadily across three fiscal quarters. [#ev:ev_FOREIGN:0-40]"
    out3 = _post_tail(w3, pool3, w3_draft, writer_verify)
    if "ev_FOREIGN" in out3:
        _fail("W3_foreign_token", f"a FOREIGN token must NOT render; got {out3!r}")
    if "[#ev:ev_w3:" not in out3 or w3_quote.rstrip(".") not in out3:
        _fail("W3_kspan", f"W3 must fall back to its OWN verbatim K-span; got {out3!r}")

    # ── W4: meaning-DISTORTION — full-span NEUTRAL (real entailment leg, NO judge fake) -> K-span.
    # The span carries the NEUTRAL sentinel so the scripted judge returns NEUTRAL on the FULL span;
    # under the wrapper's allow_local_window_fallback=False that fails closed immediately.
    w4_quote = f"Productivity gains were concentrated in larger firms. {_NEUTRAL_SENTINEL}"
    w4 = _basket("w4", "productivity gains", w4_quote, "ev_w4")
    pool4 = {"ev_w4": {"evidence_id": "ev_w4", "direct_quote": w4_quote}}
    w4_token = f"[#ev:ev_w4:0-{len(w4_quote)}]"
    # Fluent, shares >=2 content words, real token, but the judge grades the full span NEUTRAL.
    w4_draft = f"Productivity gains were concentrated in smaller firms across the sector. {w4_token}"
    out4 = _post_tail(w4, pool4, w4_draft, writer_verify)
    if "smaller firms across the sector" in out4:
        _fail("W4_distortion_rendered", f"a meaning-DISTORTING paraphrase must NOT render under enforce; got {out4!r}")
    if "[#ev:ev_w4:" not in out4 or "Productivity gains were concentrated in larger firms" not in out4:
        _fail("W4_kspan", f"W4 must fall back to its verbatim K-span; got {out4!r}")
    # Prove the failure_reason is the entailment leg (W4) and NOT the judge_error path (W6) — distinct mechanisms.
    w4_scoped = {"ev_w4": pool4["ev_w4"]}
    w4_sent = f"Productivity gains were concentrated in smaller firms across the sector. {w4_token}"
    w4_res = writer_verify(w4_sent, w4_scoped)
    if bool(getattr(w4_res, "is_verified", False)):
        _fail("W4_wrapper_pass", f"W4 distortion must FAIL the wrapper; got is_verified=True ({w4_res!r})")
    if not any("entailment_failed" in r for r in (getattr(w4_res, "failure_reasons", []) or [])):
        _fail("W4_reason",
              f"W4 must fail via the entailment leg (entailment_failed), distinct from W6's judge_error; "
              f"reasons={getattr(w4_res, 'failure_reasons', None)!r}")

    # ── W5: garbage / empty -> K-span; NEVER empty.
    w5_quote = "Investment in automation tooling increased among manufacturing operators."
    w5 = _basket("w5", "automation investment", w5_quote, "ev_w5")
    pool5 = {"ev_w5": {"evidence_id": "ev_w5", "direct_quote": w5_quote}}
    out5 = _post_tail(w5, pool5, "", writer_verify)  # empty writer draft
    if not out5.strip():
        _fail("W5_empty", "W5 must NEVER render empty (always-release); got empty output")
    if "[#ev:ev_w5:" not in out5 or w5_quote.rstrip(".") not in out5:
        _fail("W5_kspan", f"W5 (garbage/empty writer) must fall back to its verbatim K-span; got {out5!r}")

    # ── W6: clean paraphrase + a TRANSPORT judge_error (advisory-kept by the engine) -> wrapper FLIPS -> K-span.
    w6_quote = f"Service-sector hiring slowed in the final quarter. {_JUDGE_ERROR_SENTINEL}"
    w6 = _basket("w6", "service hiring", w6_quote, "ev_w6")
    pool6 = {"ev_w6": {"evidence_id": "ev_w6", "direct_quote": w6_quote}}
    w6_token = f"[#ev:ev_w6:0-{len(w6_quote)}]"
    w6_draft = f"Hiring in the service sector slowed during the final quarter. {w6_token}"
    # FIRST: prove the BARE engine advisory-KEEPS it (is_verified=True, judge_error=True) — the
    # exact state the wrapper must flip. This is the load-bearing W6 discrimination.
    w6_scoped = {"ev_w6": pool6["ev_w6"]}
    w6_sent = f"Hiring in the service sector slowed during the final quarter. {w6_token}"
    bare6 = base_verify(w6_sent, w6_scoped)
    if not (bool(getattr(bare6, "is_verified", False)) and bool(getattr(bare6, "judge_error", False))):
        _fail("W6_engine_advisory",
              f"the bare engine must advisory-KEEP a transport judge_error (is_verified=True, judge_error=True) "
              f"— the precondition for the wrapper flip; got is_verified={getattr(bare6, 'is_verified', None)!r} "
              f"judge_error={getattr(bare6, 'judge_error', None)!r}")
    wrapped6 = writer_verify(w6_sent, w6_scoped)
    if bool(getattr(wrapped6, "is_verified", False)):
        _fail("W6_wrapper_flip",
              "the writer wrapper must FLIP an advisory judge_error to is_verified=False; got is_verified=True")
    if not any("writer_judge_error_fail_closed" in r for r in (getattr(wrapped6, "failure_reasons", []) or [])):
        _fail("W6_reason",
              f"W6 must fail via writer_judge_error_fail_closed (the P1-1 demotion), distinct from W4's "
              f"entailment_failed; reasons={getattr(wrapped6, 'failure_reasons', None)!r}")
    out6 = _post_tail(w6, pool6, w6_draft, writer_verify)
    if "Hiring in the service sector slowed" in out6:
        _fail("W6_paraphrase_rendered",
              f"an advisory judge_error paraphrase must NEVER render — only the K-span; got {out6!r}")
    if "[#ev:ev_w6:" not in out6 or "Service-sector hiring slowed in the final quarter" not in out6:
        _fail("W6_kspan", f"W6 must fall back to its verbatim K-span; got {out6!r}")

    # ── W7: entails only a same-row LOCAL WINDOW, not the full span -> PASS under True, FAIL under
    # the wrapper's False -> K-span. The cited token spans the WHOLE row, so the FIRST judge call
    # (against the full combined span) sees the trailing NEUTRAL sentinel -> NEUTRAL. The sentence
    # carries a DECIMAL (5.4) that lives near the FRONT of the row, so the NUMERIC local-window rescue
    # finder (_find_local_support_window — ungated by PG_VERIFICATION_MODE) anchors a <=400-char
    # window on the decimal cluster; a long filler tail pushes the sentinel BEYOND that window, so the
    # rescue window is sentinel-free -> the scripted judge grades it ENTAILED. Under
    # allow_local_window_fallback=True the rescue passes (the loophole); the wrapper's False fails it
    # closed on the full-span NEUTRAL before any rescue.
    w7_lead = "Coastal export volumes grew 5.4 percent while domestic demand stayed flat."
    # >400 chars of neutral filler (no decimals, no sentinel) so the numeric rescue window (anchored
    # on the 5.4 cluster near the front) cannot reach the trailing sentinel.
    w7_filler = ("Subsequent commentary in the same report discussed unrelated administrative "
                 "procedures, footnotes, appendices, and methodological notes at considerable "
                 "length, none of which bear on the export figure above, continuing across many "
                 "additional sentences of boilerplate text padding the record well past the "
                 "four-hundred-character rescue window boundary used by the local support finder. ")
    w7_quote = f"{w7_lead} {w7_filler}{_NEUTRAL_SENTINEL}"
    w7 = _basket("w7", "export volumes", w7_quote, "ev_w7")
    pool7 = {"ev_w7": {"evidence_id": "ev_w7", "direct_quote": w7_quote}}
    w7_token = f"[#ev:ev_w7:0-{len(w7_quote)}]"
    # A genuine PARAPHRASE (distinct wording from the verbatim lead) carrying the 5.4 decimal + >=2
    # shared content words ("export"/"volumes"/"domestic"/"demand") so the K-span (the verbatim lead)
    # and the paraphrase are textually distinguishable in the post-tail assertion.
    w7_paraphrase = "Export volumes along the coast rose 5.4 percent even as domestic demand was flat."
    w7_sent = f"{w7_paraphrase} {w7_token}"
    w7_scoped = {"ev_w7": pool7["ev_w7"]}
    # Direction A — the bare verifier with allow_local_window_fallback=True (the K-span path default):
    # the full-span judge is NEUTRAL, but the local-window rescue re-judges a narrower window
    # (sentinel-free) as ENTAILED, so it PASSES. This proves the loophole EXISTS.
    bare7 = base_verify(w7_sent, w7_scoped, allow_local_window_fallback=True)
    if not bool(getattr(bare7, "is_verified", False)):
        _fail("W7_loophole_absent",
              f"W7 must PASS under allow_local_window_fallback=True (the local-window rescue) to prove the "
              f"loophole exists; got is_verified=False ({getattr(bare7, 'failure_reasons', None)!r})")
    # Direction B — the writer wrapper pins allow_local_window_fallback=False, so the full-span
    # NEUTRAL fails closed immediately (no rescue). This proves the WRAPPER closes the loophole.
    wrapped7 = writer_verify(w7_sent, w7_scoped)
    if bool(getattr(wrapped7, "is_verified", False)):
        _fail("W7_wrapper_open",
              "the writer wrapper must CLOSE the local-window loophole (allow_local_window_fallback=False); "
              "got is_verified=True")
    out7 = _post_tail(w7, pool7, w7_sent, writer_verify)
    if "along the coast rose" in out7:
        _fail("W7_local_window_rendered",
              f"a local-window-only paraphrase must NOT render under the writer wrapper; got {out7!r}")
    if "[#ev:ev_w7:" not in out7 or w7_lead.rstrip(".") not in out7:
        _fail("W7_kspan", f"W7 must fall back to its verbatim K-span (the verbatim lead); got {out7!r}")

    # ── W8: sentence->span clean, but DROPS a substantive span numeric -> wrapper completeness guard
    # (writer_numeric_dropped) -> K-span. The span has TWO substantive numerics; the rewrite carries
    # only one. The bare engine (one-directional) passes it; the wrapper must fail it.
    w8_quote = "Treatment response was 13.0 percent in the first arm and 27.0 percent in the second arm."
    w8 = _basket("w8", "treatment response", w8_quote, "ev_w8")
    pool8 = {"ev_w8": {"evidence_id": "ev_w8", "direct_quote": w8_quote}}
    w8_token = f"[#ev:ev_w8:0-{len(w8_quote)}]"
    w8_sent = f"Treatment response reached 13.0 percent in the first arm. {w8_token}"  # drops 27.0
    w8_scoped = {"ev_w8": pool8["ev_w8"]}
    # Direction A — the bare engine PASSES (sentence->span: 13.0 is in the span; it never checks the drop).
    bare8 = base_verify(w8_sent, w8_scoped)
    if not bool(getattr(bare8, "is_verified", False)):
        _fail("W8_engine_should_pass",
              f"the bare one-directional engine must PASS the dropped-numeric rewrite (proving the gap the "
              f"wrapper closes); got is_verified=False ({getattr(bare8, 'failure_reasons', None)!r})")
    # Direction B — the writer wrapper's completeness guard FAILS it (27.0 dropped).
    wrapped8 = writer_verify(w8_sent, w8_scoped)
    if bool(getattr(wrapped8, "is_verified", False)):
        _fail("W8_wrapper_pass",
              "the writer completeness guard must FAIL a dropped span numeric; got is_verified=True")
    if not any("writer_numeric_dropped" in r for r in (getattr(wrapped8, "failure_reasons", []) or [])):
        _fail("W8_reason",
              f"W8 must fail via writer_numeric_dropped (the P1-3 completeness guard); "
              f"reasons={getattr(wrapped8, 'failure_reasons', None)!r}")
    out8 = _post_tail(w8, pool8, w8_sent, writer_verify)
    # The K-span is the verbatim full span, so it is complete by construction (carries BOTH numerics).
    if "13.0" not in out8 or "27.0" not in out8 or "[#ev:ev_w8:" not in out8:
        _fail("W8_kspan",
              f"W8 must fall back to its COMPLETE verbatim K-span (both 13.0 AND 27.0); got {out8!r}")

    print("PASS iarch_beatboth005 abstractive-writer harness (POST-TAIL behavioral, FAIL LOUD): "
          "W1 clean faithful paraphrase RENDERS clean prose (not the K-span — writer fired); "
          "W2 fabricated numeric -> K-span; W3 foreign/garbled token -> K-span; "
          "W4 meaning-distortion (entailment_failed, real NEUTRAL leg) -> K-span; "
          "W5 garbage/empty -> K-span, never empty; "
          "W6 transport judge_error advisory-kept by the engine then FLIPPED by the wrapper "
          "(writer_judge_error_fail_closed) -> K-span; "
          "W7 local-window paraphrase PASSES under allow_local_window_fallback=True but FAILS under the "
          "wrapper's False -> K-span; "
          "W8 dropped span numeric PASSES the bare one-directional engine but FAILS the wrapper "
          "completeness guard (writer_numeric_dropped) -> COMPLETE K-span. "
          "Every fixture asserted THROUGH _rewrite_draft_with_spans (the real render tail), not just the "
          "compose loop. WRITER faked (no spend); W6 JUDGE faked; strict_verify + wrapper + compose + tail "
          "all REAL; faithfulness untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
