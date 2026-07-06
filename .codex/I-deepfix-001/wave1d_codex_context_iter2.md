HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Wave-1d re-gate (iter 2) — fail-loud shallow-report canaries, YOUR two P1/P2 fixes applied

You reviewed this diff in iter 1 and returned REQUEST_CHANGES with:
- **P1**: "OFF is not byte-identical: `_sweep_records` unconditionally emits `shallow_report_canary:null` when PG_SHALLOW_REPORT_CANARY is off."
- **P2**: "Flag-on missing/unreadable run_log is reported as `ok` rather than skip/no-data."

Both fixes are now applied. Your job this iter: CONFIRM the two fixes are correct AND that the fix introduced NO new problem (no reformat/scope-creep, OFF still byte-identical for every other key, faithfulness still untouched, structural-not-quantity still holds). This is a Claude-authored diff you are reviewing (Plan §7.A LOCKED A2).

## What this change is
Two POST-RUN DETECTORS in `scripts/dr_benchmark/run_gate_b.py` that FAIL LOUD (set the sweep exit code to 1) when a released report is structurally shallow despite the winner slate being ON:
- `assert_depth_synthesis_fired`: depth cross-source pass DRAFTED >=1 eligible high-corroboration basket YET kept ZERO synthesized findings (eligible-yet-zero).
- `assert_multi_origin_baskets_exist`: finding_dedup grouped >=1 cluster with >=2 DISTINCT origins YET zero baskets reached composition with verified_support_origin_count>=2.
Both are STRUCTURAL (eligible-yet-zero), never a word/citation/source COUNT threshold (§-1.3 bans counts as quality signals). Behind default-OFF `PG_SHALLOW_REPORT_CANARY`; OFF must be byte-identical to the pre-Wave-1d baseline. The launcher (`scripts/run_honest_sweep_r3.py`) emits ONE flag-gated `[shallow-canary]` telemetry line that canary 2 parses; canary 1 parses the EXISTING `[depth-synthesis] D8-thread:` line.

## How the two fixes were applied (verify against the diff below)
**FIX 1 (P1 — OFF byte-identical sweep record).** The pre-existing sweep-record append (`_sweep_records.append({...})`, which already carried `m6_cross_source_canary` and `ok` from an earlier wave — see the 3 deletions) was restructured to: build a base `_record = {...}` dict that does NOT contain `shallow_report_canary`, then add the key ONLY under `if _shallow_canary is not None:` (flag ON => the wrapper always returns a string => the guard is exactly the flag boundary). `_shallow_canary` defaults to `None`. The pre-existing `"ok"` field gained ` and _shallow_canary != "FAILED"`, which is None-safe when OFF (`None != "FAILED"` is `True`), so its value is unchanged OFF. The pre-existing `m6_cross_source_canary` key emission is left UNCHANGED (it is NOT a Wave-1d key).

**FIX 2 (P2 — no-data must not report ok).** In the flag-ON block, `_sc_log_text` defaults to `None` (sentinel for missing/unreadable). Missing run_dir, missing file, and read exception all leave/set it `None`. `if _sc_log_text is None:` sets `_shallow_canary = "skip:no-run-log"` directly instead of calling the wrapper with `""` (which would have returned `"ok"` and false-greened the fail-loud detector). The stale comment was corrected.

**FIX 3 (Fable minor doc, P2).** A NOTE comment before canary 1's loop documents that if the producer ever emits per-section D8-thread lines, a single dark section could fire — intended eligible-yet-zero semantics. Comment only.

## Diff hygiene note
The working-tree file had an editor whitespace/line-ending reformat artifact (raw diff showed 273 deletions). It was mechanically cleaned (rstrip-aligned to HEAD bytes on unchanged lines). The diff below is the RESULT: `git diff` now shows 184 insertions / 3 deletions, and `git diff -w` (whitespace-ignored) shows the SAME 184/3 — i.e. ZERO whitespace-only churn remains. Please confirm the diff you see below is purely additive + the 3 real deletions of the old inline append (no reformatted existing blocks).

## THE CLEAN DIFF (git diff, both files)

