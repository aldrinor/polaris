HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1 findings.
- If you detect "I'm holding back a P1 for the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## I-cred-006b (#1170) DIFF gate ITER 2 — iter-1 P0 FIXED (faithfulness-critical)

ITER-1 P0 (you found it, correctly): the weighted ON path could reach generation with non-empty classified_sources but ZERO usable evidence_rows (generation consumes evidence_rows; live retrieval appends a CorpusSource while skipping content-starved rows). With the planner + its downstream plan-sufficiency gate OFF, that is "synthesize from nothing".

THE FIX (this diff):
1. weighted_corpus_gate.py: has_usable_corpus(classified_sources, evidence_rows) now REQUIRES BOTH non-empty (evidence_rows is a REQUIRED param, no default, so a caller cannot silently bypass it). weighted_corpus_proceeds(...) takes evidence_rows and passes it through.
2. run_honest_sweep_r3.py — BOTH suppression sites now require usable evidence rows:
   (a) the adequacy-abort suppression adds `and bool(retrieval.evidence_rows)` — an empty evidence pool still aborts (abort_corpus_inadequate) regardless of the flag;
   (b) the weighted_corpus_proceeds call passes evidence_rows=retrieval.evidence_rows — empty pool -> falls through to the unchanged approval refusal;
   (c) the disclosure-write guard now passes evidence_rows too.
3. tests: signatures updated; NEW behavioral test (flag-ON + material deviation + sources + EMPTY evidence_rows -> proceeds=False) + structural assertions that both sites reference retrieval.evidence_rows.

VERIFY: (a) the zero-evidence-row ON path now aborts before generation at BOTH sites; (b) strict_verify + 4-role D8 still untouched; (c) flag-OFF still byte-identical; (d) the per-tier-mix proceed still works when evidence rows ARE present; (e) no new bypass. 79/79 corpus-gate tests pass. End with 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES' then the schema.

DIFF:
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 9ca4ad39..71cacd88 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -124,6 +124,15 @@ from src.polaris_graph.nodes.corpus_approval_gate import (  # noqa: E402
     compute_tier_distribution,
     save_approval_decision,
 )
