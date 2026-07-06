HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings; reserve P0/P1 for real execution risks; classify minor items P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Wave-3a U1 diff review — synth-primary ROUTING for corroborated baskets + fire marker (FAITHFULNESS-CRITICAL)

CONTEXT: POLARIS I-deepfix-001 (#1344). The DUAL-APPROVED routing proof found: on gate-B, PG_VERIFIED_COMPOSE_MULTICITED is force-ON, so verified_compose.py routed EVERY >=2-distinct-origin basket to compose_basket_multicited_sentence (the OLD verbatim-K-span path), which NEVER entered the new synth-primary group writer. So corroborated baskets (the core report body) were built by the OLD path even with PG_SYNTH_PRIMARY ON — the "wrong module fires in place of the right one" failure. This diff (Claude-authored, you are the independent gate) routes corroborated baskets THROUGH synth-primary when PG_SYNTH_PRIMARY is ON, and adds the activation fire marker.

REVIEW THE DIFF for these EXACT properties (this is the highest-stakes unit — verification must NOT be relaxed and no corroborator citation may be dropped):
1. **FAITHFULNESS ENGINE BYTE-UNTOUCHED.** The change only alters WHICH composer handles a corroborated basket. strict_verify / the per-sentence verify wrapper `_verify_all_sentences_synth` (same verify_fn, own-region gate, chrome screen) / provenance / span grounding must be logically unchanged. The repair loop was refactored into a shared `_synth_primary_repair_loop` — confirm the moved code is byte-equivalent (the deleted lines 61-76 = the loop body now inside the helper, including the empty-redraft guard). Confirm `_compose_one_basket_synth_primary`'s behavior is unchanged (same kept/failed/body) apart from the marker side-effect.
2. **EVERY CORROBORATOR CITATION PRESERVED (§-1.3 consolidate-keep-all).** The new `compose_basket_multicited_synth_primary`: authored prose ships as primary body, then `_uncited_corroborator_clauses` surfaces every distinct-origin corroborator the authored body did NOT itself cite as its OWN verbatim K-span (carrying its own [#ev] token, re-passing strict_verify). Confirm NO corroborator is dropped — the whole point of the old multicited path was all-corroborator citations; synth-primary must carry them all. If synth-primary authors no surviving prose, it falls back to the UNCHANGED compose_basket_multicited_sentence (which itself surfaces every corroborator) — confirm this is never a single-K-span collapse.
3. **OFF BYTE-IDENTICAL.** PG_SYNTH_PRIMARY unset => `_synth_primary_enabled()` False => the nested gate takes the `else` => the UNCHANGED compose_basket_multicited_sentence (the deleted lines 188-190 re-indented one level into the else, content byte-identical). The new functions are defined but never called when OFF. Confirm the paid-path behavior with the flag OFF is identical to HEAD. (git diff vs git diff -w differ by exactly the 3 re-indent lines — a deliberate nesting, not editor churn.)
4. **FIRE MARKER.** `_emit_synth_primary_marker(kept)` emits the exact literal `[activation] synth_primary: authored_prose kept=<N>` via logger.info ONLY when kept is non-empty (authored prose survived); NEVER on kept=[] (pure disclosure/exhaustion). Confirm it cannot fire on an empty body (that would let the activation canary count a disclosure-only exhaustion as authored prose). STRUCTURAL presence+count, not a threshold.
5. Any P0/P1: a dropped corroborator, a relaxed verify, an OFF-path behavior change, a marker that fires on empty body, a routing case that still sends a corroborated basket to the old path when the flag is ON with a redraft_fn threaded, or any reformat/scope-creep.

THE DIFF (verified_compose.py):
```diff
diff --git a/src/polaris_graph/generator/verified_compose.py b/src/polaris_graph/generator/verified_compose.py
index e065a48c..77b10cc7 100644
--- a/src/polaris_graph/generator/verified_compose.py
+++ b/src/polaris_graph/generator/verified_compose.py
@@ -1437,6 +1437,51 @@ def _synth_primary_fallback_unit(basket: Any, evidence_pool: dict, *, body: str)
     return _no_verified_span_disclosure(basket)
 
 
+def _emit_synth_primary_marker(kept: list) -> None:
+    """Emit the SYNTH_PRIMARY activation fire marker (I-deepfix-001 Wave-3a #1344) — the stable literal
+    the activation canary parses to prove synth-primary actually produced prose. Fires ONLY when authored
+    prose survived (``kept`` non-empty); NEVER on an empty / pure-disclosure return (Fable R5 — a
+    ``kept=[]`` exhaustion is NOT authored prose). Structural presence + count, never a threshold (§-1.3).
+    Side-effect only; the composed text is byte-untouched."""
+    if kept:
+        logger.info("[activation] synth_primary: authored_prose kept=%d", len(kept))
+
+
+def _synth_primary_repair_loop(
+    basket: Any,
+    scoped_pool: dict,
+    regions: dict,
+    *,
+    writer_fn: Callable[[Any, dict], str],
+    verify_fn: Callable[..., Any],
+    redraft_fn: Callable[..., str],
+) -> "tuple[list[str], list[tuple[str, list[str]]]]":
+    """The SYNTH_PRIMARY compose-then-verify + BOUNDED whole-paragraph repair CORE (extracted #1344
+    Wave-3a so BOTH the single-basket and the corroborated-basket synth-primary composers share ONE loop).
+    Draft ONE paragraph via ``writer_fn``, verify EVERY sentence with the UNCHANGED
+    ``_verify_all_sentences_synth`` wrapper (SAME verify_fn, own-region gate, chrome screen), and re-draft
+    up to ``_writer_repair_max()`` times feeding the RARR failure reasons back. Returns ``(kept, failed)``
+    — the verified authored sentences and the residual failures. The faithfulness engine (verify_fn /
+    wrapper / region gate) is BYTE-UNTOUCHED; only which draft is submitted changes, under a finite cap
+    that can never ship a failed sentence."""
+    draft = writer_fn(basket, scoped_pool) or ""
+    kept, failed = _verify_all_sentences_synth(draft, scoped_pool, regions, verify_fn=verify_fn)
+    attempts = 0
+    repair_max = _writer_repair_max()
+    while failed and attempts < repair_max:
+        attempts += 1
+        revise_reasons = _collect_synth_revise_reasons(failed)
+        fresh = redraft_fn(basket, scoped_pool, revise_reasons=revise_reasons) or ""
+        # Codex P0 / Fable P1: an EMPTY re-draft (a 429 storm, a wedged writer abandoned by the async
+        # bridge, or any writer error returning "") must NOT overwrite the prior attempt's verified
+        # sentences with nothing — break and keep the prior kept/failed so the exhaustion path ships the
+        # verified authored body, never collapse a partially-good paragraph because a repair came back empty.
+        if not fresh.strip():
+            break
+        kept, failed = _verify_all_sentences_synth(fresh, scoped_pool, regions, verify_fn=verify_fn)
+    return kept, failed
+
+
 def _compose_one_basket_synth_primary(
     basket: Any,
     evidence_pool: dict,
@@ -1459,23 +1504,14 @@ def _compose_one_basket_synth_primary(
     The faithfulness engine (strict_verify / NLI / D8 / provenance / the writer wrapper) is UNTOUCHED;
     only which draft is submitted changes, under a strict finite cap that can never ship a failed
     authored sentence."""
-    draft = writer_fn(basket, scoped_pool) or ""
-    kept, failed = _verify_all_sentences_synth(draft, scoped_pool, regions, verify_fn=verify_fn)
-    attempts = 0
-    repair_max = _writer_repair_max()
-    while failed and attempts < repair_max:
-        attempts += 1
-        revise_reasons = _collect_synth_revise_reasons(failed)
-        fresh = redraft_fn(basket, scoped_pool, revise_reasons=revise_reasons) or ""
-        # Codex P0 / Fable P1: an EMPTY re-draft (a 429 storm, a wedged writer abandoned by the async
-        # bridge, or any writer error returning "") must NOT overwrite the prior attempt's verified
-        # sentences with nothing. Break and keep the prior kept/failed so the exhaustion path ships the
-        # verified authored body + labeled K-span — never collapse a partially-good paragraph to a bare
-        # disclosure just because a repair call came back empty.
-        if not fresh.strip():
-            break
-        kept, failed = _verify_all_sentences_synth(fresh, scoped_pool, regions, verify_fn=verify_fn)
+    kept, failed = _synth_primary_repair_loop(
+        basket, scoped_pool, regions, writer_fn=writer_fn, verify_fn=verify_fn, redraft_fn=redraft_fn,
+    )
     body = " ".join(kept)
+    # Wave-3a #1344: fire the activation marker ONLY when authored prose survived (Fable R5). When ``kept``
+    # is non-empty the body ALWAYS ships below (as ``body`` or ``body`` + the labeled K-span); an empty
+    # ``kept`` routes to a pure-disclosure fallback and does NOT fire.
+    _emit_synth_primary_marker(kept)
     if not failed:
         # Every sentence covered (or the draft produced nothing). A non-empty body ships as-is; an empty
         # body falls to the K-span / honest-gap fallback (never an empty unit).
@@ -1900,6 +1936,95 @@ def compose_basket_multicited_sentence(
     return build_verified_span_draft(basket, evidence_pool)
 
 
+# ── I-deepfix-001 Wave-3a (#1344) — SYNTH_PRIMARY routing for the CORROBORATED core body ─────────────
+#
+# On gate-B ``PG_VERIFIED_COMPOSE_MULTICITED`` is force-ON, so every corroborated (>=2 distinct-origin
+# SUPPORTS) basket — the §-1.3 consolidate-keep-all CORE report body — was composed by the multi-cited
+# K-span co-location and NEVER reached the SYNTH_PRIMARY group writer. Wave-3a routes those baskets THROUGH
+# synth-primary WHEN ``PG_SYNTH_PRIMARY`` is ON (and a group-capable ``redraft_fn`` is threaded), so the
+# stricter per-sentence writer verify wrapper (``_verify_all_sentences_synth``) composes the coherent body,
+# WHILE every distinct-origin corroborator the authored prose did not itself cite is still surfaced as its
+# OWN verbatim K-span (all-corroborator multi-citation preserved — no corroborating source is dropped).
+# The faithfulness engine is byte-untouched: the authored sentences ran the SAME verify wrapper; the
+# appended clauses are verbatim verified spans; the caller re-runs the UNCHANGED strict_verify. OFF (flag
+# unset OR no ``redraft_fn``) => the multi-cited co-location runs => byte-identical to the pre-Wave-3a path.
+
+
+def _uncited_corroborator_clauses(basket: Any, evidence_pool: dict, body: str) -> list[str]:
+    """VERBATIM K-span clauses for every DISTINCT-ORIGIN corroborator whose citation the synth-primary
+    authored ``body`` did NOT already carry — so routing a corroborated basket THROUGH synth-primary
+    (Wave-3a #1344) never DROPS a corroborating source (§-1.3 consolidate-keep-all). Each clause is the
+    member's OWN verified verbatim span (``_member_verbatim_clause`` -> ``build_verified_span_draft`` over a
+    1-member sub-basket) carrying its OWN ``[#ev]`` token, so it re-passes the UNCHANGED strict_verify
+    trivially — the faithfulness engine is byte-untouched. Order-stable (weight desc, inherited from
+    ``_distinct_origin_supports``); pure read. Returns ``[]`` when the body already cites every origin."""
+    # Map every SUPPORTS member's evidence_id to its ORIGIN — the authored body may cite a NON-representative
+    # member of an origin the distinct-origin roster represents by a DIFFERENT eid (never re-surface it).
+    eid_to_origin: dict[str, str] = {}
+    for m in _basket_supports_members(basket):
+        eid = str(getattr(m, "evidence_id", "") or "")
+        if eid:
+            eid_to_origin[eid] = str(getattr(m, "origin_cluster_id", "") or eid)
+    cited_origins: set[str] = set()
+    for ev_id, _s, _e in _resolved_spans(body):
+        cited_origins.add(eid_to_origin.get(ev_id, ev_id))
+    out: list[str] = []
+    for member in _distinct_origin_supports(basket):
+        origin = str(
+            getattr(member, "origin_cluster_id", "")
+            or getattr(member, "evidence_id", "")
+            or id(member)
+        )
+        if origin in cited_origins:
+            continue
+        verbatim = _member_verbatim_clause(basket, member, evidence_pool)
+        if verbatim and verbatim.strip():
+            cited_origins.add(origin)  # a corroborator now surfaced cannot re-surface
+            out.append(verbatim.strip())
+    return out
+
+
+def compose_basket_multicited_synth_primary(
+    basket: Any,
+    evidence_pool: dict,
+    *,
+    writer_fn: Callable[[Any, dict], str],
+    verify_fn: Callable[..., Any],
+    redraft_fn: Callable[..., str],
+) -> str:
+    """Compose a CORROBORATED (>=2 distinct-origin SUPPORTS) basket THROUGH the SYNTH_PRIMARY group writer
+    (I-deepfix-001 Wave-3a #1344) while PRESERVING all-corroborator multi-citation (§-1.3).
+
+    The synth-primary compose-then-verify + bounded repair core (``_synth_primary_repair_loop`` — the SAME
+    ``_verify_all_sentences_synth`` wrapper / own-region gate / chrome screen as the single-basket path)
+    authors the coherent core body. THEN every distinct-origin corroborator whose citation the authored
+    prose did not itself carry is surfaced as its OWN verbatim K-span clause (``_uncited_corroborator_
+    clauses``) — so NO corroborating source is dropped. When synth-primary authors NO prose (the writer
+    produced nothing that survived verify), fall back to the UNCHANGED multi-cited co-location
+    (``compose_basket_multicited_sentence``), which itself surfaces every corroborator — never a single
+    K-span collapse. Faithfulness: strict_verify / provenance / span-grounding are byte-untouched; the
+    authored sentences ran the stricter writer wrapper and the appended clauses are verbatim verified spans;
+    the caller re-runs the UNCHANGED strict_verify over the rendered draft."""
+    scoped_pool = _basket_scoped_pool(basket, evidence_pool)
+    regions = _basket_member_regions(basket, evidence_pool)
+    kept, _failed = _synth_primary_repair_loop(
+        basket, scoped_pool, regions, writer_fn=writer_fn, verify_fn=verify_fn, redraft_fn=redraft_fn,
+    )
+    body = " ".join(kept)
+    # Wave-3a #1344: fire the activation marker ONLY on a non-empty authored body (Fable R5).
+    _emit_synth_primary_marker(kept)
+    if not body.strip():
+        # Synth-primary authored NO prose for this corroborated basket -> preserve EVERY corroborator via
+        # the UNCHANGED multi-cited co-location (all-corroborator guarantee); never collapse to one K-span.
+        return compose_basket_multicited_sentence(
+            basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
+        ) or ""
+    # Authored coherent prose is the primary body; append a verbatim K-span for any distinct-origin
+    # corroborator it did not already cite so NO corroborating source is dropped (§-1.3).
+    extra = _uncited_corroborator_clauses(basket, evidence_pool, body)
+    return (body + " " + " ".join(extra)) if extra else body
+
+
 # ── I-deepfix-001 Wave-3 PART 1 (#1344) — COMPANION-FIGURE COMPOSE producer ─────────────────────────
 
 
@@ -2318,9 +2443,22 @@ def _compose_section_per_basket(
         # explicitly keeps the default-OFF path byte-identical with NO new import/call when the flag is
         # off, and only invokes the new producer for genuinely-corroborated baskets when on).
         if _multicited_on and len(_distinct_origin_supports(basket)) >= 2:
-            composed = compose_basket_multicited_sentence(
-                basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
-            ) or ""
+            # I-deepfix-001 Wave-3a (#1344): the corroborated (>=2 distinct-origin SUPPORTS) baskets are
+            # the §-1.3 consolidate-keep-all CORE body. When PG_SYNTH_PRIMARY is ON *and* a group-capable
+            # redraft_fn is threaded, compose them THROUGH the synth-primary group writer (the stricter
+            # per-sentence writer verify wrapper + bounded repair) instead of the verbatim-K-span
+            # co-location — while STILL surfacing every distinct-origin corroborator the authored prose did
+            # not itself cite (all-corroborator multi-citation preserved; no verify gate relaxed). Flag OFF
+            # OR no redraft_fn => the UNCHANGED multi-cited co-location => byte-identical to pre-Wave-3a.
+            if redraft_fn is not None and _synth_primary_enabled():
+                composed = compose_basket_multicited_synth_primary(
+                    basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
+                    redraft_fn=redraft_fn,
+                ) or ""
+            else:
+                composed = compose_basket_multicited_sentence(
+                    basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
+                ) or ""
         else:
             composed = _compose_one_basket(
                 basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
```

THE NEW TEST (tests/polaris_graph/test_synth_primary_routing_wave3a.py):
```python
"""I-deepfix-001 Wave-3a (#1344) — SYNTH_PRIMARY routing for the CORROBORATED core body.

Offline unit proof (NO real LLM, NO GPU, NO network — the writer is a STUB, the verifier returns real
``SentenceVerification`` dataclasses, the baskets are in-memory ``SimpleNamespace``) that:

  (a) OFF byte-identical routing — with ``PG_SYNTH_PRIMARY`` unset a corroborated (>=2 distinct-origin
      SUPPORTS) basket STILL routes to the multi-cited K-span co-location (``compose_basket_multicited_
      sentence``), NEVER the synth-primary composer — even when a group-capable ``redraft_fn`` is threaded
      (the flag gates the route, not redraft presence).
  (b) ON route — with ``PG_SYNTH_PRIMARY=1`` and a threaded ``redraft_fn`` the corroborated basket routes
      THROUGH ``compose_basket_multicited_synth_primary`` (the synth-primary group writer), and EVERY
      distinct-origin corroborator the authored prose did not itself cite is still surfaced as its own
      verbatim K-span (§-1.3 consolidate-keep-all — no corroborator citation is dropped).
  (c) Fire marker — ``[activation] synth_primary: authored_prose kept=<N>`` emits with the authored
      sentence count ONLY when authored prose survived, and is ABSENT on an empty / pure-disclosure return
      (Fable R5).

Faithfulness engine (strict_verify / provenance / span-grounding / the writer wrapper) is byte-untouched
by the routing change — these tests exercise WHICH composer runs + that no corroborator is dropped.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import src.polaris_graph.generator.verified_compose as vc
from src.polaris_graph.generator.provenance_generator import SentenceVerification

_FAIL_MARKER = "FAILMEPLEASE"
_LOGGER_NAME = "src.polaris_graph.generator.verified_compose"

_Q1 = "Automation displaced routine manufacturing tasks over the decade."
_Q2 = "Reinstatement effects created new labor tasks in the services sector."


# ── fixtures (mirror the Wave-1a offline harness) ──────────────────────────────────────────────────
def _member(eid: str, quote: str, weight: float = 1.0):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=quote,
        span_verdict="SUPPORTS",
        credibility_weight=weight,
        supporting_members=None,
    )


def _basket(members, subject="AI and labor market outcomes", cluster_id="clust_1"):
    return SimpleNamespace(
        supporting_members=members,
        subject=subject,
        claim_text=subject,
        claim_cluster_id=cluster_id,
    )


def _pool(*members):
    return {m.evidence_id: {"direct_quote": m.direct_quote} for m in members}


def _tok(eid: str, quote: str) -> str:
    return f"[#ev:{eid}:0-{len(quote)}]"


def _line(text: str, eid: str, quote: str) -> str:
    return f"{text} {_tok(eid, quote)}."


def _sv(sentence: str, *, is_verified: bool, reasons=None):
    return SentenceVerification(
        sentence=sentence,
        tokens=[],
        is_verified=is_verified,
        failure_reasons=list(reasons or []),
        judge_error=False,
    )


def _stub_verify(sentence, _scoped_pool, *args, **kwargs):
    """PASS every sentence WITHOUT the fail marker; the real own-region gate then gates the token."""
    if _FAIL_MARKER in sentence:
        return _sv(sentence, is_verified=False, reasons=["stub_entailment_fail"])
    return _sv(sentence, is_verified=True)


def _corroborated_basket():
    m1, m2 = _member("eva", _Q1), _member("evb", _Q2)
    return _basket([m1, m2]), _pool(m1, m2)


def _spy_both(monkeypatch):
    """Wrap BOTH corroborated composers so a test can assert WHICH one the routing chose."""
    calls = {"multicited": 0, "synth": 0}
    real_multi = vc.compose_basket_multicited_sentence
    real_synth = vc.compose_basket_multicited_synth_primary

    def spy_multi(*a, **k):
        calls["multicited"] += 1
        return real_multi(*a, **k)

    def spy_synth(*a, **k):
        calls["synth"] += 1
        return real_synth(*a, **k)

    monkeypatch.setattr(vc, "compose_basket_multicited_sentence", spy_multi)
    monkeypatch.setattr(vc, "compose_basket_multicited_synth_primary", spy_synth)
    return calls


# ── (a) OFF byte-identical routing ─────────────────────────────────────────────────────────────────
def test_off_corroborated_routes_to_multicited_not_synth(monkeypatch):
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    monkeypatch.delenv("PG_SYNTH_PRIMARY", raising=False)
    basket, pool = _corroborated_basket()
    calls = _spy_both(monkeypatch)

    # redraft_fn is threaded, yet with the flag OFF the corroborated basket MUST still take the
    # multi-cited co-location (the flag gates the route, not the presence of redraft_fn).
    vc._compose_section_per_basket(
        [basket], pool,
        writer_fn=lambda _b, _p: _line("Automation reshaped the labour market", "eva", _Q1),
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: "",
    )
    assert calls["multicited"] == 1
    assert calls["synth"] == 0


def test_on_but_no_redraft_still_multicited(monkeypatch):
    """The synth-primary route requires BOTH the flag AND a threaded redraft_fn — flag alone keeps the
    corroborated basket on the multi-cited co-location (byte-identical)."""
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    basket, pool = _corroborated_basket()
    calls = _spy_both(monkeypatch)

    vc._compose_section_per_basket(
        [basket], pool,
        writer_fn=lambda _b, _p: _line("Automation reshaped the labour market", "eva", _Q1),
        verify_fn=_stub_verify,
        # redraft_fn omitted (defaults None) => the AND-guard keeps the multi-cited path.
    )
    assert calls["multicited"] == 1
    assert calls["synth"] == 0


# ── (b) ON route + all-corroborator preservation ────────────────────────────────────────────────────
def test_on_corroborated_routes_to_synth_primary(monkeypatch):
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()
    calls = _spy_both(monkeypatch)

    authored = _line("Automation reshaped the labour market", "eva", _Q1)
    vc._compose_section_per_basket(
        [basket], pool,
        writer_fn=lambda _b, _p: authored,
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
    )
    assert calls["synth"] == 1
    assert calls["multicited"] == 0  # the OLD multi-cited K-span path did NOT compose the core body


def test_synth_primary_preserves_every_corroborator_citation(monkeypatch):
    """The synth-primary authored body cites ONLY corroborator eva; evb (the un-cited corroborator) is
    surfaced as its OWN verbatim K-span so NO corroborating source is dropped (§-1.3)."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()

    authored = _line("Automation reshaped the labour market", "eva", _Q1)  # cites eva only
    out = vc.compose_basket_multicited_synth_primary(
        basket, pool,
        writer_fn=lambda _b, _p: authored,
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
    )
    assert authored in out          # the synth-primary authored prose is the primary body
    assert "[#ev:eva:" in out       # corroborator eva (cited by the writer)
    assert "[#ev:evb:" in out       # corroborator evb surfaced as its verbatim K-span (never dropped)
    assert _FAIL_MARKER not in out


def test_synth_primary_falls_back_to_multicited_when_no_authored_prose(monkeypatch):
    """When synth-primary authors NO prose (every draft sentence fails verify), the corroborated basket
    falls back to the UNCHANGED multi-cited co-location — which itself surfaces every corroborator — never
    a single-K-span collapse."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()

    bad = f"{_FAIL_MARKER} this authored sentence never verifies."
    out = vc.compose_basket_multicited_synth_primary(
        basket, pool,
        writer_fn=lambda _b, _p: bad,
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: bad,
    )
    assert out.strip() != ""        # never a silent empty
    assert _FAIL_MARKER not in out  # the failed authored draft never ships
    assert "[#ev:eva:" in out       # both corroborators still surfaced via the multi-cited fallback
    assert "[#ev:evb:" in out


# ── (c) fire marker ─────────────────────────────────────────────────────────────────────────────────
def _synth_primary_markers(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if "[activation] synth_primary:" in r.getMessage()
    ]


def test_fire_marker_emits_kept_count_on_authored_body(monkeypatch, caplog):
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()
    authored = _line("Automation reshaped the labour market", "eva", _Q1)

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        vc.compose_basket_multicited_synth_primary(
            basket, pool,
            writer_fn=lambda _b, _p: authored,
            verify_fn=_stub_verify,
            redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
        )
    # exactly ONE authored sentence survived => kept=1 (structural count, never a threshold).
    assert _synth_primary_markers(caplog) == ["[activation] synth_primary: authored_prose kept=1"]


def test_fire_marker_absent_on_empty_authored_body(monkeypatch, caplog):
    """Fable R5: an empty / pure-disclosure return (no authored prose survived) must NOT fire the
    marker — else the canary would count a disclosure-only exhaustion as 'synth-primary produced prose'."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()
    bad = f"{_FAIL_MARKER} this authored sentence never verifies."

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        vc.compose_basket_multicited_synth_primary(
            basket, pool,
            writer_fn=lambda _b, _p: bad,
            verify_fn=_stub_verify,
            redraft_fn=lambda _b, _p, *, revise_reasons=None: bad,
        )
    assert _synth_primary_markers(caplog) == []  # never fire on an empty authored body


def test_single_source_synth_primary_also_emits_marker(monkeypatch, caplog):
    """The refactored single-basket synth-primary path (_compose_one_basket -> _compose_one_basket_synth_
    primary) still emits the marker when it authors prose (kept=1), proving the marker fires on BOTH the
    single-source and corroborated composers."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    m = _member("eva", _Q1)
    basket, pool = _basket([m]), _pool(m)
    authored = _line("Automation reshaped the labour market", "eva", _Q1)

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        out = vc._compose_one_basket(
            basket, pool,
            writer_fn=lambda _b, _p: authored,
            verify_fn=_stub_verify,
            redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
        )
    assert out == authored
    assert _synth_primary_markers(caplog) == ["[activation] synth_primary: authored_prose kept=1"]
```

OUTPUT SCHEMA (return exactly):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
faithfulness_untouched: true|false
every_corroborator_preserved: true|false
off_byte_identical: true|false
marker_empty_body_safe: true|false
convergence_call: continue | accept_remaining
notes: <short>
```
APPROVE iff faithfulness untouched, every corroborator preserved, OFF byte-identical, marker empty-body-safe, and zero P0/P1.