```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index d242a744..9a0146d8 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -49,6 +49,7 @@ import src._polaris_native_thread_safety  # noqa: F401,E402  # import-time side
 import json
 import logging
 import os
+import re
 from dataclasses import dataclass
 from pathlib import Path
 from typing import Any, Callable, Mapping
@@ -2559,6 +2560,136 @@ def _run_m6_firing_canary(
         print(f"<<< {domain} / {slug}: M6 cross-source firing canary FAILED: {_m6_exc}")
         return "FAILED"
     print(f"<<< {domain} / {slug}: M6 cross-source firing canary=ok")
+    return "ok"
+
+
+# ── I-deepfix-001 (#1344) Wave-1d — FAIL-LOUD SHALLOW-REPORT CANARIES ─────────────────────────────────
+# Two DETECTORS that guard against the "false-fired pipeline": the winner slate is ON, the writer-path
+# logs are busy, yet the rendered report is still shallow/degraded. Each asserts a STRUCTURAL
+# contradiction (an ELIGIBLE-YET-ZERO condition), NEVER a word/citation/source COUNT threshold (§-1.3:
+# such counts are BANNED as quality signals). Both self-skip unless the opt-in PG_SHALLOW_REPORT_CANARY
+# flag is truthy (default OFF => byte-identical, the canary never runs). Faithfulness-neutral: they READ
+# post-run telemetry lines and raise for investigation; they touch NO verdict, threshold, judge, or gate.
+#
+# Producer marker lines (stable literals) the two canaries parse:
+#   * canary 1 reads the EXISTING depth-synthesis D8-thread line (run_honest_sweep_r3.py:16074):
+#       "[depth-synthesis] D8-thread: baskets_total=.. drafted=.. kept_findings=.. (cross=.. single=..)"
+#   * canary 2 reads the Wave-1d flag-gated telemetry line (run_honest_sweep_r3.py, post-U5):
+#       "[shallow-canary] finding_dedup_multiorigin_clusters=.. multi_origin_baskets=.."
+_SHALLOW_REPORT_CANARY_ENV = "PG_SHALLOW_REPORT_CANARY"
+_DEPTH_D8_THREAD_RE = re.compile(
+    r"\[depth-synthesis\] D8-thread:.*?\bdrafted=(\d+).*?\bkept_findings=(\d+)"
+)
+_SHALLOW_MULTIORIGIN_RE = re.compile(
+    r"\[shallow-canary\] finding_dedup_multiorigin_clusters=(\d+) multi_origin_baskets=(\d+)"
+)
+
+
+def _shallow_report_canary_enabled() -> bool:
+    """PG_SHALLOW_REPORT_CANARY opt-in kill-switch (default OFF). Read at CALL time (LAW VI). OFF =>
+    both asserts early-return AND the post-run wrapper is never invoked => byte-identical to pre-Wave-1d
+    (the canary never runs). The producer-side telemetry line is gated by the SAME flag, so OFF also
+    writes NO run_log.txt line."""
+    return os.getenv(_SHALLOW_REPORT_CANARY_ENV, "0").strip().lower() in ("1", "true", "yes", "on")
+
+
+def assert_depth_synthesis_fired(log_text: str) -> None:
+    """Wave-1d shallow canary #1 (post-run, pure string logic — no spend, no network).
+
+    STRUCTURAL contradiction: the grounded DEPTH cross-source synthesis pass DRAFTED >=1 ELIGIBLE
+    high-corroboration basket (the pre-pass only drafts baskets clearing the DEFINITIONAL
+    ``>=2 distinct-origin members`` floor) YET the run kept ZERO synthesized findings
+    (``kept_findings==0``). That is the "0 analytical units when eligible pairs exist" failed
+    validation — the depth layer is a SILENT NO-OP (flag-on but dark). Raise RuntimeError.
+
+    NEVER a count target: a run that drafted 0 eligible baskets (``drafted==0`` — a single-source /
+    low-corroboration corpus) NEVER raises (§-1.3, depth is never FORCED); a run that kept >=1 finding
+    (``kept_findings>=1``, of ANY magnitude) NEVER raises. Only the zero-when-eligible contradiction
+    decides — no magnitude threshold. Reads the EXISTING depth-synthesis D8-thread telemetry line and
+    asserts nothing about any verdict (the frozen faithfulness engine is untouched). Self-skips when
+    PG_SHALLOW_REPORT_CANARY is off."""
+    if not _shallow_report_canary_enabled():
+        return
+    # NOTE (Fable review): the producer today emits ONE run-level D8-thread line per query. If it ever
+    # emits PER-SECTION D8-thread lines, a single dark section (drafted>=1, kept_findings==0) could fire
+    # even when another section kept findings — that is still the intended eligible-yet-zero semantics
+    # (a per-line structural contradiction), documented here for future producer changes.
+    for _m in _DEPTH_D8_THREAD_RE.finditer(log_text or ""):
+        drafted = int(_m.group(1))
+        kept_findings = int(_m.group(2))
+        if drafted >= 1 and kept_findings == 0:
+            raise RuntimeError(
+                "shallow-report canary FAILED [DEPTH-SYNTHESIS DARK]: the depth cross-source synthesis "
+                "pass DRAFTED >=1 eligible high-corroboration basket (>=2 distinct-origin members) yet "
+                "the run kept ZERO synthesized findings (kept_findings==0) — 0 analytical units while "
+                "eligible baskets existed. Investigate depth_synthesis.synthesize_cross_source_findings "
+                "/ the per-sentence re-ground; do NOT ship a report whose depth layer produced nothing "
+                "while eligible baskets existed."
+            )
+
+
+def assert_multi_origin_baskets_exist(log_text: str) -> None:
+    """Wave-1d shallow canary #2 (post-run, pure string logic — no spend, no network).
+
+    STRUCTURAL contradiction: finding_dedup grouped >=1 cluster carrying >=2 DISTINCT origins
+    (``corroboration_count>=2`` — the SAME distinct-origin basis as the basket denominator, so a
+    same-host near-dup pair is never miscounted) YET ZERO consolidation baskets reached composition
+    with ``verified_support_origin_count>=2``. That is the finding_dedup->basket keystone silently NOT
+    producing multi-origin baskets — the documented "787 rows -> mostly-singleton baskets, Multi-source
+    corroborated: 0" regression (credibility_pass.py:51-56). Raise RuntimeError.
+
+    NEVER a count target: a run whose finding_dedup produced 0 multi-origin clusters (a single-source /
+    non-overlapping corpus) NEVER raises (§-1.3, corroboration is never FORCED); a run that produced
+    >=1 multi-origin basket (of ANY magnitude) NEVER raises. Absent the flag-gated telemetry line (the
+    Wave-1d flag was off during the run, or finding_dedup did not run) the canary has no data and NEVER
+    raises. Reads only telemetry; touches no verdict. Self-skips when PG_SHALLOW_REPORT_CANARY is off."""
+    if not _shallow_report_canary_enabled():
+        return
+    for _m in _SHALLOW_MULTIORIGIN_RE.finditer(log_text or ""):
+        multiorigin_clusters = int(_m.group(1))
+        multi_origin_baskets = int(_m.group(2))
+        if multiorigin_clusters >= 1 and multi_origin_baskets == 0:
+            raise RuntimeError(
+                "shallow-report canary FAILED [MULTI-ORIGIN BASKETS DARK]: finding_dedup grouped >=1 "
+                "cluster with >=2 distinct origins yet ZERO consolidation baskets reached composition "
+                "with verified_support_origin_count>=2 — the finding_dedup->basket keystone silently "
+                "produced no multi-origin baskets. Investigate credibility_pass basket assembly / the "
+                "PG_BASKET_CONSUME_FINDING_DEDUP keystone; do NOT ship a report whose multi-origin "
+                "corroboration collapsed while finding_dedup found corroborating origins."
+            )
+
+
+def _run_shallow_report_canary(
+    log_text: str,
+    status: str,
+    *,
+    smoke_scale: bool,
+    domain: str,
+    slug: str,
+) -> str:
+    """POST-RUN shallow-report canary wrapper (Wave-1d). Mirrors ``_run_m6_firing_canary``: on a
+    RELEASED, non-smoke run, run BOTH structural detectors over the run_log text. A GENUINE
+    eligible-yet-zero contradiction raises RuntimeError -> "FAILED" (caller sets overall_rc=1). Both
+    asserts self-skip when PG_SHALLOW_REPORT_CANARY is off (wrapper returns "skip:disabled" first).
+    Reuses the breadth/M6 released-status universe so it applies exactly where a full-contract report
+    was rendered. Faithfulness-neutral: reads run telemetry, asserts nothing about any verdict.
+    Returns a one-line sweep-record status."""
+    if not _shallow_report_canary_enabled():
+        return "skip:disabled"
+    if status not in _BREADTH_CANARY_RELEASED_STATUSES:
+        return f"skip:status={status or '<none>'}"
+    if smoke_scale:
+        return "skip:smoke_scale"
+    try:
+        assert_depth_synthesis_fired(log_text)
+        assert_multi_origin_baskets_exist(log_text)
+    except RuntimeError as _sc_exc:
+        logging.getLogger("run_gate_b").error(
+            "shallow-report canary FAILED for %s/%s: %s", domain, slug, _sc_exc,
+        )
+        print(f"<<< {domain} / {slug}: shallow-report canary FAILED: {_sc_exc}")
+        return "FAILED"
+    print(f"<<< {domain} / {slug}: shallow-report canary=ok")
     return "ok"
 
 
@@ -5178,16 +5309,66 @@ def main(argv: list[str] | None = None) -> int:
                 )
                 if _m6_canary == "FAILED":
                     overall_rc = 1
-            _sweep_records.append({
+            # I-deepfix-001 (#1344) Wave-1d: POST-RUN SHALLOW-REPORT canaries — mirror the M6 wrapper.
+            # Default-OFF flag PG_SHALLOW_REPORT_CANARY => the block is skipped (canary never runs,
+            # byte-identical). When ON, read this query's run_log.txt (the `_log` tee sink carrying the
+            # depth D8-thread + [shallow-canary] telemetry lines) and FAIL CLOSED on a genuine
+            # eligible-yet-zero contradiction (depth dark OR multi-origin baskets dark). Faithfulness-
+            # neutral (reads telemetry only). If the run_log is MISSING or UNREADABLE there is no
+            # telemetry to assert over; a fail-loud detector must NOT false-green on no-data, so that
+            # case records an explicit "skip:no-run-log" instead of asserting over an empty string.
+            _shallow_canary = None
+            if _shallow_report_canary_enabled():
+                _sc_log_text = None  # None => run_log missing/unreadable (distinct from a read empty log)
+                try:
+                    _sc_run_dir = summary.get("run_dir")
+                    if _sc_run_dir:
+                        _sc_log_path = Path(str(_sc_run_dir)) / "run_log.txt"
+                        if _sc_log_path.exists():
+                            _sc_log_text = _sc_log_path.read_text(
+                                encoding="utf-8", errors="replace",
+                            )
+                except Exception as _sc_read_exc:  # noqa: BLE001 — telemetry read; never abort sweep
+                    logging.getLogger("run_gate_b").warning(
+                        "shallow-report canary: run_log read failed for %s/%s: %s",
+                        domain, slug, _sc_read_exc,
+                    )
+                    _sc_log_text = None
+                if _sc_log_text is None:
+                    # No run_log => no data to assert over. Do NOT call the wrapper with "" (it would
+                    # return "ok" and false-green the fail-loud detector) — record an explicit skip.
+                    _shallow_canary = "skip:no-run-log"
+                else:
+                    _shallow_canary = _run_shallow_report_canary(
+                        _sc_log_text, status,
+                        smoke_scale=args.smoke_scale, domain=domain, slug=slug,
+                    )
+                    if _shallow_canary == "FAILED":
+                        overall_rc = 1
+            # OFF-purity (Codex+Fable P1): the shallow-report canary is a NEW Wave-1d record key. When the
+            # flag is OFF, _shallow_canary is None — adding "shallow_report_canary": null would give a
+            # flag-OFF sweep_summary.json a key the pre-Wave-1d baseline lacks (OFF not byte-identical). So
+            # the key is added ONLY when the wrapper actually ran (flag ON => always a string). The
+            # None-safe "ok" conjunct below is byte-identical when OFF (None != "FAILED" is True). The
+            # pre-existing "m6_cross_source_canary" key emission is left UNCHANGED (not a Wave-1d key).
+            _record = {
                 "query_index": query_index,
                 "slug": slug,
                 "domain": domain,
                 "status": status,
-                "ok": _status_ok and _breadth_canary != "FAILED" and _m6_canary != "FAILED",
+                "ok": (
+                    _status_ok
+                    and _breadth_canary != "FAILED"
+                    and _m6_canary != "FAILED"
+                    and _shallow_canary != "FAILED"
+                ),
                 "breadth_enrichment_canary": _breadth_canary,
                 "m6_cross_source_canary": _m6_canary,
                 "cost_usd": summary.get("cost_usd"),
-            })
+            }
+            if _shallow_canary is not None:
+                _record["shallow_report_canary"] = _shallow_canary
+            _sweep_records.append(_record)
         except Exception as exc:  # noqa: BLE001 — isolate ONE query; never abort the sweep silently
             tb = traceback.format_exc()
             overall_rc = 1
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 8ef1412f..065ef7b1 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -19234,6 +19234,39 @@ async def run_one_query(
                     multi_cited_sentence_count=_u5_multicited,
                 )
 
+        # I-deepfix-001 (#1344) Wave-1d SHALLOW-REPORT CANARY telemetry (detector-only, default-OFF).
+        # Opt-in flag PG_SHALLOW_REPORT_CANARY (LAW VI). OFF => this block is skipped => NO run_log.txt
+        # line is written => BYTE-IDENTICAL (the canary never runs). When ON, emit ONE STRUCTURAL
+        # telemetry line the post-run `assert_multi_origin_baskets_exist` canary parses: the count of
+        # finding_dedup clusters that grouped >=2 DISTINCT origins (corroboration_count>=2 — the SAME
+        # distinct-origin basis as the basket denominator, so a same-host near-dup pair never counts) and
+        # the count of consolidation baskets that reached composition carrying
+        # verified_support_origin_count>=2. The canary FAILS LOUD only on the STRUCTURAL contradiction
+        # (>=1 multi-origin cluster yet 0 multi-origin basket = the finding_dedup->basket keystone
+        # silently not producing multi-origin baskets); it is NEVER a count target. Pure READ of
+        # already-computed telemetry (`_finding_dedup_telemetry` is None-safe per the :9676 init;
+        # `count_multi_source_baskets` handles a None credibility_analysis) — the frozen faithfulness
+        # engine is untouched. Fail-open: never abort the report.
+        if _env_flag("PG_SHALLOW_REPORT_CANARY", default=False):
+            try:
+                _sc_clusters = (
+                    _finding_dedup_telemetry.get("clusters", [])
+                    if isinstance(_finding_dedup_telemetry, dict) else []
+                )
+                _sc_multiorigin_clusters = sum(
+                    1 for _c in _sc_clusters
+                    if int((_c or {}).get("corroboration_count", 0) or 0) >= 2
+                )
+                _sc_multi_origin_baskets = count_multi_source_baskets(
+                    getattr(multi, "credibility_analysis", None)
+                )
+                _log(
+                    "[shallow-canary] finding_dedup_multiorigin_clusters="
+                    f"{_sc_multiorigin_clusters} multi_origin_baskets={_sc_multi_origin_baskets}"
+                )
+            except Exception as _sc_exc:  # noqa: BLE001 — detector telemetry; never abort the report
+                _log(f"[shallow-canary] telemetry skipped (fail-open): {_sc_exc}")
+
         # I-ready-006 (#1082): surface the complexity-routing decision on the SUCCESS manifest ONLY when
         # the router is ON (Codex brief P2-2 — byte-identical OFF: no field appears when
         # PG_COMPLEXITY_ROUTING is unset). Auditable: complexity, confidence, reasons, whether it was
```