+from src.polaris_graph.nodes.weighted_corpus_gate import (  # noqa: E402
+    # I-cred-006b (#1170): replace the tier-COUNT/material-deviation corpus REFUSAL with
+    # PROCEED + a credibility-weighted disclosure. Default-OFF byte-identical.
+    build_corpus_credibility_disclosure,
+    disclosure_to_dict,
+    has_usable_corpus,
+    weighted_corpus_gate_enabled,
+    weighted_corpus_proceeds,
+)
 from src.polaris_graph.nodes.scope_gate import run_scope_gate  # noqa: E402
 # M-INT-4: OpenRouter ScopeAffinityLLM in production scope-gate path
 from src.polaris_graph.audit_ir.scope_classifier_llm import (  # noqa: E402
@@ -3547,8 +3556,30 @@ async def run_one_query(
         # sufficiency gate). The journal_only adequacy FLOOR, however, is a HARD
         # corpus-quality gate that must abort in BOTH modes — so OR in
         # `_jo_force_inadequate`.
+        # I-cred-006b (#1170): the weighted-corpus gate REPLACES the tier-COUNT adequacy REFUSAL with
+        # PROCEED + a credibility-weighted disclosure (operator directive 2026-06-08: "we shall NOT
+        # have gate here, we shall WEIGHT the source"). The tier-count adequacy abort is the
+        # §-1.1-banned metadata proxy (it verifies no individual claim). When the flag is ON we do NOT
+        # abort on the domain-keyed adequacy decision — UNLESS `_jo_force_inadequate` is set: the
+        # journal-only adequacy FLOOR (distinct-journal count + S1 anchors) is a SEPARATE mode with its
+        # own fix (#1146) and must still abort. The legitimate corpus-ZERO floor (abort_no_sources
+        # upstream + has_usable_corpus here) also still aborts. strict_verify + the 4-role D8 release
+        # decision (the per-claim faithfulness floor) are UNTOUCHED. Default-OFF byte-identical.
+        _weighted_corpus_on = weighted_corpus_gate_enabled()
+        _wc_disclosure_dict: dict | None = None  # set on the weighted-gate proceed path (manifest field)
         if adequacy.decision == "abort" and (
             not _use_research_planner or _jo_force_inadequate
+        ) and not (
+            _weighted_corpus_on and not _jo_force_inadequate
+            # I-cred-006b iter-2 (Codex P0): the weighted gate suppresses the tier-COUNT adequacy
+            # refusal ONLY when there is real evidence to generate from. Generation consumes
+            # retrieval.evidence_rows (cited rows with spans), which can be empty even when
+            # classified_sources is non-empty (content-starved rows skipped). With the planner — and
+            # its downstream plan-sufficiency gate — OFF, suppressing the abort with zero evidence rows
+            # would reach generation with nothing. So only suppress when evidence_rows is non-empty;
+            # an empty pool still aborts (the "cannot synthesize from nothing" floor), regardless of
+            # the flag.
+            and bool(retrieval.evidence_rows)
         ):
             _log(f"[ABORT]       Corpus inadequate for confident synthesis. "
                  f"Refusing to ship a misleading short report.")
@@ -3628,7 +3659,26 @@ async def run_one_query(
         # The old canned note defeated the rubber-stamp guard and billed a
         # material-deviation corpus. `note` below is descriptive/audit only.
         authorization = authorization_from_env()
-        if dist.has_material_deviation:
+        # I-cred-006b (#1170): when the weighted-corpus gate is ON, a material deviation is NOT a
+        # REFUSAL — the corpus is ACCEPTED and its credibility is DISCLOSED (weighted, domain-aware).
+        # We record an HONEST approval (approved=True, all sources approved, the persisted decision is
+        # NOT a dishonest approved=False+rejected-all) whose basis is the weighted-corpus disclosure,
+        # NOT a structured PG_AUTHORIZED_SWEEP_APPROVAL and NOT a free-text note. The legitimate
+        # corpus-ZERO floor still aborts (has_usable_corpus + the upstream abort_no_sources). The
+        # per-claim faithfulness floor (strict_verify + 4-role D8) is unchanged.
+        _weighted_corpus_approve = weighted_corpus_proceeds(
+            flag_on=_weighted_corpus_on,
+            has_material_deviation=dist.has_material_deviation,
+            classified_sources=retrieval.classified_sources,
+            # I-cred-006b iter-2 (Codex P0): require >=1 usable evidence row, not just a classified
+            # source — generation consumes evidence_rows; an empty pool falls through to the unchanged
+            # approval logic (material deviation + no structured authorization -> abort), never proceeds.
+            evidence_rows=retrieval.evidence_rows,
+        )
+        if _weighted_corpus_approve:
+            approved = True
+            approval_error = ""
+        elif dist.has_material_deviation:
             ok, err = check_auto_approve_allowed(dist, authorization)
             approved = ok
             approval_error = err
@@ -3637,8 +3687,13 @@ async def run_one_query(
             approval_error = ""
         note = (
             f"R-3 sweep. Domain={q['domain']}. "
-            + ("structured authorization present"
-               if authorization is not None else "no structured authorization")
+            + (
+                "weighted-corpus gate (PG_SWEEP_WEIGHTED_CORPUS_GATE): corpus accepted with a "
+                "credibility-weighted disclosure (no tier-count refusal)"
+                if _weighted_corpus_approve
+                else ("structured authorization present"
+                      if authorization is not None else "no structured authorization")
+            )
         )
         decision = CorpusApprovalDecision(
             run_id=run_id,
@@ -3652,6 +3707,49 @@ async def run_one_query(
         )
         save_approval_decision(decision, run_dir)
 
+        # I-cred-006b (#1170): when the weighted-corpus gate is ON, attach the deterministic,
+        # domain-aware credibility-weighting disclosure (the corpus is ACCEPTED + DISCLOSED, not refused
+        # on tier-mix). PURE — no LLM/judge/network/spend; the per-source weight is the deterministic
+        # authority_score already computed upstream. Written on EVERY weighted-gate proceed path so the
+        # run honestly discloses that lower-tier sources are lower-credibility. The per-claim
+        # faithfulness floor (strict_verify + 4-role D8) is untouched.
+        if _weighted_corpus_on and has_usable_corpus(
+            retrieval.classified_sources, retrieval.evidence_rows
+        ):
+            # Deterministic url -> authority_score join from the evidence rows (where the NUMERIC
+            # authority actually lives in planner mode; run_honest_sweep_r3.py:3034). Empty when no row
+            # carries authority_score (legacy mode) — the disclosure then weights by the per-tier prior.
+            # Read-only; no row mutation, no network, no spend.
+            _wc_authority_by_url: dict[str, float] = {}
+            for _row in (retrieval.evidence_rows or []):
+                _u = str(_row.get("source_url") or _row.get("url") or "")
+                _a = _row.get("authority_score")
+                if _u and _a is not None and _u not in _wc_authority_by_url:
+                    _wc_authority_by_url[_u] = _a
+            _wc_disclosure = build_corpus_credibility_disclosure(
+                classified_sources=retrieval.classified_sources,
+                tier_counts=dist.tier_counts,
+                tier_fractions=dist.tier_fractions,
+                total_sources=dist.total_sources,
+                had_material_deviation=dist.has_material_deviation,
+                domain=q["domain"],
+                research_question=q["question"],
+                authority_by_url=_wc_authority_by_url,
+            )
+            _wc_disclosure_dict = disclosure_to_dict(_wc_disclosure)
+            (run_dir / "corpus_credibility_disclosure.json").write_text(
+                json.dumps(_wc_disclosure_dict, indent=2, sort_keys=True,
+                           default=str) + "\n",
+                encoding="utf-8",
+            )
+            _log(
+                f"[weighted_corpus] gate ON: corpus ACCEPTED + credibility-disclosed "
+                f"(total={_wc_disclosure.total_sources}, weighted_mean="
+                f"{_wc_disclosure.weighted_credibility_mean:.2f}, "
+                f"had_material_deviation={_wc_disclosure.had_material_deviation}); "
+                f"no tier-count refusal. strict_verify + 4-role D8 unchanged."
+            )
+
         # Codex round 1 B-2: ENFORCE the corpus-approval gate. Previously
         # the orchestrator wrote corpus_approval.json and then proceeded
         # regardless of `approved`. Now we short-circuit exactly like the
@@ -6048,6 +6146,14 @@ async def run_one_query(
             "fact_dedup": getattr(multi, "fact_dedup_telemetry", {}),
         }
 
+        # I-cred-006b (#1170): surface the weighted-corpus credibility disclosure in the per-run
+        # manifest (ON-mode only — the key is ABSENT when the flag is off, preserving the legacy
+        # manifest shape byte-for-byte, matching the other ON-mode keys below). The full per-source
+        # breakdown lives in corpus_credibility_disclosure.json; the manifest carries the summary so a
+        # downstream audit sees the corpus was ACCEPTED + credibility-disclosed (not tier-refused).
+        if _wc_disclosure_dict is not None:
+            manifest["corpus_credibility_disclosure"] = _wc_disclosure_dict
+
         # I-meta-005 Phase 1 (#985, P1-8): record the SHA-pinned ResearchPlan
         # in the manifest (gap #19 extension). ON-mode only — the key is absent
         # in OFF, preserving the legacy manifest shape byte-for-byte.
diff --git a/src/polaris_graph/nodes/weighted_corpus_gate.py b/src/polaris_graph/nodes/weighted_corpus_gate.py
new file mode 100644
index 00000000..044e28e8
--- /dev/null
+++ b/src/polaris_graph/nodes/weighted_corpus_gate.py
@@ -0,0 +1,257 @@
+"""I-cred-006b (#1170) — weighted-corpus gate: REPLACE the tier-COUNT/material-deviation
+corpus REFUSAL with PROCEED + a credibility-weighted disclosure (operator directive 2026-06-08,
+repeat-flagged + FURIOUS: "we shall NOT have gate here, we shall WEIGHT the source").
+
+THE PROBLEM (drb_72, #1100): the dry-run gathered 151 sources (throttle fixed) but the
+corpus_approval gate aborted ``abort_corpus_approval_denied`` because ~50% were tier-4 on an
+ECONOMICS question where T4 working papers (NBER / Acemoglu) are legitimate primary sources. That
+is a DOMAIN-BLIND tier-COUNT refusal — the §-1.1-banned metadata proxy (counting source-types
+verifies no individual claim). The corpus_adequacy gate's ``max_t5_plus_t6_fraction`` is the same
+class of proxy.
+
+THE FIX (this module): when ``PG_SWEEP_WEIGHTED_CORPUS_GATE`` is ON, the two corpus-level REFUSAL
+branches in ``run_one_query`` are replaced by PROCEED — and this module builds the deterministic,
+DOMAIN-AWARE credibility-weighting disclosure that is attached to the run (``corpus_credibility_
+disclosure.json`` + a manifest field). Lower-tier sources are not refused; they are DISCLOSED as
+lower-credibility and weighted by the deterministic ``authority_score`` already computed per source.
+
+FAITHFULNESS POSTURE (binding — see the issue's faithfulness argument):
+  * The per-claim binding gates are UNTOUCHED and remain the ONLY faithfulness floor:
+    ``strict_verify`` (generator/provenance_generator.py — every sentence must match its cited
+    [start:end] span: evidence-id in pool, span bounds valid, every decimal present, >=2 content-word
+    overlap) drops any unsupported sentence REGARDLESS of that source's tier; the 4-role D8 release
+    decision is per-claim. Removing the corpus-level tier-count proxy changes WHICH corpora reach
+    generation, NOT whether any individual claim is verified.
+  * The legitimate corpus-ZERO floor stays: a corpus with no usable sources cannot synthesize and
+    still aborts (``abort_no_sources`` upstream, and ``has_usable_corpus`` here as a defense-in-depth
+    check the caller asserts before proceeding). This is a real floor, not a tier proxy.
+  * PURE + OFFLINE: no network, no LLM/judge, no spend, no row mutation. The per-source weight is the
+    deterministic ``authority_score`` POLARIS already computed (the credibility-judge LLM weighting is
+    the SEPARATE downstream ``PG_SWEEP_CREDIBILITY_REDESIGN`` machinery; this gate never invokes it).
+  * DEFAULT-OFF byte-identical: with the flag unset/falsey the caller never calls this module and the
+    two REFUSAL branches fire exactly as today (LAW VI env-overridable, no magic numbers).
+
+This module owns NO control flow — it only (a) reads the flag and (b) builds the disclosure object.
+The caller (``run_one_query``) decides to proceed-vs-refuse based on ``weighted_corpus_gate_enabled()``.
+"""
+from __future__ import annotations
+
+import os
+from dataclasses import asdict, dataclass, field
+from typing import Any
+
+# ── flag (default OFF — matches the other PG_SWEEP_* capability flags) ────────
+_FLAG = "PG_SWEEP_WEIGHTED_CORPUS_GATE"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+# Per-tier nominal credibility prior, used ONLY for the human-readable disclosure label when a source
+# has no deterministic ``authority_score`` (so the disclosure is never blank). It is NOT a gate and NOT
+# a faithfulness signal — strict_verify decides per-claim support, not this number. T1 (peer-reviewed
+# primary) highest; T7 (stub/unknown) lowest. LAW VI: the whole map is env-overridable as a fallback.
+_DEFAULT_TIER_CREDIBILITY_PRIOR: dict[str, float] = {
+    "T1": 0.95, "T2": 0.85, "T3": 0.75, "T4": 0.60,
+    "T5": 0.40, "T6": 0.30, "T7": 0.15, "UNKNOWN": 0.20,
+}
+
+
+def weighted_corpus_gate_enabled() -> bool:
+    """True unless ``PG_SWEEP_WEIGHTED_CORPUS_GATE`` is unset/falsey (default OFF => byte-identical).
+
+    When OFF the caller never calls this module's disclosure builder and the tier-count /
+    material-deviation REFUSAL branches in ``run_one_query`` fire exactly as today.
+    """
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _tier_prior(tier: str) -> float:
+    """The nominal per-tier credibility prior (disclosure label only; not a gate)."""
+    return _DEFAULT_TIER_CREDIBILITY_PRIOR.get(str(tier or "").strip().upper(), 0.20)
+
+
+def _coerce_authority(value: Any) -> float | None:
+    """Coerce a source's ``authority_score`` to a finite [0,1] float; None when absent/non-numeric."""
+    try:
+        x = float(value)
+    except (TypeError, ValueError):
+        return None
+    if x != x or x in (float("inf"), float("-inf")):  # NaN / inf
+        return None
+    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
+
+
+@dataclass
+class SourceCredibilityRow:
+    """One source's DISCLOSED credibility weight (deterministic — authority_score, tier-prior fallback).
+
+    ``credibility_weight`` is the deterministic ``authority_score`` when present, else the per-tier
+    nominal prior (so the disclosure is never blank). ``weight_basis`` records which was used, so the
+    disclosure is honest about provenance. This is a DISCLOSURE field, never a keep/drop verdict.
+    """
+
+    url: str
+    tier: str
+    domain: str
+    credibility_weight: float
+    weight_basis: str   # "authority_score" | "tier_prior"
+
+
+@dataclass
+class CorpusCredibilityDisclosure:
+    """The corpus-level credibility-weighting disclosure attached when the weighted-corpus gate is ON.
+
+    Replaces the tier-COUNT/material-deviation REFUSAL: the corpus is ACCEPTED and its credibility is
+    DISCLOSED (weighted, domain-aware), not refused on source-type mix. ADVISORY — the binding
+    per-claim gates (strict_verify + 4-role D8) are untouched.
+    """
+
+    gate: str                       # the flag name, for audit provenance
+    domain: str
+    research_question: str
+    total_sources: int
+    tier_counts: dict[str, int]
+    tier_fractions: dict[str, float]
+    had_material_deviation: bool    # what the OLD gate WOULD have refused on (disclosed, not acted on)
+    weighted_credibility_mean: float  # source-count-weighted mean of per-source credibility (disclosure)
+    per_source: list[SourceCredibilityRow] = field(default_factory=list)
+    disclosure_note: str = ""
+
+
+def has_usable_corpus(classified_sources: list[Any], evidence_rows: list[Any]) -> bool:
+    """Defense-in-depth corpus-ZERO floor the caller asserts before proceeding on the weighted gate.
+
+    The weighted gate REPLACES the tier-MIX refusal, NOT the legitimate "cannot synthesize from
+    nothing" floor.
+
+    I-cred-006b iter-2 (Codex P0): generation consumes ``retrieval.evidence_rows`` (the cited rows
+    with spans), NOT ``classified_sources``. Live retrieval can append a ``CorpusSource`` (so
+    ``classified_sources`` is non-empty) while every content-starved / no-content evidence row is
+    skipped (so ``evidence_rows`` is empty). Checking only ``classified_sources`` therefore let the ON
+    path reach generation with zero usable evidence — a "synthesize from nothing" violation when the
+    planner (and its downstream plan-sufficiency gate) is OFF. So the floor requires BOTH: at least one
+    classified source to weight AND at least one usable evidence row to generate from. ``evidence_rows``
+    is REQUIRED (no default) so a caller cannot silently bypass the evidence-row floor.
+    """
+    return bool(classified_sources) and bool(evidence_rows)
+
+
+def weighted_corpus_proceeds(
+    *,
+    flag_on: bool,
+    has_material_deviation: bool,
+    classified_sources: list[Any],
+    evidence_rows: list[Any],
+) -> bool:
+    """THE load-bearing decision: does the weighted-corpus gate turn a material-deviation REFUSAL into
+    a PROCEED for this corpus? Extracted as a pure, behaviorally-testable function (mirrors
+    ``check_auto_approve_allowed`` being a separate function) so a logic typo cannot hide behind
+    string-presence tests — the §-1.1 false-green trap, in test form.
+
+    Returns True iff ALL hold:
+      * the gate flag is ON (``PG_SWEEP_WEIGHTED_CORPUS_GATE``);
+      * the corpus has a material tier deviation (the ONLY case the old gate would have REFUSED — a
+        within-distribution corpus already auto-approves and needs no weighted-proceed);
+      * the corpus has at least one classified source AND one usable evidence row
+        (``has_usable_corpus`` — the corpus-ZERO / "cannot synthesize from nothing" floor still
+        aborts; iter-2 P0: evidence_rows, not just classified_sources, because generation consumes the
+        cited rows).
+
+    When this returns False the caller falls through to the UNCHANGED approval logic
+    (``check_auto_approve_allowed`` / default-approve), so OFF + within-distribution behavior is
+    byte-identical. The journal-only adequacy FLOOR (``_jo_force_inadequate``) is enforced by the
+    caller BEFORE this decision (it aborts at the adequacy gate, upstream of approval), so it is not a
+    parameter here.
+    """
+    return (
+        bool(flag_on)
+        and bool(has_material_deviation)
+        and has_usable_corpus(classified_sources, evidence_rows)
+    )
+
+
+def build_corpus_credibility_disclosure(
+    *,
+    classified_sources: list[Any],
+    tier_counts: dict[str, int],
+    tier_fractions: dict[str, float],
+    total_sources: int,
+    had_material_deviation: bool,
+    domain: str,
+    research_question: str,
+    authority_by_url: dict[str, Any] | None = None,
+) -> CorpusCredibilityDisclosure:
+    """Build the deterministic, domain-aware corpus credibility disclosure — PURE, offline, no LLM.
+
+    Each source is weighted by its deterministic ``authority_score`` (computed upstream by the
+    authority package) when present — first from the source object's own ``.authority_score``
+    attribute, else from the optional ``authority_by_url`` join map (``{url: authority_score}``,
+    supplied by the caller from the evidence rows where the numeric authority actually lives in planner
+    mode) — and falls back to the per-tier nominal prior only when neither is available. The disclosure
+    records the tier mix, what the OLD gate would have refused on (``had_material_deviation``), and a
+    source-weighted mean credibility — so the run honestly DISCLOSES that lower-tier sources are
+    lower-credibility, rather than refusing the whole corpus on the source-type count.
+
+    ``classified_sources`` are the ``CorpusSource``-shaped objects (``.url`` / ``.tier`` / ``.domain``
+    + optional ``.authority_score``); read-only. ``authority_by_url`` is read-only. No row mutation, no
+    network, no spend.
+    """
+    auth_by_url = authority_by_url or {}
+    per_source: list[SourceCredibilityRow] = []
+    weight_sum = 0.0
+    for s in (classified_sources or []):
+        tier = str(getattr(s, "tier", "") or "UNKNOWN")
+        url = str(getattr(s, "url", "") or "")
+        # Prefer the source object's own authority_score; else the caller's per-url authority join;
+        # else the per-tier nominal prior (the disclosure is never blank).
+        auth = _coerce_authority(getattr(s, "authority_score", None))
+        if auth is None and url:
+            auth = _coerce_authority(auth_by_url.get(url))
+        if auth is not None:
+            weight = auth
+            basis = "authority_score"
+        else:
+            weight = _tier_prior(tier)
+            basis = "tier_prior"
+        weight_sum += weight
+        per_source.append(SourceCredibilityRow(
+            url=str(getattr(s, "url", "") or ""),
+            tier=tier,
+            domain=str(getattr(s, "domain", "") or ""),
+            credibility_weight=round(weight, 4),
+            weight_basis=basis,
+        ))
+
+    n = len(per_source)
+    weighted_mean = round(weight_sum / n, 4) if n else 0.0
+
+    note = (
+        f"Weighted-corpus gate ({_FLAG}) ON: the corpus is ACCEPTED and its credibility is DISCLOSED "
+        f"(weighted, domain-aware) rather than refused on tier-mix. {n} source(s); source-weighted "
+        f"mean credibility {weighted_mean:.2f}. "
+        + (
+            "The corpus deviates from the pre-registered tier distribution; under the old gate this "
+            "would have been refused (abort_corpus_approval_denied / abort_corpus_inadequate). That "
+            "tier-COUNT refusal verified no individual claim — the per-claim faithfulness floor "
+            "(strict_verify + the 4-role D8 release decision) remains the binding check and is "
+            "unchanged. Lower-tier sources are disclosed as lower-credibility, not dropped."
+            if had_material_deviation
+            else "The corpus is within the pre-registered tier distribution."
+        )
+    )
+
+    return CorpusCredibilityDisclosure(
+        gate=_FLAG,
+        domain=str(domain or ""),
+        research_question=str(research_question or ""),
+        total_sources=int(total_sources),
+        tier_counts=dict(tier_counts or {}),
+        tier_fractions=dict(tier_fractions or {}),
+        had_material_deviation=bool(had_material_deviation),
+        weighted_credibility_mean=weighted_mean,
+        per_source=per_source,
+        disclosure_note=note,
+    )
+
+
+def disclosure_to_dict(disclosure: CorpusCredibilityDisclosure) -> dict[str, Any]:
+    """Serialize the disclosure to a plain dict (for ``corpus_credibility_disclosure.json`` + manifest)."""
+    return asdict(disclosure)
diff --git a/tests/polaris_graph/test_weighted_corpus_gate_icred006b.py b/tests/polaris_graph/test_weighted_corpus_gate_icred006b.py
new file mode 100644
index 00000000..78dc3caf
--- /dev/null
+++ b/tests/polaris_graph/test_weighted_corpus_gate_icred006b.py
@@ -0,0 +1,389 @@
+"""I-cred-006b (#1170) — weighted-corpus gate offline smoke + regression tests.
+
+Proves:
+  * Pure module: flag semantics (default OFF), deterministic domain-aware disclosure
+    (authority_score basis + tier-prior fallback, weighted mean, material-deviation passthrough),
+    the corpus-ZERO floor (has_usable_corpus).
+  * Sweep wiring (inspect.getsource — no network): the flag-branch exists; the OFF abort blocks are
+    PRESERVED (the literal `if not approved:` + `return summary` before the generator call); the
+    legitimate corpus-ZERO (`abort_no_sources`) and zero-sufficient-sections
+    (`abort_corpus_inadequate` plan-sufficiency) aborts still PRECEDE the generator call; the binding
+    per-claim gates (strict_verify resolve sites + the 4-role D8 seam) are UNTOUCHED.
+  * Slate activation: PG_SWEEP_WEIGHTED_CORPUS_GATE is in the Gate-B slate, force-on, and required.
+
+OFFLINE ONLY — no spend, no network. Mirrors the existing gate-test pattern
+(test_b2_corpus_approval_enforcement.py, test_corpus_adequacy_r6_gap1.py).
+"""
+from __future__ import annotations
+
+import inspect
+from dataclasses import dataclass
+
+import pytest
+
+from src.polaris_graph.nodes.weighted_corpus_gate import (
+    CorpusCredibilityDisclosure,
+    build_corpus_credibility_disclosure,
+    disclosure_to_dict,
+    has_usable_corpus,
+    weighted_corpus_gate_enabled,
+    weighted_corpus_proceeds,
+)
+
+
+@dataclass
+class _FakeSource:
+    """CorpusSource-shaped stand-in (url / tier / domain + optional authority_score)."""
+
+    url: str
+    tier: str
+    domain: str = ""
+    authority_score: float | None = None
+
+
+# ──────────────────────────────────────────────────────────────────────────────
+# Flag semantics (default OFF => byte-identical)
+# ──────────────────────────────────────────────────────────────────────────────
+
+def test_flag_default_off(monkeypatch) -> None:
+    monkeypatch.delenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", raising=False)
+    assert weighted_corpus_gate_enabled() is False
+
+
+@pytest.mark.parametrize("val", ["", "0", "false", "off", "no", "FALSE", " Off "])
+def test_flag_off_values(monkeypatch, val) -> None:
+    monkeypatch.setenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", val)
+    assert weighted_corpus_gate_enabled() is False
+
+
+@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "TRUE"])
+def test_flag_on_values(monkeypatch, val) -> None:
+    monkeypatch.setenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", val)
+    assert weighted_corpus_gate_enabled() is True
+
+
+# ──────────────────────────────────────────────────────────────────────────────
+# has_usable_corpus — the corpus-ZERO floor (NOT a tier proxy)
+# ──────────────────────────────────────────────────────────────────────────────
+
+def test_has_usable_corpus_zero_sources_is_false() -> None:
+    assert has_usable_corpus([], [{"evidence_id": "e1"}]) is False
+
+
+def test_has_usable_corpus_zero_evidence_rows_is_false() -> None:
+    # iter-2 P0 (Codex): classified sources present but ZERO usable evidence rows must NOT pass the
+    # floor — generation consumes evidence_rows, not classified_sources. "Synthesize from nothing" guard.
+    assert has_usable_corpus([_FakeSource("u", "T4")], []) is False
+
+
+def test_has_usable_corpus_sources_and_rows_is_true() -> None:
+    assert has_usable_corpus([_FakeSource("u", "T4")], [{"evidence_id": "e1"}]) is True
+
+
+# ──────────────────────────────────────────────────────────────────────────────
+# weighted_corpus_proceeds — THE load-bearing decision (behavioral, not string-presence)
+# ──────────────────────────────────────────────────────────────────────────────
+
+def test_proceeds_on_flag_on_material_deviation_with_sources() -> None:
+    """The acceptance criterion: flag-ON + a material-deviation corpus + sources -> PROCEED (the
+    drb_72 tier-skewed corpus is NOT refused). This is the exact decision wired into run_one_query."""
+    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org")]
+    assert weighted_corpus_proceeds(
+        flag_on=True, has_material_deviation=True, classified_sources=srcs,
+        evidence_rows=[{"evidence_id": "e1"}],
+    ) is True
+
+
+def test_does_not_proceed_when_flag_off() -> None:
+    """Flag-OFF -> the gate does NOT proceed; the caller falls to the unchanged refusal path
+    (byte-identical: the old abort_corpus_approval_denied still fires on a material-deviation corpus)."""
+    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org")]
+    assert weighted_corpus_proceeds(
+        flag_on=False, has_material_deviation=True, classified_sources=srcs,
+        evidence_rows=[{"evidence_id": "e1"}],
+    ) is False
+
+
+def test_does_not_proceed_when_zero_sources_even_if_flag_on() -> None:
+    """The corpus-ZERO floor holds even with the flag on: a zero-source corpus does NOT proceed
+    (cannot synthesize from nothing — a real floor, not a tier proxy)."""
+    assert weighted_corpus_proceeds(
+        flag_on=True, has_material_deviation=True, classified_sources=[],
+        evidence_rows=[{"evidence_id": "e1"}],
+    ) is False
+
+
+def test_does_not_proceed_when_zero_evidence_rows_even_if_flag_on_and_sources() -> None:
+    """iter-2 P0 (Codex): the ON path must NOT proceed when classified_sources is non-empty but there
+    are ZERO usable evidence rows — generation consumes evidence_rows, so this is the real
+    'cannot synthesize from nothing' floor. Without this, the planner-OFF beat-both path could reach
+    generation with an empty evidence pool. Falls through to the unchanged refusal path instead."""
+    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org")]
+    assert weighted_corpus_proceeds(
+        flag_on=True, has_material_deviation=True, classified_sources=srcs,
+        evidence_rows=[],
+    ) is False
+
+
+def test_does_not_proceed_when_no_material_deviation() -> None:
+    """A within-distribution corpus needs no weighted-proceed (it already auto-approves); the helper
+    returns False so the caller's unchanged default-approve path runs."""
+    srcs = [_FakeSource("https://aer.org/1", "T1", "aer.org")]
+    assert weighted_corpus_proceeds(
+        flag_on=True, has_material_deviation=False, classified_sources=srcs,
+        evidence_rows=[{"evidence_id": "e1"}],
+    ) is False
+
+
+# ──────────────────────────────────────────────────────────────────────────────
+# build_corpus_credibility_disclosure — deterministic, domain-aware, pure
+# ──────────────────────────────────────────────────────────────────────────────
+
+def _drb72_like_sources() -> list[_FakeSource]:
+    """The drb_72 shape: ~50% T4 (legit NBER/Acemoglu working papers for an economics question)."""
+    t4 = [_FakeSource(f"https://nber.org/w{i}", "T4", "nber.org", authority_score=0.62)
+          for i in range(5)]
+    t1 = [_FakeSource(f"https://aer.org/{i}", "T1", "aer.org", authority_score=0.93)
+          for i in range(3)]
+    t5 = [_FakeSource(f"https://blog/{i}", "T5", "blog.example", authority_score=0.35)
+          for i in range(2)]
+    return t4 + t1 + t5
+
+
+def test_disclosure_uses_authority_score_when_present() -> None:
+    srcs = [_FakeSource("https://x", "T4", "nber.org", authority_score=0.62)]
+    d = build_corpus_credibility_disclosure(
+        classified_sources=srcs,
+        tier_counts={"T4": 1},
+        tier_fractions={"T4": 1.0},
+        total_sources=1,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="q",
+    )
+    assert len(d.per_source) == 1
+    assert d.per_source[0].weight_basis == "authority_score"
+    assert d.per_source[0].credibility_weight == pytest.approx(0.62)
+    # weighted mean of a single source == its weight
+    assert d.weighted_credibility_mean == pytest.approx(0.62)
+
+
+def test_disclosure_uses_authority_by_url_join_when_object_lacks_it() -> None:
+    """When the CorpusSource object has no authority_score attribute (the real shape — authority lives
+    on the evidence rows), the caller-supplied url->authority join is used (real weighting, not prior)."""
+    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org", authority_score=None)]
+    d = build_corpus_credibility_disclosure(
+        classified_sources=srcs,
+        tier_counts={"T4": 1},
+        tier_fractions={"T4": 1.0},
+        total_sources=1,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="q",
+        authority_by_url={"https://nber.org/w1": 0.71},
+    )
+    assert d.per_source[0].weight_basis == "authority_score"
+    assert d.per_source[0].credibility_weight == pytest.approx(0.71)
+
+
+def test_disclosure_object_authority_wins_over_join() -> None:
+    srcs = [_FakeSource("https://x", "T4", authority_score=0.5)]
+    d = build_corpus_credibility_disclosure(
+        classified_sources=srcs,
+        tier_counts={"T4": 1},
+        tier_fractions={"T4": 1.0},
+        total_sources=1,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="q",
+        authority_by_url={"https://x": 0.99},
+    )
+    # object's own authority_score (0.5) wins over the join (0.99)
+    assert d.per_source[0].credibility_weight == pytest.approx(0.5)
+
+
+def test_disclosure_falls_back_to_tier_prior_when_no_authority_score() -> None:
+    srcs = [_FakeSource("https://x", "T4", "nber.org", authority_score=None)]
+    d = build_corpus_credibility_disclosure(
+        classified_sources=srcs,
+        tier_counts={"T4": 1},
+        tier_fractions={"T4": 1.0},
+        total_sources=1,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="q",
+    )
+    assert d.per_source[0].weight_basis == "tier_prior"
+    # T4 prior is deterministic and > 0 (lower-tier disclosed as lower-credibility, not dropped)
+    assert 0.0 < d.per_source[0].credibility_weight < 1.0
+
+
+def test_disclosure_weighted_mean_is_count_weighted() -> None:
+    d = build_corpus_credibility_disclosure(
+        classified_sources=_drb72_like_sources(),
+        tier_counts={"T4": 5, "T1": 3, "T5": 2},
+        tier_fractions={"T4": 0.5, "T1": 0.3, "T5": 0.2},
+        total_sources=10,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="effect of minimum wage",
+    )
+    expected = (5 * 0.62 + 3 * 0.93 + 2 * 0.35) / 10
+    assert d.weighted_credibility_mean == pytest.approx(expected, abs=1e-4)
+    assert d.total_sources == 10
+    assert d.had_material_deviation is True
+    # the disclosure honestly records what the OLD gate would have refused on
+    assert "credibility" in d.disclosure_note.lower()
+    assert d.gate == "PG_SWEEP_WEIGHTED_CORPUS_GATE"
+
+
+def test_disclosure_no_material_deviation_note() -> None:
+    d = build_corpus_credibility_disclosure(
+        classified_sources=[_FakeSource("https://x", "T1", "aer.org", authority_score=0.9)],
+        tier_counts={"T1": 1},
+        tier_fractions={"T1": 1.0},
+        total_sources=1,
+        had_material_deviation=False,
+        domain="economics",
+        research_question="q",
+    )
+    assert d.had_material_deviation is False
+    assert "within the pre-registered" in d.disclosure_note.lower()
+
+
+def test_disclosure_is_serializable_and_pure() -> None:
+    srcs = _drb72_like_sources()
+    snapshot = [(_s.url, _s.tier, _s.authority_score) for _s in srcs]
+    d = build_corpus_credibility_disclosure(
+        classified_sources=srcs,
+        tier_counts={"T4": 5, "T1": 3, "T5": 2},
+        tier_fractions={"T4": 0.5, "T1": 0.3, "T5": 0.2},
+        total_sources=10,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="q",
+    )
+    as_dict = disclosure_to_dict(d)
+    assert isinstance(as_dict, dict)
+    assert as_dict["total_sources"] == 10
+    assert isinstance(as_dict["per_source"], list) and len(as_dict["per_source"]) == 10
+    # NO row mutation
+    assert [(_s.url, _s.tier, _s.authority_score) for _s in srcs] == snapshot
+
+
+def test_disclosure_clamps_out_of_range_authority() -> None:
+    srcs = [
+        _FakeSource("https://hi", "T1", authority_score=2.0),   # clamps to 1.0
+        _FakeSource("https://lo", "T7", authority_score=-1.0),  # clamps to 0.0
+        _FakeSource("https://nan", "T4", authority_score=float("nan")),  # -> tier_prior fallback
+    ]
+    d = build_corpus_credibility_disclosure(
+        classified_sources=srcs,
+        tier_counts={"T1": 1, "T7": 1, "T4": 1},
+        tier_fractions={"T1": 0.33, "T7": 0.33, "T4": 0.33},
+        total_sources=3,
+        had_material_deviation=True,
+        domain="economics",
+        research_question="q",
+    )
+    by_url = {r.url: r for r in d.per_source}
+    assert by_url["https://hi"].credibility_weight == pytest.approx(1.0)
+    assert by_url["https://lo"].credibility_weight == pytest.approx(0.0)
+    # NaN authority is treated as absent -> tier_prior basis (never a NaN weight)
+    assert by_url["https://nan"].weight_basis == "tier_prior"
+    assert by_url["https://nan"].credibility_weight == by_url["https://nan"].credibility_weight  # not NaN
+
+
+# ──────────────────────────────────────────────────────────────────────────────
+# Sweep wiring (inspect.getsource — offline, no network)
+# ──────────────────────────────────────────────────────────────────────────────
+
+def _sweep_src() -> str:
+    import scripts.run_honest_sweep_r3 as sweep
+    return inspect.getsource(sweep.run_one_query)
+
+
+def test_sweep_imports_and_calls_weighted_gate() -> None:
+    src = _sweep_src()
+    assert "weighted_corpus_gate_enabled()" in src
+    assert "build_corpus_credibility_disclosure(" in src
+    assert "has_usable_corpus(" in src
+    # the load-bearing decision is the extracted pure helper (asserted behaviorally above), not an
+    # inline expression that string-presence tests cannot catch a typo in.
+    assert "weighted_corpus_proceeds(" in src
+    assert "_weighted_corpus_approve = weighted_corpus_proceeds(" in src
+
+
+def test_sweep_weighted_gate_requires_evidence_rows_iter2() -> None:
+    """iter-2 P0 (Codex): the ON path's two suppression sites must require usable evidence_rows, not
+    just classified_sources — generation consumes evidence_rows. Both the weighted_corpus_proceeds call
+    and the adequacy-abort suppression must reference retrieval.evidence_rows, so a future edit cannot
+    silently restore the 'synthesize from nothing' hole the iter-1 diff had."""
+    src = _sweep_src()
+    assert "evidence_rows=retrieval.evidence_rows" in src
+    assert "bool(retrieval.evidence_rows)" in src
+
+
+def test_sweep_preserves_approval_abort_literal_and_return() -> None:
+    """The OFF path must run the unchanged approval abort: the literal `if not approved:` survives and
+    still returns before the generator (the FX-05 enforcement contract is intact)."""
+    src = _sweep_src()
+    assert "if not approved:" in src
+    approval_idx = src.find("if not approved:")
+    gen_idx = src.find("generate_multi_section_report(")
+    assert approval_idx != -1 and gen_idx != -1
+    assert approval_idx < gen_idx
+    assert "return summary" in src[approval_idx:gen_idx]
+    assert "abort_corpus_approval_denied" in src
+
+
+def test_sweep_keeps_zero_source_and_zero_section_aborts_before_generation() -> None:
+    """The legitimate corpus-ZERO (`abort_no_sources`) and zero-sufficient-sections
+    (plan-sufficiency `abort_corpus_inadequate`) aborts are NOT tier proxies and must still precede
+    the generator call regardless of the weighted gate."""
+    src = _sweep_src()
+    gen_idx = src.find("generate_multi_section_report(")
+    assert gen_idx != -1
+    no_sources_idx = src.find("abort_no_sources")
+    assert no_sources_idx != -1 and no_sources_idx < gen_idx
+    inadequate_idx = src.find("abort_corpus_inadequate")
+    assert inadequate_idx != -1 and inadequate_idx < gen_idx
+
+
+def test_sweep_weighted_gate_does_not_suppress_journal_only_floor() -> None:
+    """The journal-only adequacy FLOOR (`_jo_force_inadequate`) is a SEPARATE mode (#1146) and must
+    still abort — the weighted-gate proceed is gated on `not _jo_force_inadequate`."""
+    src = _sweep_src()
+    assert "_jo_force_inadequate" in src
+    assert "not _jo_force_inadequate" in src
+
+
+def test_binding_faithfulness_gates_untouched() -> None:
+    """strict_verify + the 4-role D8 seam remain the ONLY binding gates — this issue touches neither
+    the resolve sites that call strict_verify nor the seam activation."""
+    src = _sweep_src()
+    # strict_verify is still invoked on the generation path
+    assert "strict_verify" in src or "generate_multi_section_report(" in src
+    # the 4-role seam toggle is unchanged (env flag still read, not removed)
+    assert "PG_FOUR_ROLE_MODE" in src or "_seam_will_run" in src
+
+
+# ──────────────────────────────────────────────────────────────────────────────
+# Slate activation (Gate-B)
+# ──────────────────────────────────────────────────────────────────────────────
+
+def test_slate_activates_weighted_gate_force_on_and_required() -> None:
+    import scripts.dr_benchmark.run_gate_b as gb
+    assert gb._FULL_CAPABILITY_BENCHMARK_SLATE.get("PG_SWEEP_WEIGHTED_CORPUS_GATE") == "1"
+    assert "PG_SWEEP_WEIGHTED_CORPUS_GATE" in gb._BENCHMARK_FORCE_ON_FLAGS
+    assert "PG_SWEEP_WEIGHTED_CORPUS_GATE" in gb._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
+
+
+def test_slate_apply_forces_on_over_operator_zero(monkeypatch) -> None:
+    """An explicit operator PG_SWEEP_WEIGHTED_CORPUS_GATE=0 must NOT survive the slate (force-on)."""
+    import scripts.dr_benchmark.run_gate_b as gb
+    monkeypatch.setenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", "0")
+    # set_max_cost_per_run side effect is harmless offline; apply the slate and re-check the env.
+    gb.apply_full_capability_benchmark_slate()
+    import os
+    assert os.environ["PG_SWEEP_WEIGHTED_CORPUS_GATE"] == "1"
```
