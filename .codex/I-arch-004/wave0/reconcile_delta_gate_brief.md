You are a Codex reviewer. Everything you need is INLINE in this message. Do NOT run ANY shell/git/python/pytest command and do NOT read any file — just review the diff below from context and emit the verdict. (Your sandbox cannot run commands here; a command attempt kills your session.)

CONTEXT: The A3 Wave-0 lanes (F01 semaphore, F25 per-query isolation, F03 coverage-floor, F02 blank-completion runaway) were already Codex-APPROVE'd (3 iters each). This diff is a SMALL reconciliation delta applying TWO faithfulness-STRENGTHENING corrections on top of that approved base:

1. F03 strict-by-default: the approved base defaulted PG_MIN_VERIFIED_SECTION_FRACTION to 0.0 (INERT/fail-open — a mostly-gap-stubbed clinical report shipped green unless an operator opted in). This delta makes the floor STRICT BY DEFAULT (DEFAULT_MIN_VERIFIED_SECTION_FRACTION=0.5, enforced with no env opt-in; unset/blank/malformed -> strict default; only an explicit NEGATIVE value disables it). Tests updated from inert-default to strict-default + a behavioral proof.

2. F02 order[0] rotation fallback: the approved base captured the served provider UNCONDITIONALLY (good) but had NO fallback when the provider is UNKNOWN. A fully-dead drb_72 stream emits NO provider field -> served={} -> unconditional-capture alone cannot rotate -> the retry re-POSTs the same stalled provider (allow_fallbacks=false). This delta adds: if no served provider, exclude the pinned current provider = body['provider']['order'][0] (already a slug). Plus a test proving rotation on a no-provider-field dead stream.

HARD CONSTRAINTS: faithfulness gates strengthened NEVER relaxed (§-1.3). Both changes make gates STRICTER. Verdict APPROVE iff zero NOVEL P0 AND zero P1. 101 tests pass (stated, do not run them).

Output ONLY this YAML:
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
remaining_blockers_for_execution: [...]

=== THE DELTA DIFF (review this) ===
### DELTA 1/4: scripts/run_honest_sweep_r3.py (F03 strict default + comment)
--- .claude/worktrees/wf_7ed8eebf-4e3-1/scripts/run_honest_sweep_r3.py	2026-06-14 02:52:14.503453700 -0700
+++ scripts/run_honest_sweep_r3.py	2026-06-14 03:47:25.654076400 -0700
@@ -1402,28 +1402,46 @@
     ]
 
 