## THE FULL NEW TEST FILE (tests/polaris_graph/test_shallow_report_canary_wave1d.py) — 39 tests, all passing

```python
"""I-deepfix-001 (#1344) Wave-1d — fail-loud SHALLOW-REPORT canaries (offline, no model / GPU / spend).

Two DETECTORS in ``scripts/dr_benchmark/run_gate_b.py`` guard against the "false-fired pipeline"
(winner slate ON, writer-path logs busy, yet the rendered report is still shallow/degraded):

  * ``assert_depth_synthesis_fired`` — the depth cross-source pass DRAFTED >=1 eligible
    high-corroboration basket yet kept ZERO synthesized findings (eligible-yet-zero).
  * ``assert_multi_origin_baskets_exist`` — finding_dedup grouped >=1 cluster with >=2 distinct
    origins yet ZERO baskets reached composition with verified_support_origin_count>=2 (the
    keystone silently not producing multi-origin baskets).

Both are STRUCTURAL detectors (an eligible-yet-zero contradiction), NEVER a word / citation / source
COUNT threshold (§-1.3). Both self-skip unless the opt-in ``PG_SHALLOW_REPORT_CANARY`` flag is on
(default OFF => byte-identical, canary never runs). The telemetry is stubbed as log strings — no
pipeline run, no model, no network. The frozen faithfulness engine is untouched (canaries only READ).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.dr_benchmark.run_gate_b as rg

_FLAG = "PG_SHALLOW_REPORT_CANARY"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCHER = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
_GATE_B = _REPO_ROOT / "scripts" / "dr_benchmark" / "run_gate_b.py"

# ── stub telemetry lines (exactly the runtime shape of the real producers) ───────────────────────
_DEPTH_LINE = "[depth-synthesis] D8-thread: baskets_total={bt} drafted={d} kept_findings={k} (cross={c} single={s})"
_SHALLOW_LINE = "[shallow-canary] finding_dedup_multiorigin_clusters={x} multi_origin_baskets={y}"


def _depth(drafted: int, kept: int, *, baskets_total: int = 9, cross: int = 0) -> str:
    return _DEPTH_LINE.format(bt=baskets_total, d=drafted, k=kept, c=cross, s=max(0, kept - cross))


def _shallow(clusters: int, baskets: int) -> str:
    return _SHALLOW_LINE.format(x=clusters, y=baskets)


def _noise() -> str:
    return "some unrelated log line\n[retrieval] fetched 12 rows\n[multi_section] verified-compose PRIMARY: 4 baskets"


# ── OFF => byte-identical: the canary NEVER runs (no raise even on a would-fire log) ──────────────

def test_off_asserts_are_noop_on_would_fire_logs(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)  # default OFF
    assert not rg._shallow_report_canary_enabled()
    # both logs WOULD fire if the flag were on — with it off, both asserts return None (no raise).
    rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=0))
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=4, baskets=0))


def test_off_wrapper_returns_skip_disabled(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    out = rg._run_shallow_report_canary(
        _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0),
        "success", smoke_scale=False, domain="d", slug="s",
    )
    assert out == "skip:disabled"


def test_off_explicit_zero_is_off(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    assert not rg._shallow_report_canary_enabled()
    rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=0))  # no raise


# ── canary 1: depth-synthesis eligible-yet-zero ──────────────────────────────────────────────────

def test_canary1_fires_on_eligible_yet_zero(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    with pytest.raises(RuntimeError, match="DEPTH-SYNTHESIS DARK"):
        rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=0))


def test_canary1_silent_when_it_fired(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=2))  # kept>=1 => fired, no raise


def test_canary1_silent_when_no_eligible_baskets(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # drafted==0 (no eligible high-corroboration baskets) — conditional absence, never FORCED (§-1.3).
    rg.assert_depth_synthesis_fired(_depth(drafted=0, kept=0, baskets_total=40))


def test_canary1_silent_when_no_depth_line(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_depth_synthesis_fired(_noise())  # no D8-thread line => no data => no raise


def test_canary1_large_counts_alone_do_not_fire(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # huge magnitudes, but kept>=1 => genuinely fired. Magnitude alone decides nothing (structural).
    rg.assert_depth_synthesis_fired(_depth(drafted=100, kept=50))


# ── canary 2: finding_dedup multi-origin clusters yet zero multi-origin baskets ───────────────────

def test_canary2_fires_on_multiorigin_clusters_yet_zero_baskets(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    with pytest.raises(RuntimeError, match="MULTI-ORIGIN BASKETS DARK"):
        rg.assert_multi_origin_baskets_exist(_shallow(clusters=4, baskets=0))


def test_canary2_silent_when_baskets_exist(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=4, baskets=3))  # baskets>=1 => no raise


def test_canary2_silent_when_no_multiorigin_clusters(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # 0 multi-origin clusters (single-source / non-overlapping corpus) — never FORCED (§-1.3).
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=0, baskets=0))


def test_canary2_silent_when_no_telemetry_line(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_multi_origin_baskets_exist(_noise())  # no [shallow-canary] line => no data => no raise


def test_canary2_large_clusters_with_baskets_do_not_fire(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=999, baskets=1))  # baskets>=1 => no raise


# ── STRUCTURAL-NOT-QUANTITY: only the eligible-yet-zero contradiction decides, never a magnitude ──

@pytest.mark.parametrize("drafted,kept,should_fire", [
    (0, 0, False),    # no eligible: conditional absence
    (1, 0, True),     # minimal eligible, zero kept: FIRE
    (3, 0, True),
    (100, 0, True),   # large eligible, still zero kept: FIRE (magnitude irrelevant)
    (3, 1, False),    # one kept: fired
    (100, 50, False), # large kept: fired
    (0, 5, False),    # kept without drafted (never happens, but: not eligible-yet-zero)
])
def test_canary1_decision_is_purely_structural(monkeypatch, drafted, kept, should_fire):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=drafted, kept=kept)
    if should_fire:
        with pytest.raises(RuntimeError):
            rg.assert_depth_synthesis_fired(log)
    else:
        rg.assert_depth_synthesis_fired(log)  # no raise


@pytest.mark.parametrize("clusters,baskets,should_fire", [
    (0, 0, False),    # no multi-origin clusters: conditional absence
    (1, 0, True),     # minimal cluster, zero baskets: FIRE
    (4, 0, True),
    (999, 0, True),   # large clusters, still zero baskets: FIRE (magnitude irrelevant)
    (4, 1, False),    # one basket: keystone fired
    (999, 500, False),
    (0, 5, False),    # baskets without clusters: not clusters-yet-zero
])
def test_canary2_decision_is_purely_structural(monkeypatch, clusters, baskets, should_fire):
    monkeypatch.setenv(_FLAG, "1")
    log = _shallow(clusters=clusters, baskets=baskets)
    if should_fire:
        with pytest.raises(RuntimeError):
            rg.assert_multi_origin_baskets_exist(log)
    else:
        rg.assert_multi_origin_baskets_exist(log)  # no raise


# ── the post-run wrapper (mirrors _run_m6_firing_canary) ─────────────────────────────────────────

def test_wrapper_fails_on_firing_log(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=False, domain="d", slug="s")
    assert out == "FAILED"


def test_wrapper_fails_when_only_multiorigin_dark(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # depth healthy, but multi-origin keystone dark — the wrapper runs BOTH asserts, so it still FAILS.
    log = _depth(drafted=3, kept=2) + "\n" + _shallow(clusters=4, baskets=0)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=False, domain="d", slug="s")
    assert out == "FAILED"


def test_wrapper_ok_on_healthy_log(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=2) + "\n" + _shallow(clusters=4, baskets=3)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=False, domain="d", slug="s")
    assert out == "ok"


def test_wrapper_ok_on_released_with_disclosed_gaps(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=0, kept=0) + "\n" + _shallow(clusters=0, baskets=0)  # conditional-absence run
    out = rg._run_shallow_report_canary(
        log, "released_with_disclosed_gaps", smoke_scale=False, domain="d", slug="s",
    )
    assert out == "ok"


def test_wrapper_skip_on_non_released_status(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0)  # would FAIL if released
    out = rg._run_shallow_report_canary(
        log, "abort_scope_rejected", smoke_scale=False, domain="d", slug="s",
    )
    assert out.startswith("skip:status=")


def test_wrapper_skip_on_smoke_scale(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=True, domain="d", slug="s")
    assert out == "skip:smoke_scale"


def test_wrapper_released_status_universe_is_reused():
    # the wrapper reuses the breadth/M6 released-status set — success is released, an abort is not.
    assert "success" in rg._BREADTH_CANARY_RELEASED_STATUSES
    assert "released_with_disclosed_gaps" in rg._BREADTH_CANARY_RELEASED_STATUSES
    assert "abort_scope_rejected" not in rg._BREADTH_CANARY_RELEASED_STATUSES


# ── the canaries parse REAL producer lines (guards against producer/canary drift) ─────────────────

def test_producer_lines_exist_in_launcher_source():
    src = _LAUNCHER.read_text(encoding="utf-8")
    # canary 1 reads the EXISTING depth-synthesis D8-thread producer line.
    assert "[depth-synthesis] D8-thread:" in src
    assert "drafted=" in src
    assert "kept_findings=" in src
    # canary 2 reads the Wave-1d flag-gated telemetry producer line.
    assert "[shallow-canary] finding_dedup_multiorigin_clusters=" in src
    assert "multi_origin_baskets=" in src
    # the regexes actually match the runtime shape of those producer lines.
    assert rg._DEPTH_D8_THREAD_RE.search(_depth(drafted=3, kept=0)) is not None
    assert rg._SHALLOW_MULTIORIGIN_RE.search(_shallow(clusters=4, baskets=0)) is not None


def test_producer_emission_is_flag_gated_off_byte_identical():
    # the run_honest_sweep_r3 telemetry emission is gated by the canary flag => OFF writes NO line.
    src = _LAUNCHER.read_text(encoding="utf-8")
    idx = src.index("[shallow-canary] finding_dedup_multiorigin_clusters=")
    guard = 'if _env_flag("PG_SHALLOW_REPORT_CANARY", default=False):'
    gidx = src.rindex(guard, 0, idx)
    # the emission is within a few dozen lines of its flag guard (same gated block).
    assert 0 < (idx - gidx) < 2000, "the [shallow-canary] emission is not under the PG_SHALLOW_REPORT_CANARY guard"


# ── OFF-purity: the sweep record must NOT carry the new key when the flag is off (byte-identical) ─

def test_sweep_record_key_is_guarded_off_byte_identical():
    """FIX 1 (Codex+Fable P1): the base ``_record`` dict must NOT contain the Wave-1d
    ``shallow_report_canary`` key; it is added ONLY inside an ``if _shallow_canary is not None:`` guard,
    so a flag-OFF run's sweep_summary.json is byte-identical to the pre-Wave-1d baseline."""
    src = _GATE_B.read_text(encoding="utf-8")
    # the key is added via an explicit guarded assignment, not as a base-dict literal entry.
    assert 'if _shallow_canary is not None:' in src
    assert '_record["shallow_report_canary"] = _shallow_canary' in src
    # the base _record literal (from "_record = {" to the "if _shallow_canary is not None:" guard) has
    # NO shallow_report_canary key — that is the OFF-byte-identical property.
    start = src.index("_record = {")
    guard = src.index("if _shallow_canary is not None:", start)
    base_literal = src[start:guard]
    assert '"shallow_report_canary"' not in base_literal, "the OFF path would emit a null key"
    # the pre-existing m6 key is left as an unconditional base-dict entry (unchanged, not a Wave-1d key).
    assert '"m6_cross_source_canary": _m6_canary,' in base_literal


def test_no_data_path_records_skip_not_ok():
    """FIX 2 (Codex+Fable P2): when the run_log is missing/unreadable the code must NOT call the wrapper
    with "" (which returns "ok") — it records an explicit ``skip:no-run-log`` so the fail-loud detector
    never false-greens on no data."""
    src = _GATE_B.read_text(encoding="utf-8")
    assert '_shallow_canary = "skip:no-run-log"' in src
    # the no-data branch is keyed on the None sentinel (missing run_dir / missing file / read exception).
    assert 'if _sc_log_text is None:' in src


# ── smoke: the module + symbols import offline ───────────────────────────────────────────────────

def test_smoke_symbols_present():
    for name in (
        "_shallow_report_canary_enabled",
        "assert_depth_synthesis_fired",
        "assert_multi_origin_baskets_exist",
        "_run_shallow_report_canary",
        "_SHALLOW_REPORT_CANARY_ENV",
        "_DEPTH_D8_THREAD_RE",
        "_SHALLOW_MULTIORIGIN_RE",
    ):
        assert hasattr(rg, name), f"run_gate_b is missing {name}"
    assert rg._SHALLOW_REPORT_CANARY_ENV == _FLAG
```

