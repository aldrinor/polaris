HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-beatboth-fix-000 (#1171) — CLINICAL-SCOPE fix — diff review gate

Review the clinical-scope fix. This is a SCOPING-ONLY change for the
clinical cluster of the beat-both fix campaign. Context: the 3 clinical
golden benchmark questions (drb_75 metal-ions-CVD, drb_76
gut-microbiota-CRC, drb_78 parkinsons-DBS) are fully-scoped lit-review
questions whose review-style phrasing names no listed drug and no listed
demographic, so the regex PICO extractor (`extract_pico_heuristic`)
returns BOTH population=None AND intervention=None and the clinical gate
HARD-REJECTS them as `clinical_pico_unscoped` at
`src/polaris_graph/nodes/scope_gate.py:541` (the `len(pico_missing) == 2`
branch). Forensic baseline: those 3 questions aborted at scope ($0,
elapsed ~0.1s) on the real VM run — a false rejection of legitimate
clinical questions.

The fix threads per-question PICO/PCC `scope_overrides` (defined in
`SWEEP_QUERIES`) into the ALREADY-EXISTING `run_scope_gate(user_overrides=...)`
parameter (`scope_gate.py:393`, merged at `:457-459`, recorded in
`protocol.user_overrides` at `:586`). The override sets the two PICO
anchors so the both-anchors-missing hard-reject does not fire.

VERIFY (claim-by-claim against the diff + cited source lines):

(a) PROCEED: the 3 clinical golden questions (drb_75 / drb_76 / drb_78)
    now scope=PROCEED with correct population + intervention. Confirm each
    `scope_overrides` dict carries a non-empty `population` and
    `intervention` and that, fed through `run_scope_gate`, the
    `len(pico_missing) == 2` branch (`scope_gate.py:541`) cannot fire.
    The tests `test_clinical_golden_question_proceeds_with_overrides`
    assert `scope_decision == "proceed"` reading the REAL SWEEP_QUERIES
    overrides (not hardcoded copies).

(b) GATE NOT DISABLED: genuinely-unscoped / off-topic clinical-domain
    questions STILL reject. Confirm the discriminator tests
    (`test_genuinely_unscoped_clinical_still_rejects_discriminator`,
    `test_offtopic_question_without_overrides_still_rejects`,
    `test_clinical_golden_question_still_rejects_without_overrides`)
    prove the gate logic itself is UNTOUCHED — the fix is override
    threading, NOT a softened/disabled gate. The same 3 questions WITHOUT
    overrides must still reject with `clinical_pico_unscoped`.

(c) SCOPING-ONLY: strict_verify / NLI / 4-role are byte-unchanged. The
    scope_overrides set retrieval scope + the protocol PICO fields ONLY;
    they MUST NOT enter the evidence pool, generated prose, strict_verify,
    NLI, or the 4-role gate. Grep the call sites: confirm the diff touches
    only `scripts/run_honest_sweep_r3.py` (SWEEP_QUERIES data + the one
    `run_scope_gate(... user_overrides=q.get("scope_overrides"))` kwarg)
    and the test file — NO verification-gate source file is modified.

(d) PICO OVERRIDE ACCURACY: if PICO overrides are used, verify they are
    ACCURATE for each question and do NOT misrepresent the locked question.
    Read each override's population + intervention against the locked
    question text quoted in SWEEP_QUERIES. They are deliberately BROAD
    population/concept (PCC) phrases derived only from the locked question
    (narrow drug names would over-narrow retrieval — itself a defect).
    Flag any override that asserts a population or intervention NOT present
    in / NOT faithful to the locked question.

(e) DEFAULT-OFF byte-identical + slate-activated if flagged: questions
    WITHOUT a `scope_overrides` key pass None -> `dict(None or {}) == {}`
    (`scope_gate.py:441`) -> byte-identical to today for every other slug
    (drb_90 policy carries no overrides). Both live entry paths share the
    single gate call site: the direct `--only` run AND the Gate-B path
    (`run_gate_b -> run_gate_b_query -> run_one_query`). Confirm the wiring
    tests (`test_live_call_site_threads_scope_overrides`,
    `test_gate_b_loader_carries_scope_overrides_through`) genuinely assert
    the threading on both paths.

End your review with a single line `verdict: APPROVE` or
`verdict: REQUEST_CHANGES`, then the schema:

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

## STAGED DIFF UNDER REVIEW

```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index ea183737..117ce67e 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1085,6 +1085,23 @@ SWEEP_QUERIES: list[dict] = [
             "interventions—such as supplementation—have been proposed, and is "
             "there clinical evidence supporting their feasibility and efficacy?"
         ),
+        # I-beatboth-fix-000 (#1171): broad PCC (Population + Concept) scope
+        # anchors so the regex PICO extractor's both-anchors-missing hard-reject
+        # (scope_gate.py:541) does NOT fire on this scoped lit-review question.
+        # Authored as BROAD population/concept phrases (NOT narrow drug names —
+        # over-narrowing retrieval would itself be a defect) derived only from
+        # the locked question text. Threaded via run_scope_gate(user_overrides=...)
+        # at the live call site; recorded in protocol.user_overrides for the
+        # pre-registration audit trail. Scoping only: these set retrieval scope +
+        # the protocol PICO fields; they never enter the evidence pool, generated
+        # prose, strict_verify, NLI, or the 4-role gate.
+        "scope_overrides": {
+            "population": "adults with or at risk of cardiovascular disease",
+            "intervention": (
+                "modulation of plasma metal-ion levels "
+                "(mineral supplementation, chelation)"
+            ),
+        },
     },
     {
         "slug": "drb_76_gut_microbiota_crc",
@@ -1104,6 +1121,14 @@ SWEEP_QUERIES: list[dict] = [
             "what toxic metabolites do they produce? How might these findings "
             "inform and optimize our daily dietary choices?"
         ),
+        # I-beatboth-fix-000 (#1171): broad PCC scope anchors (see drb_75 note).
+        "scope_overrides": {
+            "population": "adults at risk of colorectal cancer or with gut dysbiosis",
+            "intervention": (
+                "gut-microbiota modulation "
+                "(probiotics, prebiotics, dietary fiber)"
+            ),
+        },
     },
     {
         "slug": "drb_78_parkinsons_dbs",
@@ -1118,6 +1143,14 @@ SWEEP_QUERIES: list[dict] = [
             "and support strategies can be implemented to improve their comfort "
             "and overall well-being?"
         ),
+        # I-beatboth-fix-000 (#1171): broad PCC scope anchors (see drb_75 note).
+        "scope_overrides": {
+            "population": "patients with Parkinson's disease, including post-DBS patients",
+            "intervention": (
+                "deep brain stimulation and Parkinson's disease "
+                "management and support"
+            ),
+        },
     },
     {
         "slug": "drb_90_adas_liability",
@@ -2086,11 +2119,20 @@ async def run_one_query(
                 return summary
 
         # Phase 2b scope gate
+        # I-beatboth-fix-000 (#1171): thread per-question PICO/PCC scope
+        # overrides into the already-existing run_scope_gate(user_overrides=...)
+        # param (scope_gate.py:393, applied :457-459). Questions without a
+        # `scope_overrides` key pass None -> dict(None or {}) == {} (scope_gate.py:441)
+        # -> byte-identical to today for every other slug. Config-driven, no new env
+        # (LAW VI). This single call site covers BOTH live entry paths: the direct
+        # `run_honest_sweep_r3 --only` run and the Gate-B path (run_gate_b ->
+        # run_gate_b_query -> run_one_query), which share this one gate invocation.
         scope = run_scope_gate(
             research_question=q["question"],
             run_dir=run_dir,
             run_id=run_id,
             domain=q["domain"],
+            user_overrides=q.get("scope_overrides"),
         )
         protocol = scope.protocol.to_json_dict()
         _log(f"[scope]       sha256={scope.protocol_sha256[:16]}... "
diff --git a/tests/polaris_graph/test_scope_gate.py b/tests/polaris_graph/test_scope_gate.py
index cc9ea98a..a2b63fb0 100644
--- a/tests/polaris_graph/test_scope_gate.py
+++ b/tests/polaris_graph/test_scope_gate.py
@@ -307,3 +307,214 @@ def test_extract_pico_heuristic_drug_detection() -> None:
     pico3 = extract_pico_heuristic("What are pharmaceutical trends in 2025?")
     assert pico3["intervention"] is None  # no drug
     assert pico3["population"] is None
+
+
+# ─────────────────────────────────────────────────────────────────
+# I-beatboth-fix-000 (#1171) — CLINICAL-SCOPE false-rejection fix.
+#
+# The 3 clinical golden benchmark questions (drb_75 metal-ions-CVD,
+# drb_76 gut-microbiota-CRC, drb_78 parkinsons-DBS) are fully-scoped
+# lit-review questions whose review-style phrasing names no listed drug
+# and no listed demographic, so extract_pico_heuristic returns BOTH
+# population=None AND intervention=None and the gate hard-rejects them as
+# clinical_pico_unscoped (forensic baseline: outputs/vm_forensic/drb_7{5,6,8}_*/
+# protocol.json all show scope_decision=reject, $0, elapsed_s=0.1).
+#
+# The fix threads per-question PICO/PCC scope_overrides (defined in
+# SWEEP_QUERIES) into the already-existing run_scope_gate(user_overrides=...)
+# param. These tests read the REAL SWEEP_QUERIES overrides (NOT hardcoded
+# copies) so a typo in the live definitions fails the test rather than
+# silently shipping broken. SCOPING-ONLY: no verification gate is exercised.
+# ─────────────────────────────────────────────────────────────────
+
+_CLINICAL_GOLDEN_SLUGS = (
+    "drb_75_metal_ions_cvd",
+    "drb_76_gut_microbiota_crc",
+    "drb_78_parkinsons_dbs",
+)
+
+
+def _sweep_entry(slug: str) -> dict:
+    """Return the live SWEEP_QUERIES entry for `slug` (single source of truth)."""
+    import importlib
+
+    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
+    matches = [q for q in sweep.SWEEP_QUERIES if q.get("slug") == slug]
+    assert len(matches) == 1, (
+        f"slug {slug!r} must be registered exactly once in SWEEP_QUERIES "
+        f"(found {len(matches)})"
+    )
+    return matches[0]
+
+
+@pytest.mark.parametrize("slug", _CLINICAL_GOLDEN_SLUGS)
+def test_clinical_golden_question_proceeds_with_overrides(
+    slug: str, tmp_path: Path
+) -> None:
+    """Each of the 3 clinical golden questions now scope=PROCEED.
+
+    Reads the REAL question text + scope_overrides from SWEEP_QUERIES and
+    feeds them into run_scope_gate exactly as the live sweep call site does.
+    The same call WITHOUT overrides yields reject (proven by the regression
+    test below); WITH the registered overrides it must proceed with both
+    PICO anchors populated.
+    """
+    entry = _sweep_entry(slug)
+    overrides = entry.get("scope_overrides")
+    assert overrides, (
+        f"SWEEP_QUERIES entry {slug!r} must carry a non-empty scope_overrides "
+        f"dict for the clinical-scope fix"
+    )
+
+    result = run_scope_gate(
+        research_question=entry["question"],
+        run_dir=tmp_path / slug,
+        run_id=f"TEST_{slug}",
+        domain=entry["domain"],
+        user_overrides=overrides,
+    )
+    # The fix: reject -> proceed.
+    assert result.protocol.scope_decision == "proceed", (
+        f"{slug!r} must scope=proceed with overrides (was reject)"
+    )
+    assert result.protocol.scope_rejected is False
+    assert result.protocol.scope_rejection_code is None
+    # Both PICO anchors land (population/intervention lowercased per
+    # scope_gate.py:459 — assert non-None, not exact case).
+    assert result.protocol.population is not None
+    assert result.protocol.intervention is not None
+    # The author-supplied scope is recorded verbatim in the audit trail.
+    assert result.protocol.user_overrides == overrides
+
+
+@pytest.mark.parametrize("slug", _CLINICAL_GOLDEN_SLUGS)
+def test_clinical_golden_question_still_rejects_without_overrides(
+    slug: str, tmp_path: Path
+) -> None:
+    """Baseline confirmation: WITHOUT overrides the same question rejects.
+
+    Proves the overrides (not some other change) are what flips the verdict,
+    and that the regex extractor genuinely cannot scope these questions —
+    i.e. the fix is the override threading, not a softened gate.
+    """
+    entry = _sweep_entry(slug)
+    result = run_scope_gate(
+        research_question=entry["question"],
+        run_dir=tmp_path / f"{slug}_baseline",
+        run_id=f"TEST_{slug}_BASE",
+        domain=entry["domain"],
+        # No user_overrides -> the un-fixed behavior.
+    )
+    assert result.protocol.scope_decision == "reject"
+    assert result.protocol.scope_rejected is True
+    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"
+
+
+def test_genuinely_unscoped_clinical_still_rejects_discriminator(
+    tmp_path: Path,
+) -> None:
+    """DISCRIMINATOR: a genuinely contentless clinical question STILL rejects.
+
+    This is the guard that proves the fix did not just disable the gate. A
+    vague question with no scope_overrides must keep rejecting with
+    clinical_pico_unscoped (mirrors test_b100_scope_rejects_unscoped_clinical).
+    """
+    result = run_scope_gate(
+        research_question="Tell me about safety outcomes.",
+        run_dir=tmp_path / "unscoped",
+        run_id="TEST_UNSCOPED_DISCRIM",
+        domain="clinical",
+    )
+    assert result.protocol.scope_decision == "reject"
+    assert result.protocol.scope_rejected is True
+    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"
+
+
+def test_offtopic_question_without_overrides_still_rejects(
+    tmp_path: Path,
+) -> None:
+    """Off-topic / non-clinical-shaped clinical-domain query still rejects
+    when it carries no extractable PICO and no overrides."""
+    result = run_scope_gate(
+        research_question="What is the best espresso machine for a home kitchen?",
+        run_dir=tmp_path / "offtopic",
+        run_id="TEST_OFFTOPIC",
+        domain="clinical",
+    )
+    assert result.protocol.scope_decision == "reject"
+    assert result.protocol.scope_rejected is True
+    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"
+
+
+def test_non_clinical_slug_without_overrides_unchanged(tmp_path: Path) -> None:
+    """OFF-mode byte-identical: a question with NO scope_overrides passes
+    None to run_scope_gate (q.get returns None), which is dict(None or {}) == {}
+    — exactly today's path. drb_90 (policy) carries no overrides, so it must
+    behave identically with and without the (None) override argument."""
+    entry = _sweep_entry_safe("drb_90_adas_liability")
+    assert entry.get("scope_overrides") is None, (
+        "non-clinical slugs must NOT carry scope_overrides (off-mode unchanged)"
+    )
+    # Explicit None override == no override == byte-identical path.
+    r_none = run_scope_gate(
+        research_question=entry["question"],
+        run_dir=tmp_path / "policy_none",
+        run_id="TEST_POLICY_NONE",
+        domain=entry["domain"],
+        user_overrides=entry.get("scope_overrides"),  # None
+    )
+    r_absent = run_scope_gate(
+        research_question=entry["question"],
+        run_dir=tmp_path / "policy_absent",
+        run_id="TEST_POLICY_ABSENT",
+        domain=entry["domain"],
+    )
+    assert r_none.protocol.scope_decision == r_absent.protocol.scope_decision
+    assert r_none.protocol.user_overrides == r_absent.protocol.user_overrides == {}
+
+
+def _sweep_entry_safe(slug: str) -> dict:
+    import importlib
+
+    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
+    matches = [q for q in sweep.SWEEP_QUERIES if q.get("slug") == slug]
+    assert matches, f"slug {slug!r} not found in SWEEP_QUERIES"
+    return matches[0]
+
+
+def test_live_call_site_threads_scope_overrides() -> None:
+    """WIRING (source/AST scan): the live sweep call site passes
+    user_overrides=q.get("scope_overrides") into run_scope_gate.
+
+    Mirrors test_b100_orchestrator_aborts_before_retrieval_on_reject's
+    source-scan pattern: proves the override threading is wired so a future
+    refactor that drops the kwarg fails this test loudly.
+    """
+    import inspect
+    import scripts.run_honest_sweep_r3 as sweep
+
+    source = inspect.getsource(sweep.run_one_query)
+    call_idx = source.find("scope = run_scope_gate(")
+    assert call_idx > 0, "expected the run_scope_gate call in run_one_query"
+    # Bound the search to the call's argument block.
+    after = source[call_idx:call_idx + 600]
+    assert 'user_overrides=q.get("scope_overrides")' in after, (
+        "run_scope_gate call must thread user_overrides=q.get('scope_overrides') "
+        "so per-question PICO/PCC overrides reach the gate"
+    )
+
+
+def test_gate_b_loader_carries_scope_overrides_through() -> None:
+    """GATE-B ACTIVATION: the Gate-B loader (load_locked_questions) returns the
+    live SWEEP_QUERIES entry, so the clinical slugs' scope_overrides reach
+    run_one_query on the Gate-B path (run_gate_b -> run_gate_b_query ->
+    run_one_query -> the shared run_scope_gate call site). Offline, no network."""
+    from scripts.dr_benchmark.run_gate_b import load_locked_questions
+
+    for slug in _CLINICAL_GOLDEN_SLUGS:
+        entry = load_locked_questions((slug,))[0]
+        assert entry["slug"] == slug
+        assert entry.get("scope_overrides"), (
+            f"Gate-B loader must surface scope_overrides for {slug!r} so the "
+            f"4-role benchmark path scopes=proceed instead of abort_scope_rejected"
+        )
```

---

## SUPPORTING SOURCE CONTEXT (unchanged by this diff — for VERIFY (a)/(b)/(c))

scope_gate.py override merge + clinical hard-reject (NOT modified by this diff):

```python
    overrides = dict(user_overrides or {})

    # 1. Load template. If domain is rejected, skip the template load
    # (it would raise) and use an empty template; the protocol document
    # still needs to be assembled so the orchestrator can emit an
    # abort manifest.
    if scope_rejected:
        template = {}
        template_path_rel = f"config/scope_templates/<rejected:{domain}>.yaml"
    else:
        template = load_scope_template(domain)
        template_path_rel = f"config/scope_templates/{domain}.yaml"

    # 2. PICO heuristic extraction
    pico = extract_pico_heuristic(research_question)
    # Overrides win
    for key in ("population", "intervention", "comparator", "outcome"):
        if key in overrides and overrides[key]:
            pico[key] = str(overrides[key]).lower()
    if scope_rejected:
        notes.extend(scope_reasons)
    elif domain == "clinical":
        pico_missing: list[str] = []
        if not pico["population"]:
            notes.append(
                "PICO population could not be extracted from the research "
                "question. User should confirm the target population."
            )
            pico_missing.append("population")
        if not pico["intervention"]:
            notes.append(
                "PICO intervention could not be extracted. User should "
                "confirm the drug / procedure under study."
            )
            pico_missing.append("intervention")
        if len(pico_missing) == 2:
            # Both anchors missing: retrieval would be poorly scoped.
            # Hard reject rather than flag-only.
            scope_decision = "reject"
            scope_rejected = True
            scope_rejection_code = "clinical_pico_unscoped"
            scope_reasons.append(
                "Clinical question has neither extractable population nor "
                "intervention after overrides; retrieval would be too broad "
                "to produce a meaningful evidence corpus."
            )
            needs_review = False
        elif pico_missing:
            # One anchor missing: flag for review but still proceed.
            scope_decision = "review"
            needs_review = True

```

Diff name-only (proves NO verification-gate file touched):
```
scripts/run_honest_sweep_r3.py
tests/polaris_graph/test_scope_gate.py
```