+# F03 (A3): STRICT-BY-DEFAULT clinical-safety floor (Codex diff-gate P0: a 0.0
+# default was fail-open — a mostly-gap-stubbed clinical report shipped green unless
+# an operator opted in). The governed default requires a MAJORITY of the attempted
+# sections to produce verified prose: a report whose body is more gap disclosures
+# than verified findings must NOT ship as success. Enforced WITHOUT any env opt-in;
+# the env var only lets an operator move the floor (with sign-off, per the verdict
+# artifact's "Suggested next steps"). A malformed value falls back to the STRICT
+# default (never to 0.0 / fail-open). It STRENGTHENS the success gate only — it never
+# relaxes any faithfulness gate (strict_verify / NLI / 4-role / D8 are upstream).
+DEFAULT_MIN_VERIFIED_SECTION_FRACTION = 0.5
+
+
 def min_verified_section_fraction() -> float:
     """F03 (A3): the success floor on the fraction of attempted sections that
     must produce verified prose. ``PG_MIN_VERIFIED_SECTION_FRACTION`` is a FLOAT
-    in [0, 1]; default 0.0 ⇒ the floor is INERT (byte-identical to the prior
-    behavior — only the ZERO-verified abort fires). A malformed value falls back
-    to 0.0 (fail-open to the prior behavior, never crash the run) and is logged.
-
-    The floor STRENGTHENS the success gate: it only ever turns a would-be
-    success/partial into a NON-success abort; it never relaxes any faithfulness
-    gate (strict_verify / NLI / 4-role / D8 are upstream and unchanged)."""
-    raw = os.getenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0.0")
+    in [0, 1]; default ``DEFAULT_MIN_VERIFIED_SECTION_FRACTION`` (0.5) ⇒ the floor
+    is ENFORCED BY DEFAULT (a mostly-gap-stubbed report aborts with no env opt-in).
+    A malformed value falls back to the STRICT default (NOT 0.0 — never fail-open to
+    shipping a gap-stubbed report) and is logged. Only an EXPLICIT negative value
+    disables the floor (deliberate operator override)."""
+    raw = os.getenv("PG_MIN_VERIFIED_SECTION_FRACTION")
+    if raw is None or raw.strip() == "":
+        return DEFAULT_MIN_VERIFIED_SECTION_FRACTION
     try:
         value = float(raw)
     except (TypeError, ValueError):
         logging.getLogger(__name__).warning(
-            "PG_MIN_VERIFIED_SECTION_FRACTION=%r is not a float; "
-            "using 0.0 (floor inert)", raw,
+            "PG_MIN_VERIFIED_SECTION_FRACTION=%r is not a float; using the strict "
+            "default %.2f (floor stays ENFORCED, never fail-open)",
+            raw, DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
         )
-        return 0.0
+        return DEFAULT_MIN_VERIFIED_SECTION_FRACTION
     # Clamp to [0, 1]; a value > 1 would abort EVERY run (no report can exceed
-    # 100% verified sections), which is a misconfiguration, not a policy.
+    # 100% verified sections), which is a misconfiguration, not a policy. A negative
+    # value is the only way to explicitly DISABLE the floor (deliberate override).
     if value < 0.0:
+        logging.getLogger(__name__).warning(
+            "PG_MIN_VERIFIED_SECTION_FRACTION=%r < 0 explicitly DISABLES the F03 "
+            "clinical-safety floor (operator override).", raw,
+        )
         return 0.0
     if value > 1.0:
         return 1.0
@@ -6676,12 +6694,13 @@
         # mark status=fail_no_verified_prose as a post-hoc flag.
         #
         # F03 (A3): EXTEND the zero-verified gate with a verified-section-FRACTION
-        # floor (PG_MIN_VERIFIED_SECTION_FRACTION, default 0.0 = inert). The
-        # zero-verified case shipped abort_no_verified_sections, but a report where
-        # N-2 of N sections are gap stubs (only a couple verify) previously shipped
-        # as success/partial — a mostly-gap-stubbed clinical report going GREEN.
-        # When the floor is active and the report is below it, abort with a
-        # NON-`partial` status (abort_excessive_gap) so Gate-B fails it (F03 part 2).
+        # floor (PG_MIN_VERIFIED_SECTION_FRACTION, STRICT default 0.5 — ENFORCED with
+        # no env opt-in, per Codex diff-gate P0). The zero-verified case shipped
+        # abort_no_verified_sections, but a report where N-2 of N sections are gap
+        # stubs (only a couple verify) previously shipped as success/partial — a
+        # mostly-gap-stubbed clinical report going GREEN. The floor now fires by
+        # default; below it, abort with a NON-`partial` status (abort_excessive_gap)
+        # so Gate-B fails it (F03 part 2).
         # Both branches share the same fail-closed report+manifest write below.
         verified_sections = filter_verified_sections(multi.sections)
         _total_sections = len(multi.sections)

### DELTA 2/4: tests/polaris_graph/test_f03_min_verified_section_fraction.py (strict tests)
--- .claude/worktrees/wf_7ed8eebf-4e3-1/tests/polaris_graph/test_f03_min_verified_section_fraction.py	2026-06-14 02:55:23.165244600 -0700
+++ tests/polaris_graph/test_f03_min_verified_section_fraction.py	2026-06-14 03:47:14.220341800 -0700
@@ -34,8 +34,9 @@
 
 # ── pure predicate: is_excessive_gap ─────────────────────────────────────────
 
-def test_is_excessive_gap_inert_when_floor_zero() -> None:
-    """Default floor 0.0 ⇒ never fires (byte-identical to the prior behavior)."""
+def test_is_excessive_gap_inert_when_floor_explicitly_zero() -> None:
+    """An EXPLICIT 0.0 floor ⇒ never fires (only reachable via deliberate operator
+    override, no longer the default)."""
     from scripts.run_honest_sweep_r3 import is_excessive_gap
     assert is_excessive_gap(verified_count=1, total_sections=8, min_fraction=0.0) is False
 
@@ -60,26 +61,59 @@
 
 # ── env reader: min_verified_section_fraction ────────────────────────────────
 
-def test_min_verified_section_fraction_default_inert(monkeypatch) -> None:
-    from scripts.run_honest_sweep_r3 import min_verified_section_fraction
+def test_min_verified_section_fraction_default_is_strict(monkeypatch) -> None:
+    """Codex P0: unset MUST enforce the strict floor (0.5), NOT 0.0 (fail-open)."""
+    from scripts.run_honest_sweep_r3 import (
+        DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
+        min_verified_section_fraction,
+    )
     monkeypatch.delenv("PG_MIN_VERIFIED_SECTION_FRACTION", raising=False)
-    assert min_verified_section_fraction() == 0.0
+    assert min_verified_section_fraction() == DEFAULT_MIN_VERIFIED_SECTION_FRACTION
+    assert DEFAULT_MIN_VERIFIED_SECTION_FRACTION == 0.5
+
+
+def test_min_verified_section_fraction_blank_is_strict(monkeypatch) -> None:
+    """An empty/whitespace value is treated as unset ⇒ strict default, never 0.0."""
+    from scripts.run_honest_sweep_r3 import (
+        DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
+        min_verified_section_fraction,
+    )
+    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "   ")
+    assert min_verified_section_fraction() == DEFAULT_MIN_VERIFIED_SECTION_FRACTION
+
+
+def test_strict_default_aborts_mostly_gap_report(monkeypatch) -> None:
+    """End-to-end policy with NO env opt-in: the strict default flags a 1-of-3
+    gap-stubbed report (33% < 50%) as excessive gap (Codex P0 + P2 behavioral proof)."""
+    from scripts.run_honest_sweep_r3 import (
+        is_excessive_gap,
+        min_verified_section_fraction,
+    )
+    monkeypatch.delenv("PG_MIN_VERIFIED_SECTION_FRACTION", raising=False)
+    floor = min_verified_section_fraction()
+    assert is_excessive_gap(verified_count=1, total_sections=3, min_fraction=floor) is True
+    assert is_excessive_gap(verified_count=2, total_sections=3, min_fraction=floor) is False
 
 
 def test_min_verified_section_fraction_reads_env(monkeypatch) -> None:
     from scripts.run_honest_sweep_r3 import min_verified_section_fraction
-    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0.5")
-    assert min_verified_section_fraction() == pytest.approx(0.5)
+    monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0.7")
+    assert min_verified_section_fraction() == pytest.approx(0.7)
 
 
 def test_min_verified_section_fraction_clamps_and_falls_back(monkeypatch) -> None:
-    from scripts.run_honest_sweep_r3 import min_verified_section_fraction
+    from scripts.run_honest_sweep_r3 import (
+        DEFAULT_MIN_VERIFIED_SECTION_FRACTION,
+        min_verified_section_fraction,
+    )
     monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "1.5")
     assert min_verified_section_fraction() == 1.0
+    # An EXPLICIT negative is the deliberate operator disable → 0.0.
     monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "-0.2")
     assert min_verified_section_fraction() == 0.0
+    # Garbage is NOT a disable — it falls back to the STRICT default (never fail-open).
     monkeypatch.setenv("PG_MIN_VERIFIED_SECTION_FRACTION", "garbage")
-    assert min_verified_section_fraction() == 0.0  # fail-open to prior behavior
+    assert min_verified_section_fraction() == DEFAULT_MIN_VERIFIED_SECTION_FRACTION
 
 
 # ── verdict body builder ─────────────────────────────────────────────────────

### DELTA 3/4: src/polaris_graph/llm/openrouter_client.py (order[0] fallback)
--- .claude/worktrees/wf_7ed8eebf-4e3-2/src/polaris_graph/llm/openrouter_client.py	2026-06-14 03:24:09.267750700 -0700
+++ src/polaris_graph/llm/openrouter_client.py	2026-06-14 03:46:34.891630900 -0700
@@ -2014,16 +2014,30 @@
                     # Exclude the blanking provider from the NEXT attempt (mirrors the 4-role
                     # seam idiom, openrouter_role_transport.py:1157-1161): map the served DISPLAY
                     # name back to the routing SLUG so `ignore` uses the SAME identity as `order`.
-                    if _served_provider and isinstance(body.get("provider"), dict):
-                        try:
-                            from src.polaris_graph.roles.provider_routing import (
-                                slug_for_provider,
-                            )
-                            _blanked_slug = slug_for_provider(_served_provider)
-                        except Exception:  # noqa: BLE001 — routing helper must never mask the blank
-                            _blanked_slug = (_served_provider or "").lower() or None
+                    # I-arch-004 F02 (#1255, Codex diff-gate P1): if the served provider is UNKNOWN
+                    # (a fully-dead stream emits no `provider` field — the EXACT drb_72 signature),
+                    # FALL BACK to the pinned CURRENT provider = the first request `order` entry
+                    # (already a slug). With allow_fallbacks=false OpenRouter serves order[0], so
+                    # excluding it forces the retry onto the NEXT provider instead of re-POSTing the
+                    # same stalled one (unconditional-capture alone can't rotate a no-provider-field
+                    # dead stream). Single-entry order -> the retry fails loud, not loops on the stall.
+                    _prov_block = body.get("provider")
+                    if isinstance(_prov_block, dict):
+                        _blanked_slug = None
+                        if _served_provider:
+                            try:
+                                from src.polaris_graph.roles.provider_routing import (
+                                    slug_for_provider,
+                                )
+                                _blanked_slug = slug_for_provider(_served_provider)
+                            except Exception:  # noqa: BLE001 — routing helper must never mask the blank
+                                _blanked_slug = (_served_provider or "").lower() or None
+                        if not _blanked_slug:
+                            _order = _prov_block.get("order") or []
+                            if _order:
+                                _blanked_slug = _order[0]  # order entries are routing slugs already
                         if _blanked_slug:
-                            _ignore_list = body["provider"].setdefault("ignore", [])
+                            _ignore_list = _prov_block.setdefault("ignore", [])
                             if _blanked_slug not in _ignore_list:
                                 _ignore_list.append(_blanked_slug)
                     logger.warning(

### DELTA 4/4: tests/polaris_graph/test_f02_blank_completion_runaway.py (order[0] test)
--- .claude/worktrees/wf_7ed8eebf-4e3-2/tests/polaris_graph/test_f02_blank_completion_runaway.py	2026-06-14 03:37:25.861217700 -0700
+++ tests/polaris_graph/test_f02_blank_completion_runaway.py	2026-06-14 03:48:28.681920200 -0700
@@ -291,6 +291,49 @@
     assert "wandb" in retry_ignore
 
 
+def _sse_blank_death_no_provider() -> list[str]:
+    """SSE chunks for the WORST drb_72 case: a fully-dead stream that emits NO `provider` field at
+    all (just an empty delta then [DONE]). _accumulate_sse returns served={} — so the rotation has
+    NO served identity and MUST fall back to the request order[0]."""
+    return ['data: {"choices": [{"delta": {}}]}', "data: [DONE]"]
+
+
+def test_REAL_sse_path_rotation_falls_back_to_order_when_provider_unknown(monkeypatch):
+    """(b) The order[0] fallback (Codex diff-gate P1): a fully-dead stream that reports NO provider
+    field leaves served={}, so unconditional-capture alone CANNOT rotate. The fallback must exclude
+    the pinned current provider = order[0]. Without it the retry re-POSTs the same stalled provider
+    (allow_fallbacks=false) — the exact drb_72 runaway."""
+    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "wandb,siliconflow,baidu")
+    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
+    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
+    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
+    assert not openrouter_client._pathb_capture.is_active()
+    state = {"n": 0, "bodies": []}
+
+    def _fake_stream(method, url, **kwargs):
+        i = state["n"]
+        state["n"] += 1
+        state["bodies"].append(copy.deepcopy(kwargs.get("json")))
+        lines = _sse_blank_death_no_provider() if i == 0 else _sse_ok_lines()
+        return _FakeStreamResponse(lines)
+
+    monkeypatch.setattr(client._client, "stream", _fake_stream)
+    resp = asyncio.run(
+        client._call_impl(
+            messages=[{"role": "user", "content": "q"}],
+            call_type="contract_slot",
+            reasoning_enabled=False,
+        )
+    )
+    assert resp.content == "the answer"
+    assert state["n"] == 2
+    # No served provider was reported, so the rotation fell back to order[0]=wandb on the retry.
+    first_ignore = (state["bodies"][0].get("provider", {}) or {}).get("ignore", [])
+    retry_ignore = (state["bodies"][1].get("provider", {}) or {}).get("ignore", [])
+    assert "wandb" not in first_ignore
+    assert "wandb" in retry_ignore
+
+
 # --------------------------------------------------------------------------------------------- (c) NARROWNESS
 def test_blank_with_usage_does_not_trip_degenerate_guard(monkeypatch):
     """(c) A blank-CONTENT response that DOES carry a usage block + finish_reason is NOT the
