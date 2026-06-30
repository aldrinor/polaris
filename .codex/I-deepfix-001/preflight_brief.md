HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex consolidated-diff gate — I-deepfix-001 (#1344) deepfix preflight, ITER 2

You are the ONLY binding code-review authority for this gate. Review the consolidated diff
of the drb_72 deepfix files (4 src + 2 tests, 492 insertions). The diff is the ACTUAL
working-tree code under `C:/POLARIS` (read-only sandbox). The diff is reproduced inline
below, AND on disk at `.codex/I-deepfix-001/preflight_consolidated.diff` — you MUST read the
FULL files for surrounding context, not just the hunks:

- `scripts/run_honest_sweep_r3.py` (FIX-1, ~14567-14635; also read `recover_seam_partial_verdicts`, `build_seam_release_outcome`, and the seam-release redactor)
- `src/polaris_graph/roles/openrouter_role_transport.py` (FIX-2, ~1185-1300; read `_build_openrouter_body`, `_JUDGE_MAX_TOKENS_CHAIN_MIN`, the sentinel/mirror/judge branches, and `finalize_body` A2-CLAMP)
- `src/polaris_graph/generator/multi_section_generator.py` (FIX-3, ~3915-4200; read `_build_verified_span_draft`, `_run_section`, `_substantive_units`, and `weighted_enrichment.py` for `_row_relevance` + `is_render_chrome_or_unrenderable`)
- `src/polaris_graph/retrieval/contradiction_detector.py` (FIX-4, ~316-411 and 1735-1948; read `_find_value_generic`, `detect_contradictions`, `_a17_guard_enabled`, `_group_incommensurable_reason`, `ContradictionRecord`, `ExtractedNumericClaim`)
- `tests/polaris_graph/test_deepfix_contradiction_unitless_p1.py` (NEW — the iter-1 P1 regression lock)
- `tests/roles/test_openrouter_role_transport_meta007.py` (updated to the FIX-2 knob)

## THE 4 FIXES (consolidated diff, drb_72 deepfix campaign I-deepfix-001)

**FIX-1** `scripts/run_honest_sweep_r3.py:14570-14632` — on a 4-role D8 SEAM TEAR
(timeout/error), re-invoke the PURE deterministic `four_role_input_builder` and persist
`four_role_claim_audit.json` byte-identically to the success path
(`sweep_integration.py:1210`), so the redactor takes the SURGICAL per-claim path (ships
VERIFIED, quarantines rest) instead of the audit-map-missing WHOLE-BODY withhold that was
discarding 58 D8-VERIFIED claims. Unsettled-but-kept claims folded into `final_verdicts` as
non-VERIFIED "UNADJUDICATED" (a real settled verdict always wins). Coverage stays the
conservative proxy -> status can only be `released_with_disclosed_gaps`/`held`, never
`success`. Fail-safe: any error preserves the prior fail-closed withhold byte-for-byte.
Default-on, no new flag.

**FIX-2** `src/polaris_graph/roles/openrouter_role_transport.py:1288-1300` — the per-claim D8
verdict-JUDGE else-branch of `_build_openrouter_body` was reserving max_tokens=262140
(I-arch-003 "max max" mis-applied to a verdict) -> 193x HTTP-429 + 67x HTTP-400
context-overrun -> seam timeout. Now reserves `PG_D8_VERDICT_MAX_TOKENS` default **16384**
(parse-guarded, clamped to `_JUDGE_MAX_TOKENS_CHAIN_MIN`). **ITER-2: the default was RAISED
from the iter-1 4000 to 16384** (I-meta-008's generous-but-bounded judge budget) because
effort=xhigh allocates ~95% of max_tokens to reasoning, so a 4000 cap risked STARVING the
bare verdict to empty (the I-meta-008 failure / §9.1.8 "never starve"); 16384 leaves ample
room AND still reserves ~16x fewer tokens than 262140 + stays well under the 262144 window.
Sentinel/Mirror branches + generator path UNTOUCHED. Faithfulness-neutral.

**FIX-3** `src/polaris_graph/generator/multi_section_generator.py:3918-4192` — at the FIX-K
verified-span render (`_evsr`), added (a) `_compose_relevance_floored_ev_ids`: holds OFF-TOPIC
weight-~0 sources out of the COMPOSED findings only when KNOWN `selection_relevance <
PG_COMPOSE_RELEVANCE_FLOOR` (default 0.10); missing score = keep-NEUTRAL; (b)
`_screen_fixk_render_chrome` reusing the shared `is_render_chrome_or_unrenderable` predicate
+ 3 precision-anchored leak classes (author byline / bare contact-email masthead /
service-sunset nav). Render-only, fail-safe lossless segmentation; held sources STAY in
`evidence_pool` + disclosed pool (COMPOSE-boundary withhold, NOT a B18 selection-drop).
`PG_COMPOSE_RELEVANCE_FLOOR=0.0` kill-switch.

**FIX-4** `src/polaris_graph/retrieval/contradiction_detector.py:319-411,1740-1948` — stop the
extractor lifting identifier fragments (bare arXiv YYMM.NNNNN MONTH-VALIDATED, law/statute
hyphen-tails) as metric values; gate the unit-less comparison. **ITER-2 (this addresses the
iter-1 P1): the `not_comparable` relabel now REQUIRES POSITIVE count-scale evidence** — at
least one operand >= `PG_CONTRADICTION_RAW_COUNT_FLOOR` (default 100). A real unit-less metric
(hazard ratio / odds ratio / risk ratio / index) is ~always < 100, so a >= 100 operand is a
count/sample-size/identifier lifted as a value. WITHOUT such an operand a >1000% spread is
left as a REAL same-metric contradiction (hazard ratio 0.5 vs 8.0, rel 1500%, is NEVER
suppressed) — fixing the iter-1 P1 where the spurious-magnitude arm fired on EVERY unit-less
group. The forensic 0-1-ratio-vs-3682-count case still relabels `not_comparable` (magnitude
nulled, all sources DISCLOSED). Shares the A17 flag. IMPROVES faithfulness. Locked by
`tests/polaris_graph/test_deepfix_contradiction_unitless_p1.py` (2 cases: HR 0.5-vs-8.0 still
flagged; 0.62-vs-3682 not_comparable).

**P2 cleanups** (iter-1 non-blocking, now done): bare-arXiv regex MONTH-VALIDATED
(`\d{2}(0[1-9]|1[0-2])\.` — a real NNNN.NNNN metric whose 3rd-4th digits aren't 01-12 is no
longer screened); `tests/roles/test_openrouter_role_transport_meta007.py` updated to
`PG_D8_VERDICT_MAX_TOKENS` / 16384 (3 tests).

**INVARIANTS:** faithfulness engine (strict_verify / NLI / 4-role D8 / provenance /
span-grounding) UNTOUCHED; §-1.3 WEIGHT-not-FILTER / no silent-drop; surgical not rewrites.
ALL offline tests pass: 6 transport + 66 contradiction + 2 new P1 regression.

## REVIEW ASK (this is ITER 2)

Verify the iter-1 P1 is CLEARED and no NEW P0/P1 was introduced.

The iter-1 P1 was: **FIX-4's spurious-magnitude arm fired on EVERY unit-less group,
suppressing a genuine unit-less SAME-metric contradiction** (hazard ratio / odds ratio /
index, >1000% spread). ITER-2 fix: the `not_comparable` relabel now REQUIRES a count-scale
operand (>= `PG_CONTRADICTION_RAW_COUNT_FLOOR`, default 100).

VERIFY:
1. **FIX-4 iter-2 relabel-gate** — trace `_group_scale_not_comparable` +
   `detect_contradictions` (~1736-1948): confirm the `if not has_count: return ""` early-out
   restores the real HR-0.5-vs-8.0 contradiction (a genuine sub-100 unit-less spread is left
   as a REAL contradiction, magnitude preserved, `not_comparable=False`) while STILL
   suppressing the 0.62-vs-3682 forensic case (`has_ratio and has_count` ->
   incompatible-scales). Confirm the two regression cases in
   `test_deepfix_contradiction_unitless_p1.py` actually exercise this and that the asserts are
   correct (not vacuous).
2. **FIX-2 iter-2 default RAISE 4000 -> 16384** — confirm it (i) still kills the 262140
   blowup (16384 << 262144 window, ~16x fewer reserved tokens, A2-CLAMP never needs to fire),
   (ii) RESPECTS §9.1.8 "never starve" (effort=xhigh ~95% reasoning -> a 4000 cap could
   truncate the verdict to empty; 16384 leaves room), (iii) is scoped to the JUDGE else-branch
   only, sentinel/mirror/generator untouched, and the meta007 test updates (the `== 16384`
   assert + the `PG_D8_VERDICT_MAX_TOKENS` rename in the override + clamp tests) are
   internally consistent with the code path (including the 999999-override -> 260092 A2-CLAMP
   still holding).
3. **Re-verify the still-standing concerns:**
   - (a) FIX-3 `PG_COMPOSE_RELEVANCE_FLOOR` is a COMPOSE-boundary withhold (held source stays
     in `evidence_pool` + disclosed pool), NOT the B18-forbidden selection-relevance hard-drop.
     Confirm `_compose_relevance_floored_ev_ids` only narrows the ev_id list passed to
     `_build_verified_span_draft` and never mutates `evidence_pool` / selection / disclosure.
   - (b) FIX-1 re-invokes `four_role_input_builder` a SECOND time on the rescue path
     (pure / zero-spend — no network, no LLM) and must NEVER ship an unsettled claim AS
     VERIFIED (UNADJUDICATED = non-VERIFIED, never overwrites a settled verdict, routes through
     quarantine; coverage stays conservative so status can only be
     released_with_disclosed_gaps/held). Confirm the fail-safe preserves the prior withhold
     byte-for-byte on any error.
   - (c) the P2-2 month-validated arXiv regex `\b\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?\b`
     doesn't screen a real unit-less metric, and the hyphen-tail reject in `_find_value_generic`
     cannot suppress a legitimate standalone negative value.

Also scan for any NEW execution risk introduced since iter 1: crash / None-deref / regex
catastrophic-backtrack / import-cycle / exception escaping a fail-safe. Front-load every real
finding now (5-cap, no iter 6). Reserve P0/P1 for real execution/faithfulness risks; classify
nits as P2/P3.

## OUTPUT SCHEMA (§8.3.9) — emit EXACTLY this, the final `verdict:` line is parsed by CI:

```
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected. The FINAL line of your output MUST be `verdict: APPROVE` or
`verdict: REQUEST_CHANGES`. APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## CONSOLIDATED DIFF (inline)

```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index c7c982a3..9df30dc0 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -14567,6 +14567,69 @@ async def run_one_query(
                         _seam_partial_coverage,
                         _seam_partial_settled,
                     ) = recover_seam_partial_verdicts(run_dir, _seam_total_claims)
+                # I-deepfix-001 FIX-1 (#1344) AUDIT-MAP-FROM-PARTIALS (keystone): on a torn seam the
+                # per-claim audit map (four_role_claim_audit.json) was NEVER written — sweep_integration
+                # writes it ONLY after run_four_role_evaluation returns, which a timed-out / errored seam
+                # never reaches. The post-seam redactor then finds the map MISSING and (under
+                # always-release) WITHHOLDS THE WHOLE findings body — discarding the D8-VERIFIED backbone
+                # too. That over-withhold is the §-1.3 violation: a seam timeout should keep ALL VERIFIED
+                # claims and surgically quarantine only the rest. The seam input builder is a PURE,
+                # deterministic function of the finished `multi` report (NO network, NO spend), so
+                # RE-DERIVE the full per-claim audit map here and PERSIST it, so the redactor can locate
+                # every claim's verbatim sentence: ship the VERIFIED, quarantine/label the non-VERIFIED.
+                # We ALSO fold every kept claim the seam never SETTLED into the verdict map as a
+                # non-VERIFIED "UNADJUDICATED" placeholder, so an un-adjudicated kept sentence is
+                # quarantined/labeled and NEVER ships as verified (settled verdicts WIN over the
+                # placeholder). Coverage stays the conservative `_seam_partial_coverage` (unchanged), so a
+                # timeout can still only resolve to released_with_disclosed_gaps / held — never a false
+                # full-certify. FAIL-SAFE: ANY failure leaves the prior behaviour (audit map absent ->
+                # redactor withholds the body) byte-unchanged. Builder path only (the static path mints no
+                # audit map). Faithfulness-STRICT: only VERIFIED claims survive as verified — strictly
+                # safer than the engine's intent, never a gate relaxation.
+                if four_role_input_builder is not None and run_dir is not None:
+                    _seam_audit_map: "dict[str, dict]" = {}
+                    try:
+                        _seam_recovery_bundle = four_role_input_builder(
+                            multi=multi,
+                            template=_template,
+                            slug=q["slug"],
+                            domain=q["domain"],
+                            ev_pool=ev_pool,
+                        )
+                        _seam_audit_map = dict(getattr(_seam_recovery_bundle, "audit_map", {}) or {})
+                    except Exception as _seam_audit_exc:  # noqa: BLE001 — FAIL-SAFE: keep prior withhold
+                        _log(
+                            "[four_role]   SEAM audit-map re-derive FAILED (kept prior body-withhold "
+                            f"behaviour): {type(_seam_audit_exc).__name__}: {str(_seam_audit_exc)[:120]}"
+                        )
+                    if _seam_audit_map:
+                        try:
+                            (run_dir / "four_role_claim_audit.json").write_text(
+                                json.dumps(_seam_audit_map, indent=2, sort_keys=True) + "\n",
+                                encoding="utf-8",
+                            )
+                        except OSError as _seam_audit_io:  # noqa: BLE001 — write best-effort, fail-safe
+                            _log(
+                                "[four_role]   SEAM audit-map write FAILED (kept prior body-withhold "
+                                f"behaviour): {_seam_audit_io}"
+                            )
+                            _seam_audit_map = {}
+                    if _seam_audit_map:
+                        # Treat EVERY kept claim the seam never settled as non-VERIFIED so the redactor
+                        # quarantines/labels it (never ships an un-adjudicated claim as verified). A real
+                        # SETTLED verdict (VERIFIED/UNSUPPORTED/...) is authoritative and is never
+                        # overwritten by the placeholder.
+                        _seam_unadjudicated = 0
+                        for _seam_cid in _seam_audit_map:
+                            if _seam_cid not in _seam_partial_verdicts:
+                                _seam_partial_verdicts[_seam_cid] = "UNADJUDICATED"
+                                _seam_unadjudicated += 1
+                        _log(
+                            "[four_role]   SEAM audit-map re-derived from partials: "
+                            f"{len(_seam_audit_map)} claims (settled={_seam_partial_settled}, "
+                            f"unadjudicated->quarantine={_seam_unadjudicated}); VERIFIED backbone "
+                            "ships, non-VERIFIED surgically quarantined (was: whole-body withhold)"
+                        )
                 _seam_release_outcome, _seam_body_withheld, _seam_withhold_reason = (
                     build_seam_release_outcome(
                         sections=multi.sections,
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 0fcc5b4b..2204fa8b 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -3915,6 +3915,153 @@ def _normalize_citation_punctuation(text: str) -> str:
     return _MISSING_TERMINATOR_RE.sub(lambda m: "." + m.group(2) + " ", text)
 
 
+# ─────────────────────────────────────────────────────────────────────────────
+# I-deepfix-001 (#1344) FIX-3 — COMPOSE-time render-cleanliness gate for the FIX-K
+# deterministic verified-span dump (drb_72 forensic root cause). The "Corroborated
+# Weighted Findings" enrichment section RAW-DUMPS each verified span; the forensic found
+# it shipped (a) page-furniture CHROME as findings (a bare contact email, a "Written by
+# <Name>" byline, a "<X> website will be retired" service-sunset nav line — chrome that
+# IS the verbatim span and so passes provenance) and (b) OFF-TOPIC weight-~0 sources
+# composed as findings (legal-aid / nationhood-sociology / bankruptcy / a Dunzo teaching
+# case for a clinical question) because relevance is computed but not enforced at compose.
+#
+# Both filters are RENDER-ONLY and faithfulness-NEUTRAL. A held source/span STAYS in
+# ``evidence_pool`` and in the disclosed pool — it is only kept OUT OF THE COMPOSED
+# FINDINGS. No faithfulness gate (strict_verify / NLI / 4-role D8 / provenance span-
+# grounding) is touched. §-1.3 WEIGHT-not-FILTER is preserved exactly: this is a render
+# seam that WITHHOLDS a unit from the rollup (the same category as the chrome screen), at
+# the COMPOSE boundary AFTER selection/disclosure — NOT the forbidden re-imposition of a
+# hard ``selection_relevance < floor`` DROP at the selection boundary (B18), which would
+# delete a source from the corpus. A missing/unparseable score is keep-NEUTRAL.
+_COMPOSE_RELEVANCE_FLOOR_ENV = "PG_COMPOSE_RELEVANCE_FLOOR"
+_DEFAULT_COMPOSE_RELEVANCE_FLOOR = 0.10
+
+
+def _compose_relevance_floor() -> float:
+    """The compose-time topicality floor (env ``PG_COMPOSE_RELEVANCE_FLOOR``, default 0.10),
+    parse-guarded to [0.0, 1.0] (LAW VI). ``0.0`` disables the gate (no score is < 0.0)."""
+    raw = os.environ.get(_COMPOSE_RELEVANCE_FLOOR_ENV)
+    if raw is None or not str(raw).strip():
+        return _DEFAULT_COMPOSE_RELEVANCE_FLOOR
+    try:
+        val = float(str(raw).strip())
+    except (TypeError, ValueError):
+        return _DEFAULT_COMPOSE_RELEVANCE_FLOOR
+    if val != val:  # NaN guard
+        return _DEFAULT_COMPOSE_RELEVANCE_FLOOR
+    return min(1.0, max(0.0, val))
+
+
+def _compose_relevance_floored_ev_ids(ev_ids: Any, evidence_pool: Any) -> list[str]:
+    """The caller-ordered ev_id list with off-topic weight-~0 rows held OUT OF THE COMPOSED
+    findings (drb_72 forensic). A row is held ONLY when its KNOWN topicality score
+    (``selection_relevance`` via the shared ``_row_relevance`` reader) is below the floor; a
+    missing/unparseable score is keep-NEUTRAL (never held) — identical to the selection
+    ordering's missing-relevance handling. The held rows REMAIN in ``evidence_pool`` and in
+    the disclosed pool (§-1.3 WEIGHT-not-FILTER); they are only not COMPOSED as findings."""
+    from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
+        _row_relevance,
+    )
+
+    floor = _compose_relevance_floor()
+    pool = evidence_pool or {}
+    kept: list[str] = []
+    for ev_id in (ev_ids or []):
+        eid = str(ev_id or "")
+        if not eid:
+            continue
+        rel = _row_relevance(pool.get(eid))
+        if rel is not None and rel < floor:
+            continue  # off-topic weight-~0 row: held from the render, KEPT in the pool
+        kept.append(eid)
+    return kept
+
+
+# Per-span chrome leak classes the SHARED render-chrome predicate (is_render_chrome_or_
+# unrenderable) does NOT yet catch — the exact drb_72 forensic leaks. Structure-anchored /
+# precision-first: a real finding never OPENS "Written by <Name>", is never a lone contact
+# email (near-empty once the email token is removed), and never says a website/service "will
+# be retired" — so a real verbatim claim is never dropped (precision over recall on a drop
+# path, per the I-wire-013/016 chrome-rule convention).
+_FIXK_BYLINE_RE = re.compile(
+    r"^(?:[Ww]ritten|[Pp]osted|[Rr]eviewed|[Ee]dited|[Aa]uthored|[Rr]eported|[Cc]ompiled)"
+    r"\s+[Bb]y\s+[A-Z][a-z]+",
+)
+_FIXK_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
+_FIXK_SERVICE_SUNSET_RE = re.compile(
+    r"\b(?:web\s?site|website|service|site|platform|portal|product|page|database|app|system)\b"
+    r"[^.]{0,40}\bwill be\s+(?:retired|discontinued|shut\s?down|decommissioned|sunset|"
+    r"deprecated|removed|unavailable)\b",
+    re.IGNORECASE,
+)
+_FIXK_TRAILING_MARKERS_RE = re.compile(r"(?:\s\[[^\[\]]+\])+\.?\s*$")
+_FIXK_ALPHA_WORD_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
+_COMPOSE_EMAIL_RESIDUE_WORD_FLOOR = 4  # < this many real words once the email is removed => a contact masthead
+# A FIX-K unit is "<core, no [ ] brackets> [eid][eid].": ``_substantive_units`` rejects any
+# unit containing "[" or "]", so the ONLY bracketed tokens in the joined draft are the ev-id
+# markers and every unit reliably ends with one-or-more " [eid]" markers + ".". Each ``\S``-
+# anchored match is exactly one space-joined ``_emit_unit`` part (byte-identical span).
+_FIXK_UNIT_RE = re.compile(r"\S.*?(?:\s\[[^\[\]]+\])+\.")
+
+
+def _is_compose_email_masthead(core: str) -> bool:
+    """True iff ``core`` (markers stripped) is a contact-email masthead: it carries an email AND,
+    once the email token is removed, has fewer than the residue word floor of real words. A real
+    finding that merely cites an email keeps substantial surrounding prose and is NOT flagged."""
+    if not _FIXK_EMAIL_RE.search(core):
+        return False
+    residue = _FIXK_EMAIL_RE.sub(" ", core)
+    return len(_FIXK_ALPHA_WORD_RE.findall(residue)) < _COMPOSE_EMAIL_RESIDUE_WORD_FLOOR
+
+
+def _is_compose_render_chrome(unit: str, shared_predicate: Any) -> bool:
+    """True iff a FIX-K verbatim unit is render chrome: the SHARED predicate (reused — the strong
+    detector) OR one of the three named leak classes it does not yet catch (author byline / bare
+    contact-email / service-sunset nav). SUPPRESS-ONLY — never touches a faithfulness verdict; the
+    source stays in the pool."""
+    if shared_predicate(unit):
+        return True
+    core = _FIXK_TRAILING_MARKERS_RE.sub("", unit).strip()
+    if _FIXK_BYLINE_RE.match(core):
+        return True
+    if _is_compose_email_masthead(core):
+        return True
+    return bool(_FIXK_SERVICE_SUNSET_RE.search(core))
+
+
+def _screen_fixk_render_chrome(raw_draft: str) -> str:
+    """Drop page-furniture chrome SPANS from the FIX-K verbatim-span dump before render.
+
+    Each emitted unit is re-screened through the SHARED render-chrome predicate
+    (``is_render_chrome_or_unrenderable``) PLUS the three named leak classes it does not yet
+    catch (drb_72 forensic). A chrome unit is dropped from the rendered draft; the SOURCE is
+    untouched (it remains in ``evidence_pool`` + disclosure). FAIL-SAFE: if the draft cannot be
+    losslessly segmented into marker-terminated units, it is returned UNCHANGED (never risk
+    dropping a real verbatim span on a parse miss). An all-chrome draft collapses to "" => the
+    caller renders its gap stub (never a silent success)."""
+    if not raw_draft or not raw_draft.strip():
+        return raw_draft
+    units = _FIXK_UNIT_RE.findall(raw_draft)
+    if not units:
+        return raw_draft
+    # FAIL-SAFE: the ``\S``-anchored marker-terminated units must reconstruct the draft EXACTLY
+    # (they are the original space-joined parts). A mismatch means the unit shape assumption broke
+    # for this draft -> keep the raw draft rather than risk dropping or corrupting a real span.
+    if " ".join(units) != raw_draft:
+        return raw_draft
+    from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
+        is_render_chrome_or_unrenderable,
+    )
+    kept = [u for u in units if not _is_compose_render_chrome(u, is_render_chrome_or_unrenderable)]
+    dropped = len(units) - len(kept)
+    if dropped:
+        logger.info(
+            "[multi_section] FIX-K render-chrome screen dropped %d/%d span(s)",
+            dropped, len(units),
+        )
+    return " ".join(kept)
+
+
 async def _run_section(
     section: SectionPlan,
     evidence_pool: dict[str, dict[str, Any]],
@@ -4029,12 +4176,20 @@ async def _run_section(
         # post-_call_section draft. Zero token cost; empty atom catalog (no
         # generated atoms). An empty draft => strict_verify keeps 0 => the
         # section renders its gap stub (never a silent success).
-        raw = _build_verified_span_draft(section.ev_ids, evidence_pool)
+        # I-deepfix-001 (#1344) FIX-3: COMPOSE-time render-cleanliness gate (drb_72 forensic).
+        # (a) hold off-topic weight-~0 sources OUT OF THE COMPOSED findings (they stay in the
+        # pool + disclosure — §-1.3 WEIGHT-not-FILTER); (b) drop page-furniture chrome SPANS
+        # (author masthead / email / byline / service-sunset nav) before they enter the dump.
+        # Both are RENDER-ONLY and faithfulness-neutral; the source is never dropped from the
+        # corpus. See the _compose_relevance_floored_ev_ids / _screen_fixk_render_chrome helpers.
+        _compose_ev_ids = _compose_relevance_floored_ev_ids(section.ev_ids, evidence_pool)
+        raw = _build_verified_span_draft(_compose_ev_ids, evidence_pool)
+        raw = _screen_fixk_render_chrome(raw)
         in_tok = out_tok = 0
         section_atom_catalog = {}
         logger.info(
-            "[multi_section] %s FIX-K verified-span render: sources=%d draft_chars=%d",
-            section.title, len(section.ev_ids or []), len(raw),
+            "[multi_section] %s FIX-K verified-span render: sources=%d composed=%d draft_chars=%d",
+            section.title, len(section.ev_ids or []), len(_compose_ev_ids), len(raw),
         )
         _draft_directly_tokened = True  # I-beatboth-009 (#1287): already [#ev:]-tokened; skip REDUCE filter
     elif (
diff --git a/src/polaris_graph/retrieval/contradiction_detector.py b/src/polaris_graph/retrieval/contradiction_detector.py
index 93cd46c0..5367d861 100644
--- a/src/polaris_graph/retrieval/contradiction_detector.py
+++ b/src/polaris_graph/retrieval/contradiction_detector.py
@@ -316,6 +316,13 @@ _BIBLIOGRAPHIC_ID_RE = re.compile(
     r"""
     \b10\.\d{4,9}/\S+                                  # DOI: 10.1038/s41586-024-07123
     | arxiv:\s*\d{4}\.\d{4,5}(?:v\d+)?                 # arXiv id: arXiv:2401.12345v2
+    # I-deepfix-001 FIX-#4 (drb_72): a BARE arXiv id with no "arXiv:" prefix
+    # (e.g. an inline "2507.07935") is still a citation artifact, never a metric
+    # value. YYMM.NNNNN shape, MONTH-VALIDATED (Codex preflight P2): 2-digit year +
+    # 2-digit month 01-12 + dot + 4-5 fraction digits (+ optional vN). The month gate
+    # rejects a real NNNN.NNNN(N) metric whose 3rd-4th digits are not a valid month
+    # (e.g. 1234.5678 -> "34" is not 01-12), so this screens arXiv ids only.
+    | \b\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?\b     # bare arXiv id: 2507.07935 (YYMM)
     | \bissn:?\s*\d{4}-\d{3}[\dxX]\b                   # ISSN: ISSN 0028-0836
     # I-wire-013 (#1327) iter-2 (Codex P2-2): the page-range dash class is written with EXPLICIT
     # codepoint escapes so it can never render ambiguously (e.g. `[\-?--?]`) under a non-UTF-8 read.
@@ -390,6 +397,22 @@ def _find_value_generic(
         # never becomes a fabricated possible_metric_mismatch. Unit-bearing values are unaffected.
         if not unit and _in_bibliographic_region(m.start(), biblio_regions):
             continue
+        # I-deepfix-001 FIX-#4 (drb_72): a UNIT-LESS value whose leading '-' is the
+        # hyphen of a "N-N" token — a law/statute number ("P.L. 87-415" -> "-415"),
+        # a page/volume range ("412-419" -> "-419"), a dash-joined index/citation
+        # ("GEZANI-5" -> "-5") — is an IDENTIFIER / RANGE fragment, never a measured
+        # metric value. The generic '-?\d+' rule otherwise lifts the tail and
+        # fabricates a contradiction against a real number. Reject it so it never
+        # becomes a claim. Unit-bearing numbers (a real "-14.9%") are unaffected, and
+        # a standalone negative (the '-' not glued to a preceding digit) is still
+        # extracted.
+        if (
+            not unit
+            and raw.startswith("-")
+            and m.start() > 0
+            and text[m.start() - 1].isdigit()
+        ):
+            continue
         candidates.append((value, unit, window, m.start()))
     if not candidates:
         return None
@@ -1713,6 +1736,99 @@ def _group_incommensurable_reason(group: list["ExtractedNumericClaim"]) -> str:
     return ""
 
 
+# ─────────────────────────────────────────────────────────────────────────────
+# I-deepfix-001 FIX-#4 (drb_72) — NON-COMPARABLE-NUMBER scale gate.
+#
+# The generic extractor lifts ANY number from prose, so a UNIT-LESS bucket can
+# pair numbers that do NOT measure the same quantity: a 0–1 probability/score
+# against a raw sample size (3,682), or an identifier fragment (arXiv id, law
+# number, author index) against a real value. The legacy comparison then stamped
+# a REAL complementarity study as "CONTRADICTED" purely because 3682 != 1 and
+# printed junk magnitudes (368100% / 3473.5%) in the report — the §-1.1-lethal
+# "mislabel a real finding" pattern. This guard marks such a unit-less bucket
+# not_comparable (nulled magnitude, kept OUT of the headline count, every source
+# still DISCLOSED — §-1.3). It complements the A17 physical-kind guard (which
+# fires only on positively-divergent physical quantity kinds) and SHARES its
+# enable flag, so the PG_CONTRADICTION_COMMENSURABILITY_GUARD escape hatch
+# disables the whole comparability family coherently. Faithfulness is IMPROVED
+# (stops fabricating false contradictions); no faithfulness threshold is changed,
+# and a genuine same-metric contradiction (same unit, sub-1000% gap) is untouched.
+# ─────────────────────────────────────────────────────────────────────────────
+
+# A 0–1 ratio/probability paired with a value at/above this magnitude is an
+# incompatible-scale pairing (a fraction vs a raw count), not a contradiction.
+PG_CONTRADICTION_RAW_COUNT_FLOOR = float(
+    os.getenv("PG_CONTRADICTION_RAW_COUNT_FLOOR", "100")
+)
+# A unit-less relative difference at/above this ratio (default 10.0 = 1000%) is an
+# obviously-spurious magnitude from a scale/identifier mismatch, not a real
+# disagreement — a genuine same-metric gap is well under 1000%.
+PG_CONTRADICTION_SPURIOUS_REL = float(
+    os.getenv("PG_CONTRADICTION_SPURIOUS_REL", "10.0")
+)
+
+
+def _group_scale_not_comparable(
+    group: list["ExtractedNumericClaim"], rel: float,
+) -> str:
+    """Return a reason string iff a UNIT-LESS group's numbers are not genuinely
+    comparable, else "". Relabeling ALWAYS requires POSITIVE incomparability evidence
+    — at least one operand at/above PG_CONTRADICTION_RAW_COUNT_FLOOR (default 100). A
+    genuine unit-less metric (hazard ratio, odds ratio, risk ratio, probability, or a
+    composite/index score) is essentially always well under 100, so a value that large
+    in a unit-less bucket is a raw count / sample size / year / identifier lifted as a
+    value. Given that out-of-metric-range operand, two patterns are not_comparable:
+
+      * incompatible scales — it is paired with a 0–1 ratio/probability (a fraction vs
+        a raw count; e.g. a 0–1 metric collapsed with 3,682).
+      * spurious magnitude — the relative difference is >= PG_CONTRADICTION_SPURIOUS_REL
+        (default 1000%), confirming a scale/identifier mismatch.
+
+    Conservative by design: with NO out-of-metric-range operand the group is left as a
+    REAL contradiction even at a >1000% spread (a hazard ratio 0.5 vs 8.0 is a genuine
+    same-metric disagreement and is NEVER suppressed) — unit-less alone is NOT evidence
+    of incomparability (Codex I-deepfix-001 preflight P1, iter 1). Pure, never raises.
+    The caller restricts this to unit-less groups (a shared-unit bucket is commensurable
+    by construction, so its numbers are never re-judged)."""
+    vals: list[float] = []
+    for c in group:
+        try:
+            vals.append(float(getattr(c, "value", 0.0)))
+        except (TypeError, ValueError):
+            return ""
+    if len(vals) < 2:
+        return ""
+    has_ratio = any(0.0 < abs(v) <= 1.0 for v in vals)
+    has_count = any(abs(v) >= PG_CONTRADICTION_RAW_COUNT_FLOOR for v in vals)
+    # POSITIVE incomparability evidence is REQUIRED before relabeling: at least one
+    # operand at/above PG_CONTRADICTION_RAW_COUNT_FLOOR. A real unit-less metric (hazard
+    # ratio, odds ratio, risk ratio, probability, composite/index score) is essentially
+    # always well under that floor, so an operand >= it is a raw count / sample size /
+    # year / identifier lifted as a value. WITHOUT such an operand, the group is a REAL
+    # same-metric contradiction even at a >1000% spread (a hazard ratio 0.5 vs 8.0, rel
+    # = 1500%) and is NEVER suppressed here — unit-less alone is NOT incomparability
+    # (Codex I-deepfix-001 preflight P1, iter 1).
+    if not has_count:
+        return ""
+    if has_ratio:
+        return (
+            "incompatible scales in one bucket: a 0–1 ratio/probability paired with "
+            f"a raw count (>= {PG_CONTRADICTION_RAW_COUNT_FLOOR:g}) — the numbers do "
+            "not measure the same quantity (a unit token was missing, so they "
+            "collapsed under one surface key); the numeric gap is not a real "
+            "disagreement"
+        )
+    if rel >= PG_CONTRADICTION_SPURIOUS_REL:
+        return (
+            f"out-of-metric-range operand with a spurious magnitude: a unit-less value "
+            f">= {PG_CONTRADICTION_RAW_COUNT_FLOOR:g} (a raw count / sample size / year "
+            f"/ identifier lifted as a value) paired across a {rel * 100:.1f}% gap (>= "
+            f"{PG_CONTRADICTION_SPURIOUS_REL * 100:.0f}%) — not a real same-metric "
+            "disagreement"
+        )
+    return ""
+
+
 def detect_contradictions(
     claims: list[ExtractedNumericClaim],
     *,
@@ -1811,6 +1927,39 @@ def detect_contradictions(
                     incommensurable_reason=incommensurable_reason,
                 ))
                 continue
+            # I-deepfix-001 FIX-#4 (drb_72): NON-COMPARABLE-NUMBER scale gate. When the A17
+            # physical-kind guard found no divergent physical quantity, still reject a unit-less
+            # bucket whose numbers are not genuinely comparable — an incompatible scale (a 0–1
+            # ratio/probability vs a raw count/identifier) or an obviously-spurious magnitude
+            # (>1000%) produced by an arXiv id / law number / author index / sample size lifted as a
+            # value. The run stamped a REAL complementarity study CONTRADICTED purely because
+            # 3682 != 1 and printed junk magnitudes (368100% / 3473.5%). Relabel not_comparable,
+            # null the magnitude, keep it OUT of the headline count, DISCLOSE every source (§-1.3).
+            # Shares the A17 enable flag; unit-less only (a shared-unit bucket is commensurable by
+            # construction, so a genuine same-unit contradiction is never re-judged here).
+            scale_reason = ""
+            if _a17_guard_enabled() and unit == "":
+                scale_reason = _group_scale_not_comparable(group, rel)
+            if scale_reason:
+                records.append(ContradictionRecord(
+                    subject=subject,
+                    predicate=f"{predicate_display} [not_comparable]",
+                    claims=sorted(group, key=lambda c: c.value),
+                    relative_difference=0.0,
+                    absolute_difference=0.0,
+                    severity="low",
+                    recommended_action=(
+                        "Not comparable (scale guard, FIX-#4): the numbers in this bucket are on "
+                        "incompatible scales (a 0–1 ratio/probability vs a raw count) or produced "
+                        "an obviously-spurious magnitude, so they do not measure the same quantity "
+                        "— typically an arXiv id, law/statute number, author index, page/volume "
+                        "number, or sample size lifted as a value. Disclose each value with its own "
+                        "context; do NOT assert a numeric contradiction across them."
+                    ),
+                    not_comparable=True,
+                    incommensurable_reason=scale_reason,
+                ))
+                continue
             # A17 SAME-SOURCE guard (iarch007 FETCH-P0): a CROSS-source contradiction requires the
             # disagreeing numbers to come from DIFFERENT sources. When every claim in this group
             # shares ONE source (same source_url, or same evidence_id when a URL is absent — and the
diff --git a/src/polaris_graph/roles/openrouter_role_transport.py b/src/polaris_graph/roles/openrouter_role_transport.py
index e18c7c08..786299a6 100644
--- a/src/polaris_graph/roles/openrouter_role_transport.py
+++ b/src/polaris_graph/roles/openrouter_role_transport.py
@@ -1185,7 +1185,7 @@ def _build_openrouter_body(request: RoleRequest, model_slug: str, normalized_mes
     NOT exclusive with effort and MUST exceed the reasoning budget. Under `effort=xhigh` the
     provider spends ~95% of top-level `max_tokens` on reasoning, so a popped/absent `max_tokens`
     starves the verdict. I-meta-008 FULL-POWER therefore SETS a generous top-level `max_tokens`
-    (PG_VERIFIER_REASONING_MAX_TOKENS, default 16384) for the reasoning verifiers and an explicit
+    (PG_D8_VERDICT_MAX_TOKENS, default 16384) for the reasoning Judge's verdict and an explicit
     small classifier budget (PG_SENTINEL_MAX_TOKENS, default 256) for the non-reasoning Sentinel.
     Source: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
     """
@@ -1225,7 +1225,7 @@ def _build_openrouter_body(request: RoleRequest, model_slug: str, normalized_mes
         # bare verdict, AND the certification used reasoning + max_tokens>=3000. So the decomposition
         # Sentinel gets its OWN generous budget (default 16384, hard-floored at 3000 so an env
         # override can never re-introduce the run-12 truncation that collapses every claim to a
-        # fail-closed UNGROUNDED). Other reasoning verifiers keep PG_VERIFIER_REASONING_MAX_TOKENS.
+        # fail-closed UNGROUNDED). The reasoning Judge gets a verdict-sized PG_D8_VERDICT_MAX_TOKENS (FIX #2).
         if request.role == "sentinel":
             # I-arch-003 (#1253, operator "max max"): MAX output without hard-erroring. Under
             # allow_fallbacks:False the binding cap is the MIN max_completion_tokens across the
@@ -1272,19 +1272,33 @@ def _build_openrouter_body(request: RoleRequest, model_slug: str, normalized_mes
                 _MIRROR_MAX_TOKENS_CHAIN_MIN,
             )
         else:
-            # I-arch-003 (#1253, operator "max max"): the reasoning Judge (Qwen3.6-35B-A3B) verdict
-            # is a short enum/JSON, so a generous output cap can only HELP (more reasoning room, never
-            # starves — max_tokens is billed by usage, not pre-allocated). Raised 16384 -> 262140, the
-            # MIN max_completion_tokens across the Judge chain (live OpenRouter read 2026-06-14:
-            # wandb=262144, io-net=262140; atlas-cloud=65536 DROPPED from the chain in the routing yaml
-            # because its 65536 cap is incompatible with the max-output directive and would 400 here).
-            # Qwen lists `effort` so it is reasoning-bounded by the model, not by an explicit numeric
-            # cap; the total budget simply guarantees the verdict never truncates.
-            # I-arch-003 hardening: clamp to the Judge chain min so an env override can never 400.
-            body["max_tokens"] = min(
-                int(os.getenv("PG_VERIFIER_REASONING_MAX_TOKENS", "262140")),
-                _JUDGE_MAX_TOKENS_CHAIN_MIN,
-            )
+            # I-deepfix-001 (#1344, drb_72 forensic FIX #2): the reasoning Judge (Qwen3.6-35B-A3B)
+            # adjudicates ONE claim with reasoning effort=xhigh and returns a SHORT structured verdict.
+            # The prior I-arch-003 "max max" raise to 262140 MIS-APPLIED the §9.1.8 "max_tokens ALWAYS
+            # MAX" rule (which governs the GENERATOR, not a tiny verdict): reserving ~262k per call blew
+            # the OpenRouter TPM budget (193x HTTP-429) AND, summed with even a small prompt, exceeded the
+            # ~262144 Qwen context window (67x HTTP-400 "requested > context") so the D8 seam timed out.
+            # FIX: restore I-meta-008's generous-but-BOUNDED Judge budget (16384). This RESPECTS §9.1.8
+            # "never starve": effort=xhigh allocates ~95% of max_tokens to reasoning, so the total must
+            # stay strictly above that allocation or the bare verdict truncates to empty (the I-meta-008
+            # starvation failure — "popping it starved the verdict to empty"); 16384 leaves ample room
+            # for xhigh reasoning AND the verdict. It ALSO kills the blowup: ~16x fewer reserved tokens
+            # than 262140, and well under the 262144 window so the HTTP-400 can never fire. (Codex
+            # I-deepfix-001 preflight iter-1 flagged the FIX-4 over-suppression; this iter-2 raise of the
+            # Judge default 4000 -> 16384 additionally removes the starvation risk a 4000 cap carried
+            # under xhigh.) Scoped to THIS verdict-judge call only — the generator keeps its MAX budget
+            # (and is not served by this transport: role_endpoint('generator') raises). FAITHFULNESS-
+            # NEUTRAL: identical model + reasoning + verdict parsing; only the reserved output ceiling
+            # shrinks from the over-raised 262140 back to the proven 16384. LAW VI: env-overridable +
+            # parse-guarded; a non-positive override falls back to the default; still clamped to the
+            # Judge chain min as a 400-proof backstop.
+            try:
+                verdict_budget = int(os.getenv("PG_D8_VERDICT_MAX_TOKENS", "16384"))
+            except (TypeError, ValueError):
+                verdict_budget = 16384
+            if verdict_budget <= 0:
+                verdict_budget = 16384
+            body["max_tokens"] = min(verdict_budget, _JUDGE_MAX_TOKENS_CHAIN_MIN)
     else:
         # Sentinel (reasoning-disabled classifier): give it explicit output room rather than relying
         # on an unknown provider default (no pop-and-hope). I-arch-003 (#1253, operator "max max"):
diff --git a/tests/polaris_graph/test_deepfix_contradiction_unitless_p1.py b/tests/polaris_graph/test_deepfix_contradiction_unitless_p1.py
new file mode 100644
index 00000000..a00e98e2
--- /dev/null
+++ b/tests/polaris_graph/test_deepfix_contradiction_unitless_p1.py
@@ -0,0 +1,73 @@
+"""I-deepfix-001 (#1344) — Codex preflight iter-1 P1 regression.
+
+The contradiction scale-guard (FIX #4) must NOT suppress a genuine UNIT-LESS SAME-METRIC
+contradiction (hazard ratio / odds ratio / risk ratio / index) merely because the spread
+exceeds 1000%. Relabeling `not_comparable` now REQUIRES positive count-scale evidence — at
+least one operand at/above PG_CONTRADICTION_RAW_COUNT_FLOOR (a raw count / sample size /
+identifier lifted as a value). Unit-less alone is NOT incomparability. Suppressing a real
+contradiction is the §-1.1-lethal "mislabel a real finding" class, so this is locked by a test.
+"""
+from __future__ import annotations
+
+from src.polaris_graph.retrieval.contradiction_detector import (
+    ExtractedNumericClaim,
+    detect_contradictions,
+)
+
+
+def _hr(ev_id: str, value: float, url: str) -> ExtractedNumericClaim:
+    """A unit-less hazard-ratio claim — the bucket the iter-1 P1 over-suppressed."""
+    return ExtractedNumericClaim(
+        evidence_id=ev_id,
+        subject="drug_x",
+        predicate="hazard ratio for all-cause mortality",
+        value=value,
+        unit="",  # hazard ratio carries no unit token
+        context_snippet=f"hazard ratio {value}",
+        source_url=url,
+    )
+
+
+def test_unitless_same_metric_high_spread_still_flagged():
+    # Hazard ratio 0.5 (protective) vs 8.0 (harmful): rel = 1500% (>1000% spurious threshold),
+    # NEITHER operand >= 100 (no count-scale evidence). A REAL clinical contradiction that MUST
+    # survive — the iter-1 P1 was the spurious-magnitude arm suppressing exactly this.
+    claims = [
+        _hr("ev_a", 0.5, "https://example.com/trial_a"),
+        _hr("ev_b", 8.0, "https://example.com/cohort_b"),
+    ]
+    records = detect_contradictions(
+        claims, rel_threshold=0.5, abs_threshold=1.0, is_clinical=True
+    )
+    assert len(records) == 1, "a unit-less same-metric >1000% contradiction must still be detected"
+    r = records[0]
+    assert r.not_comparable is False, "must NOT be relabeled not_comparable (no count-scale operand)"
+    assert "[not_comparable]" not in r.predicate
+    assert r.relative_difference > 10.0  # the real ~1500% spread is preserved, not nulled to 0.0
+
+
+def test_unitless_ratio_vs_raw_count_is_not_comparable():
+    # The drb_72 forensic case: a 0-1 ratio (0.62) bucketed with a raw count / sample size (3682)
+    # under a missing unit. has_ratio AND has_count -> genuine scale mismatch -> not_comparable
+    # (magnitude nulled, kept out of the headline count, both sources still disclosed — §-1.3).
+    claims = [
+        ExtractedNumericClaim(
+            evidence_id="ev_ratio", subject="study", predicate="complementarity index",
+            value=0.62, unit="", context_snippet="index 0.62",
+            source_url="https://example.com/s1",
+        ),
+        ExtractedNumericClaim(
+            evidence_id="ev_count", subject="study", predicate="complementarity index",
+            value=3682.0, unit="", context_snippet="n = 3682",
+            source_url="https://example.com/s2",
+        ),
+    ]
+    records = detect_contradictions(
+        claims, rel_threshold=0.5, abs_threshold=1.0, is_clinical=True
+    )
+    assert len(records) == 1
+    r = records[0]
+    assert r.not_comparable is True, "0-1 ratio vs raw count 3682 is a genuine scale mismatch"
+    assert "[not_comparable]" in r.predicate
+    assert r.relative_difference == 0.0 and r.absolute_difference == 0.0  # junk magnitude nulled
+    assert {c.evidence_id for c in r.claims} == {"ev_ratio", "ev_count"}  # both still disclosed
diff --git a/tests/roles/test_openrouter_role_transport_meta007.py b/tests/roles/test_openrouter_role_transport_meta007.py
index 4811143e..20abbe63 100644
--- a/tests/roles/test_openrouter_role_transport_meta007.py
+++ b/tests/roles/test_openrouter_role_transport_meta007.py
@@ -700,24 +700,25 @@ def test_reasoning_role_sets_generous_max_tokens(role, slug):
         assert seen["body"]["reasoning"] == {"max_tokens": 100000}
         assert seen["body"]["max_tokens"] == 131072
     else:
-        # I-arch-003 (#1253): Judge total 16384 -> 262140 (min of wandb 262144 / io-net 262140 chain).
-        # A2-CLAMP (RC2): the shared finalize_body() chokepoint now ALSO fires on the role path,
-        # reconciling the 262140 budget DOWN against the real 262144 serving window so the prompt
-        # has room (this is the qwen-judge HTTP-400 fix). With a tiny "decide" prompt (~4 tokens)
-        # and the default 2048 safety margin: 262144 - 4 - 2048 = 260092. The KEY invariant is
-        # that the budget is now STRICTLY below the 262144 window (it was == 262140 before, leaving
-        # only 4 tokens for the prompt -> 400 on every real prompt).
-        assert seen["body"]["max_tokens"] == 260092, (
-            f"{role}: budget must be clamped below the 262144 serving window (A2-CLAMP)"
+        # I-deepfix-001 (#1344, drb_72 FIX #2): the Judge verdict budget is PG_D8_VERDICT_MAX_TOKENS
+        # (default 16384 — I-meta-008's generous-but-bounded value). The I-arch-003 "max max" raise to
+        # 262140 over-reserved per call and blew the OpenRouter TPM/context ceiling (193x HTTP-429 + 67x
+        # HTTP-400 "requested > context") timing out the D8 seam; 16384 leaves ample room for
+        # effort=xhigh reasoning AND the bare verdict (never starves -> §9.1.8) while reserving ~16x
+        # fewer tokens and staying well under the 262144 window (so A2-CLAMP never needs to fire and the
+        # 400 can't recur).
+        assert seen["body"]["max_tokens"] == 16384, (
+            f"{role}: verdict budget must be the bounded PG_D8_VERDICT_MAX_TOKENS default (16384)"
         )
-        assert seen["body"]["max_tokens"] < 262144  # RC2: room left for the prompt
-        # the Judge still requests MAX effort.
+        assert seen["body"]["max_tokens"] < 262144  # well under the serving window; no 400
+        # the Judge still requests MAX reasoning effort.
         assert seen["body"]["reasoning"] == {"enabled": True, "effort": "xhigh"}
 
 
 def test_reasoning_role_max_tokens_env_overridable(monkeypatch):
-    # LAW VI: the verifier reasoning budget is env-overridable.
-    monkeypatch.setenv("PG_VERIFIER_REASONING_MAX_TOKENS", "8192")
+    # LAW VI: the Judge verdict budget is env-overridable. I-deepfix-001 FIX #2 renamed the knob from
+    # PG_VERIFIER_REASONING_MAX_TOKENS to PG_D8_VERDICT_MAX_TOKENS (8192 < chain-min, so no clamp).
+    monkeypatch.setenv("PG_D8_VERDICT_MAX_TOKENS", "8192")
     handler, seen = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
     _make_transport(handler).complete(
         RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide", params={"max_tokens": 16})
@@ -728,17 +729,18 @@ def test_reasoning_role_max_tokens_env_overridable(monkeypatch):
 def test_env_override_clamped_to_provider_chain_min(monkeypatch):
     """I-arch-003 (#1253) Codex gate P2 hardening: a too-LARGE env override must clamp DOWN to the
     role's chain-min ceiling so it can never reintroduce a provider-cap 400 ("requested N > max M")."""
-    # Judge: bad override 999_999 -> _build_openrouter_body clamps to the chain min 262140,
-    # THEN the A2-CLAMP finalize_body() chokepoint clamps again DOWN against the 262144 serving
-    # window so the prompt fits: 262144 - 4 ("decide") - 2048 margin = 260092 (RC2 HTTP-400 fix).
-    monkeypatch.setenv("PG_VERIFIER_REASONING_MAX_TOKENS", "999999")
+    # Judge: bad override 999_999 (via PG_D8_VERDICT_MAX_TOKENS, the FIX #2 knob) -> _build_openrouter_body
+    # clamps to the chain min 262140, THEN the A2-CLAMP finalize_body() chokepoint clamps again DOWN
+    # against the 262144 serving window so the prompt fits: 262144 - 4 ("decide") - 2048 margin = 260092
+    # (RC2 HTTP-400 fix). The 400-proof chain-min backstop survives the verdict-budget rename.
+    monkeypatch.setenv("PG_D8_VERDICT_MAX_TOKENS", "999999")
     handler, seen = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
     _make_transport(handler).complete(
         RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide", params={"max_tokens": 16})
     )
     assert seen["body"]["max_tokens"] == 260092
     assert seen["body"]["max_tokens"] < 262144  # RC2: never == the window
-    monkeypatch.delenv("PG_VERIFIER_REASONING_MAX_TOKENS", raising=False)
+    monkeypatch.delenv("PG_D8_VERDICT_MAX_TOKENS", raising=False)
 
     # Mirror: bad total override 999_999 -> clamp to 131072; reasoning cap stays < total.
     monkeypatch.setenv("PG_MIRROR_MAX_TOKENS", "999999")
```
