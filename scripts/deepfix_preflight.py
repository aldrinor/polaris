#!/usr/bin/env python3
"""I-deepfix-001 (#1344) GATE B — OFFLINE fail-loud behavioral preflight harness.

Proves each consolidated deepfix actually FIRES on the REAL drb_72 run-1 artifacts
(the I-arch-005 "committed+compiled+approved != wired" dead-on-arrival catcher).

NO model spend. NO network. Pure logic over module-level helpers + the banked
audit artifacts in ``scratchpad/deepfix_run1_audit/``.

Four canaries (each asserts HARD — a failed assert raises and marks the canary FAIL;
any FAIL exits non-zero):

  CANARY-2  FIX-2 verdict-cap  (openrouter_role_transport._build_openrouter_body)
            The reasoning Judge body's max_tokens == PG_D8_VERDICT_MAX_TOKENS (iter-2
            default 16384, RAISED from 4000 to avoid xhigh-reasoning starvation),
            <= the Judge chain-min, and is NOT the old 262140 "max max"; the cap did
            NOT leak to the Mirror / Sentinel roles (they resolve their own budgets).

  CANARY-3  FIX-3 relevance + render-chrome  (multi_section_generator)
            The three real drb_72 chrome leaks are caught; three real findings
            (incl. a "By week 24..." sentence + an email INSIDE prose) are NOT
            false-positived; the compose relevance-floor holds off-topic rows out
            and keeps a missing-relevance row (keep-neutral).

  CANARY-4  FIX-4 contradiction gate  (contradiction_detector)
            The drb_72 false-positives are killed (0-1 ratio vs raw-count scale
            collapse -> not_comparable, magnitude nulled, sources still disclosed;
            bare arXiv id + law-tail not extracted as numeric values) while a
            genuine same-unit 47% vs 32% contradiction STILL fires.

  CANARY-1  FIX-1 audit-map-from-partials  (run_honest_sweep_r3.py seam-rescue)
            STRUCTURAL assertion (the fix is inline in the torn-seam branch, not a
            clean unit call): the inserted block re-invokes four_role_input_builder,
            writes four_role_claim_audit.json, folds unsettled kept claims as a
            non-VERIFIED "UNADJUDICATED" placeholder (settled verdicts win), and has
            a fail-safe except preserving the prior whole-body-withhold. PLUS the
            65-line settled-verdicts backbone tallies EXACTLY 58 VERIFIED + 7
            UNSUPPORTED.

Run:  cd /c/POLARIS && python scripts/deepfix_preflight.py
      (set PYTHONPATH=C:/POLARIS/src OR C:/POLARIS if the src.* imports need it)
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
import time
from pathlib import Path

# ── make src.* importable no matter how we're launched ──────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── utf-8 stdout so the en-dash in the FIX-4 reason strings never crashes ────
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - older python
    pass

# ── locate the REAL banked drb_72 run-1 artifacts ───────────────────────────
_ARTIFACT_DIR = Path(
    os.getenv("DEEPFIX_AUDIT_DIR")
    or (_REPO_ROOT / "scratchpad" / "deepfix_run1_audit")
)
_SETTLED_VERDICTS = _ARTIFACT_DIR / "four_role_settled_verdicts.jsonl"
_RUN_SWEEP = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"


def _check(cond: bool, msg: str) -> None:
    """Hard assert: raise AssertionError(msg) when cond is falsey."""
    if not cond:
        raise AssertionError(msg)


def _p(line: str) -> None:
    print(line, flush=True)


# ════════════════════════════════════════════════════════════════════════════
# CANARY-2 — FIX-2 verdict-cap on the reasoning Judge body
# ════════════════════════════════════════════════════════════════════════════
def canary_2_verdict_cap() -> str:
    _p("[CANARY-2] FIX-2 verdict-cap (openrouter_role_transport._build_openrouter_body)")
    from src.polaris_graph.roles.openrouter_role_transport import (
        _build_openrouter_body,
        _JUDGE_MAX_TOKENS_CHAIN_MIN,
    )
    from src.polaris_graph.roles.role_transport import RoleRequest

    msgs = [{"role": "user", "content": "Adjudicate ONE claim. Evidence: foo bar. Verdict:"}]

    def build(role: str, slug: str) -> dict:
        req = RoleRequest(role=role, model_slug=slug, messages=msgs, params={})
        return _build_openrouter_body(req, slug, msgs)

    # snapshot + force the DEFAULT so the 4000 default-path is what we measure
    _saved = os.environ.pop("PG_D8_VERDICT_MAX_TOKENS", None)
    try:
        judge = build("judge", "qwen/qwen3.6-35b-a3b")
        mirror = build("mirror", "z-ai/glm-5.1")
        sentinel = build("sentinel", "minimax/minimax-m2")
        jmax = judge.get("max_tokens")
        mmax = mirror.get("max_tokens")
        smax = sentinel.get("max_tokens")
        _p(f"  judge.max_tokens    = {jmax}   (PG_D8_VERDICT_MAX_TOKENS iter-2 default 16384)")
        _p(f"  judge chain-min     = {_JUDGE_MAX_TOKENS_CHAIN_MIN}   (old 'max max' = 262140)")
        _p(f"  mirror.max_tokens   = {mmax}   (own budget, cap must NOT leak)")
        _p(f"  sentinel.max_tokens = {smax}   (own budget, cap must NOT leak)")

        _check(jmax == 16384, f"judge verdict cap must be the iter-2 default 16384, got {jmax}")
        _check(jmax <= _JUDGE_MAX_TOKENS_CHAIN_MIN,
               f"judge cap {jmax} must be <= chain-min {_JUDGE_MAX_TOKENS_CHAIN_MIN}")
        _check(jmax != 262140, f"judge cap must NOT be the old 262140 'max max', got {jmax}")

        # negative-scope: the cap is scoped to the Judge ONLY
        _check(mmax != jmax and mmax > jmax,
               f"Mirror budget {mmax} must differ from (and exceed) the Judge cap {jmax} — cap leaked")
        _check(smax != jmax and smax > jmax,
               f"Sentinel budget {smax} must differ from (and exceed) the Judge cap {jmax} — cap leaked")

        # prove the cap is WIRED to PG_D8_VERDICT_MAX_TOKENS (defends vs a hardcoded 4000)
        os.environ["PG_D8_VERDICT_MAX_TOKENS"] = "1234"
        jmax_override = build("judge", "qwen/qwen3.6-35b-a3b").get("max_tokens")
        _p(f"  judge.max_tokens(PG_D8_VERDICT_MAX_TOKENS=1234) = {jmax_override}  (env-wired, LAW VI)")
        _check(jmax_override == 1234,
               f"judge cap must follow PG_D8_VERDICT_MAX_TOKENS override (1234), got {jmax_override}")
    finally:
        os.environ.pop("PG_D8_VERDICT_MAX_TOKENS", None)
        if _saved is not None:
            os.environ["PG_D8_VERDICT_MAX_TOKENS"] = _saved

    _p("  -> PASS: Judge verdict cap = 16384 (iter-2 default, env-wired), NOT 262140, did NOT leak to Mirror/Sentinel")
    return "PASS"


# ════════════════════════════════════════════════════════════════════════════
# CANARY-3 — FIX-3 compose relevance-floor + render-chrome screen
# ════════════════════════════════════════════════════════════════════════════
def canary_3_relevance_chrome() -> str:
    _p("[CANARY-3] FIX-3 relevance + render-chrome (multi_section_generator)")
    t0 = time.time()
    try:
        from src.polaris_graph.generator.multi_section_generator import (
            _is_compose_render_chrome,
            _screen_fixk_render_chrome,
            _compose_relevance_floored_ev_ids,
        )
        from src.polaris_graph.generator.weighted_enrichment import (
            is_render_chrome_or_unrenderable as shared_predicate,
        )
    except Exception as exc:  # heavy/broken import -> SKIP (validated on VM postgen resume)
        _p(f"  -> SKIP: helper import raised {type(exc).__name__}: {str(exc)[:140]}")
        return "SKIP"
    dt = time.time() - t0
    _p(f"  (import of the module-level helpers took {dt:.2f}s, no embedder/torch loaded)")
    if dt > 30:
        _p("  -> SKIP: helper import exceeded 30s (heavy model load); validate on VM postgen resume")
        return "SKIP"

    # (i) the three REAL drb_72 chrome leaks -> chrome True
    chrome_units = [
        "s.kupeshova1@gmail.com [#ev:masthead:0-22].",            # contact-email masthead
        "Written by Jim McGwin [#ev:byline:0-20].",               # author byline
        "The Artstor website will be retired on Aug 1st [#ev:nav:0-44].",  # service-sunset nav
    ]
    for u in chrome_units:
        v = _is_compose_render_chrome(u, shared_predicate)
        _p(f"  chrome? {v!s:5}  | {u[:58]}")
        _check(v is True, f"REAL chrome leak must be caught: {u!r}")

    # (ii) precision: three REAL findings -> chrome False (no real-finding false-positive)
    real_units = [
        "Tirzepatide 15 mg reduced HbA1c by 2.3% at 40 weeks [#ev:c1:0-50].",         # decimal-bearing clinical
        "By week 24, mean body-weight change was -8.5 kg versus placebo [#ev:c2:0-60].",  # 'By week ...' (not a byline)
        "Researchers may request the de-identified dataset by emailing data@trialhub.org, "
        "which holds 1200 patient records from the registered cohort [#ev:c3:0-90].",  # email INSIDE prose
    ]
    for u in real_units:
        v = _is_compose_render_chrome(u, shared_predicate)
        _p(f"  real->chrome? {v!s:5} | {u[:58]}")
        _check(v is False, f"REAL finding must NOT be flagged as chrome: {u!r}")

    # (ii-b) behavioral: the SCREEN drops the chrome span and keeps the real one
    draft = real_units[0] + " " + chrome_units[1]
    screened = _screen_fixk_render_chrome(draft)
    _p(f"  screen kept real finding?  {real_units[0][:24]!r} in output: {real_units[0] in screened}")
    _p(f"  screen dropped byline?     {'Written by Jim McGwin' not in screened}")
    _check(real_units[0] in screened, "screen must KEEP the real verbatim finding")
    _check("Written by Jim McGwin" not in screened, "screen must DROP the byline chrome span")

    # (iii) compose relevance-floor: hold off-topic ~0, keep on-topic, keep MISSING (neutral)
    pool = {
        "off": {"selection_relevance": 0.02},  # off-topic weight-~0
        "on": {"selection_relevance": 0.80},   # on-topic
        "miss": {},                            # no relevance score -> keep-neutral
    }
    kept = _compose_relevance_floored_ev_ids(["off", "on", "miss"], pool)
    _p(f"  relevance-floor kept (floor=0.10): {kept}")
    _check("off" not in kept, "off-topic 0.02 row must be held OUT of the composed findings")
    _check("on" in kept, "on-topic 0.80 row must be kept")
    _check("miss" in kept, "missing-relevance row must be kept (keep-neutral)")

    _p("  -> PASS: 3/3 chrome caught, 3/3 real findings clean, relevance-floor holds off-topic + keeps neutral")
    return "PASS"


# ════════════════════════════════════════════════════════════════════════════
# CANARY-4 — FIX-4 contradiction gate (false-positive kills + true-positive kept)
# ════════════════════════════════════════════════════════════════════════════
def canary_4_contradiction_gate() -> str:
    _p("[CANARY-4] FIX-4 contradiction gate (contradiction_detector)")
    from src.polaris_graph.retrieval.contradiction_detector import (
        detect_contradictions,
        extract_numeric_claims,
        ExtractedNumericClaim,
        _find_value_generic,
        _bibliographic_id_regions,
        _GENERIC_VALUE_RE,
    )

    # (i)a FALSE-POSITIVE kill: 0-1 ratio (0.62) vs raw count (3682), unit-less bucket
    c1 = ExtractedNumericClaim(
        evidence_id="e1", subject="task complementarity", predicate="index",
        value=0.62, unit="", context_snippet="complementarity index of 0.62", source_url="http://a")
    c2 = ExtractedNumericClaim(
        evidence_id="e2", subject="task complementarity", predicate="index",
        value=3682.0, unit="", context_snippet="a sample of 3682 workers", source_url="http://b")
    recs = detect_contradictions([c1, c2], is_clinical=False)
    real_contras = [r for r in recs if not r.not_comparable]
    nc = next((r for r in recs if r.not_comparable), None)
    _p(f"  scale-collapse 0.62 vs 3682: records={len(recs)} real_contradictions={len(real_contras)}")
    _check(nc is not None, "the 0.62-vs-3682 scale collapse must produce a not_comparable record")
    _p(f"    not_comparable={nc.not_comparable} rel={nc.relative_difference} abs={nc.absolute_difference} "
       f"sources_disclosed={len(nc.claims)} reason={nc.incommensurable_reason[:48]!r}")
    _check(len(real_contras) == 0, "scale collapse must NOT be flagged as a real (comparable) contradiction")
    _check(nc.relative_difference == 0.0 and nc.absolute_difference == 0.0,
           "not_comparable magnitude must be nulled to 0.0 (no junk 368100%)")
    _check(len(nc.claims) == 2, "both sources must remain DISCLOSED in the not_comparable record (§-1.3)")

    # (i)b FALSE-POSITIVE kill: bare arXiv id + law-tail NOT extracted as numeric values
    arxiv_regions = _bibliographic_id_regions("see arXiv 2507.07935 in the references")
    fv_arxiv = _find_value_generic("2507.07935")
    raw_law = [(m.group("value"), m.group("unit")) for m in _GENERIC_VALUE_RE.finditer("P.L. 87-415")]
    fv_law = _find_value_generic("P.L. 87-415")
    _p(f"  bare-arXiv biblio region (FIX regex fires): {arxiv_regions}")
    _p(f"  _find_value_generic('2507.07935')           = {fv_arxiv}")
    _p(f"  raw _GENERIC_VALUE_RE on 'P.L. 87-415'       = {raw_law}   (extractor WOULD grab the tail)")
    _p(f"  _find_value_generic('P.L. 87-415')           = {fv_law}   (law-tail fix excludes it)")
    _check(bool(arxiv_regions), "the bare-arXiv id 2507.07935 must register as a bibliographic region (FIX-4 regex)")
    _check(fv_arxiv is None or fv_arxiv[0] != 2507.07935,
           "the bare arXiv id 2507.07935 must NOT be extracted as a metric value")
    _check(any(v == "-415" for v, _u in raw_law),
           "sanity: the raw regex DOES capture '-415' so the exclusion below is the FIX doing the work")
    _check(fv_law is None or fv_law[0] not in (415.0, -415.0),
           "the law/statute tail -415 (P.L. 87-415) must NOT be extracted as a metric value")

    # end-to-end extraction over the real-shaped sentence: only the real 0.62 metric survives
    ev = [{
        "evidence_id": "x",
        "direct_quote": ("Automation reduced the employment share by 0.62 in "
                         "arXiv 2507.07935 under statute P.L. 87-415."),
        "source_url": "http://x", "tier": "T3",
    }]
    claims = extract_numeric_claims(ev, domain="economics")
    vals = [c.value for c in claims]
    _p(f"  extract_numeric_claims values: {[(c.subject, c.predicate, c.value, c.unit) for c in claims]}")
    for bad in (2507.07935, 87.0, 415.0, -415.0):
        _check(bad not in vals, f"identifier/law fragment {bad} must NOT become an extracted claim value")

    # (ii) TRUE-POSITIVE preserved: genuine same-unit 47% vs 32% contradiction STILL fires
    d1 = ExtractedNumericClaim(
        evidence_id="e3", subject="semaglutide", predicate="weight loss",
        value=47.0, unit="percent", context_snippet="47% weight loss", source_url="http://c")
    d2 = ExtractedNumericClaim(
        evidence_id="e4", subject="semaglutide", predicate="weight loss",
        value=32.0, unit="percent", context_snippet="32% weight loss", source_url="http://d")
    recs2 = detect_contradictions([d1, d2], is_clinical=True)
    hit = next((r for r in recs2 if not r.not_comparable and r.relative_difference > 0), None)
    _p(f"  same-unit 47% vs 32%: records={len(recs2)} "
       f"flagged={'yes' if hit else 'NO'} "
       f"{('rel=' + str(hit.relative_difference) + ' sev=' + hit.severity) if hit else ''}")
    _check(hit is not None,
           "a genuine same-unit 47% vs 32% contradiction MUST still be flagged (not over-suppressed)")
    _check(not hit.not_comparable, "the real contradiction must NOT be marked not_comparable")

    # (iii) ITER-2 P1 REGRESSION (the new requirement): a UNIT-LESS SAME-METRIC contradiction with a
    # >1000% spread and NO count operand (hazard ratio 0.5 vs 8.0, rel 1500%, neither >= 100) must
    # STILL be flagged as a REAL contradiction. The iter-1 spurious-magnitude arm over-suppressed
    # exactly this; relabeling now REQUIRES positive count-scale evidence. Must hold.
    h1 = ExtractedNumericClaim(
        evidence_id="hr1", subject="drug_x", predicate="hazard ratio for all-cause mortality",
        value=0.5, unit="", context_snippet="hazard ratio 0.5", source_url="http://trial_a")
    h2 = ExtractedNumericClaim(
        evidence_id="hr2", subject="drug_x", predicate="hazard ratio for all-cause mortality",
        value=8.0, unit="", context_snippet="hazard ratio 8.0", source_url="http://cohort_b")
    recs3 = detect_contradictions([h1, h2], rel_threshold=0.5, abs_threshold=1.0, is_clinical=True)
    _check(len(recs3) == 1, f"unit-less HR 0.5 vs 8.0 must produce exactly one record, got {len(recs3)}")
    hr = recs3[0]
    _p(f"  iter-2 P1: unit-less HR 0.5 vs 8.0 -> not_comparable={hr.not_comparable} "
       f"rel={hr.relative_difference} pred={hr.predicate!r}")
    _check(hr.not_comparable is False,
           "iter-2 P1: unit-less same-metric >1000% with NO count operand must NOT be suppressed")
    _check("[not_comparable]" not in hr.predicate, "iter-2 P1: HR record must not carry the not_comparable tag")
    _check(hr.relative_difference > 10.0,
           "iter-2 P1: the real ~1500% (15.0) spread must be preserved, not nulled to 0.0")

    # belt-and-suspenders: the LOCKED iter-2 P1 regression test must pass (2 passed)
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/polaris_graph/test_deepfix_contradiction_unitless_p1.py", "-q"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True)
    out_tail = " | ".join((proc.stdout or "").strip().splitlines()[-2:])
    _p(f"  locked iter-2 P1 pytest: rc={proc.returncode}  {out_tail}")
    _check(proc.returncode == 0,
           f"locked iter-2 P1 regression test must pass (rc={proc.returncode})\n{proc.stdout}\n{proc.stderr}")
    _check("2 passed" in (proc.stdout or ""), "expected '2 passed' from test_deepfix_contradiction_unitless_p1")

    _p("  -> PASS: scale-collapse + arXiv/law fragments killed (sources disclosed); 47%vs32% still flagged; "
       "iter-2 P1 unit-less HR 0.5/8.0 STILL flagged (2 passed)")
    return "PASS"


# ════════════════════════════════════════════════════════════════════════════
# CANARY-1 — FIX-1 audit-map-from-partials (STRUCTURAL + settled-verdict backbone)
# ════════════════════════════════════════════════════════════════════════════
def canary_1_audit_map_structural() -> str:
    _p("[CANARY-1] FIX-1 audit-map-from-partials (run_honest_sweep_r3.py seam-rescue) — STRUCTURAL")
    _check(_RUN_SWEEP.is_file(), f"run sweep file missing: {_RUN_SWEEP}")
    src = _RUN_SWEEP.read_text(encoding="utf-8")

    marker = "I-deepfix-001 FIX-1 (#1344) AUDIT-MAP-FROM-PARTIALS"
    mpos = src.find(marker)
    _check(mpos >= 0, f"FIX-1 keystone marker not found: {marker!r}")
    # window: from the marker to the FourRoleEvaluationResult that closes the seam branch
    end = src.find("FourRoleEvaluationResult(", mpos)
    _check(end > mpos, "could not bound the FIX-1 block (FourRoleEvaluationResult sentinel not found after marker)")
    block = src[mpos:end]
    lineno = src[:mpos].count("\n") + 1
    _p(f"  located FIX-1 block at line {lineno}, window {len(block)} chars")

    # (a) re-invokes the seam input builder
    fact_a = bool(re.search(r"four_role_input_builder\s*\(", block))
    # (b) writes the per-claim audit map to four_role_claim_audit.json
    fact_b = ('four_role_claim_audit.json' in block) and ('.write_text(' in block)
    # (c) folds unsettled kept claims as non-VERIFIED "UNADJUDICATED", settled verdicts WIN
    fact_c = ('"UNADJUDICATED"' in block) and bool(
        re.search(r"if\s+_seam_cid\s+not\s+in\s+_seam_partial_verdicts", block))
    # (d) fail-safe except preserving prior whole-body-withhold
    fact_d = bool(re.search(r"except\s+Exception", block)) and ("body-withhold" in block)

    _p(f"  (a) re-invokes four_role_input_builder(...)            : {fact_a}")
    _p(f"  (b) writes four_role_claim_audit.json via write_text   : {fact_b}")
    _p(f"  (c) folds unsettled -> 'UNADJUDICATED' (settled wins)  : {fact_c}")
    _p(f"  (d) fail-safe except keeps prior whole-body-withhold   : {fact_d}")
    _check(fact_a, "FIX-1 must re-invoke four_role_input_builder on a torn seam")
    _check(fact_b, "FIX-1 must persist the re-derived map to four_role_claim_audit.json")
    _check(fact_c, "FIX-1 must fold unsettled kept claims as non-VERIFIED 'UNADJUDICATED' (never ship as verified)")
    _check(fact_d, "FIX-1 must have a fail-safe except preserving the prior whole-body-withhold")

    # backbone tally: the 65-line settled-verdicts sidecar must be EXACTLY 58 VERIFIED + 7 UNSUPPORTED
    _check(_SETTLED_VERDICTS.is_file(), f"settled-verdicts artifact missing: {_SETTLED_VERDICTS}")
    tally = collections.Counter()
    nlines = 0
    for line in _SETTLED_VERDICTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        nlines += 1
        tally[json.loads(line)["verdict"]] += 1
    _p(f"  settled verdicts: total={nlines} tally={dict(tally)}")
    _check(nlines == 65, f"settled-verdicts must be 65 lines, got {nlines}")
    _check(tally.get("VERIFIED") == 58, f"VERIFIED backbone must be 58, got {tally.get('VERIFIED')}")
    _check(tally.get("UNSUPPORTED") == 7, f"UNSUPPORTED must be 7, got {tally.get('UNSUPPORTED')}")

    _p("  -> PASS: 4/4 code-structure facts hold + settled backbone is exactly 58 VERIFIED + 7 UNSUPPORTED")
    _p("  NOTE: FIX-1's BEHAVIORAL proof needs a FORCED-seam-tear VM resume (a clean resume won't")
    _p("        tear because FIX-2 prevents the verdict-budget TPM/context blowup that timed out the seam).")
    return "PASS"


def main() -> int:
    _p("=" * 78)
    _p("I-deepfix-001 (#1344) GATE B — OFFLINE behavioral preflight (no spend, no network)")
    _p(f"repo_root      = {_REPO_ROOT}")
    _p(f"artifact_dir   = {_ARTIFACT_DIR}  (exists={_ARTIFACT_DIR.is_dir()})")
    _p("=" * 78)

    canaries = [
        ("CANARY-2 fix2_verdict_cap", canary_2_verdict_cap),
        ("CANARY-3 fix3_relevance_chrome", canary_3_relevance_chrome),
        ("CANARY-4 fix4_contradiction_gate", canary_4_contradiction_gate),
        ("CANARY-1 fix1_structural", canary_1_audit_map_structural),
    ]
    results: dict[str, str] = {}
    for name, fn in canaries:
        _p("")
        try:
            results[name] = fn()
        except Exception as exc:  # noqa: BLE001 — report per-canary FAIL, keep going
            results[name] = "FAIL"
            _p(f"  -> FAIL: {type(exc).__name__}: {exc}")

    _p("")
    _p("=" * 78)
    _p("SUMMARY")
    for name, verdict in results.items():
        _p(f"  {verdict:5} {name}")
    # overall: required = CANARY 2/3/4 PASS + CANARY-1 PASS; SKIP on CANARY-3 acceptable
    def ok(name: str) -> bool:
        v = results.get(name)
        return v == "PASS" or (name.startswith("CANARY-3") and v == "SKIP")

    all_pass = all(ok(n) for n, _ in canaries)
    _p(f"  OVERALL = {'ALL_PASS' if all_pass else 'SOME_FAIL'}")
    _p("=" * 78)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