## Verify (cite the diff line or test name)
1. **P1 FIXED — OFF byte-identical.** With PG_SHALLOW_REPORT_CANARY OFF: `_shallow_canary` stays `None`, the `if _shallow_canary is not None:` guard is False, so `_record` has NO `shallow_report_canary` key → the persisted `sweep_summary.json` is byte-identical to the pre-Wave-1d baseline. Confirm the key is NOT in the base `_record` literal and IS added only under the guard. Confirm the `"ok"` value is unchanged OFF (None-safe conjunct). Confirm NO other record key changed.
2. **P2 FIXED — no-data → skip not ok.** Flag ON + missing/unreadable run_log → `_shallow_canary = "skip:no-run-log"` (not a wrapper call on `""`). Confirm all three no-data paths (missing run_dir, missing file, read exception) reach the None sentinel and the skip branch.
3. **NO NEW REGRESSION from the fix.** The restructure `append({...})` → `_record = {...}; ...; append(_record)` must preserve every pre-existing key and value byte-for-byte OFF. Confirm the 3 deletions are ONLY the old inline-append open / old `"ok"` line / old close, and nothing else in the block changed semantics.
4. **STRUCTURAL-NOT-QUANTITY still holds.** canary 1 fires ONLY on `drafted>=1 AND kept_findings==0`; canary 2 ONLY on `multiorigin_clusters>=1 AND multi_origin_baskets==0`. No magnitude/count target anywhere. The parametrized tests prove magnitude-irrelevance.
5. **FAITHFULNESS untouched.** Both detectors only READ run_log telemetry via regex; the launcher telemetry line is a fail-open pure read of already-computed `_finding_dedup_telemetry` + `count_multi_source_baskets`. No manifest/status/gate/judge/threshold changed. The ONLY behavior change on a FIRED canary is `overall_rc = 1` (intended fail-loud sweep exit code, not a pipeline verdict). Confirm.
6. **canary 2 distinct-origin basis.** Numerator counts clusters with `corroboration_count >= 2` (independent registrable-domains); denominator = baskets with `verified_support_origin_count >= 2`. Same basis both sides so a same-host near-dup pair cannot spuriously fire. Confirm.
7. **Slate purity.** PG_SHALLOW_REPORT_CANARY is NOT added to any slate / force-list (activation is Wave 3, not 1d). Default-OFF at both call sites. Confirm.
8. **The 2 new tests actually lock the fixes.** `test_sweep_record_key_is_guarded_off_byte_identical` (P1) and `test_no_data_path_records_skip_not_ok` (P2) — confirm they would FAIL if the fix were reverted.
9. LAW VI (flags env-read at call time), snake_case, no `unittest.mock` in src.

## Output — return EXACTLY this schema (loose prose is rejected)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
structural_not_quantity: true|false
off_byte_identical: true|false
faithfulness_untouched: true|false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
notes: <short>
```
APPROVE iff zero novel P0 AND zero continuing P0 AND zero P1.
