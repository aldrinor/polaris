HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF gate — I-meta-005 Phase 1 (#985): research planner + archetype sections

Reviewing the CODE DIFF vs the APPROVED brief (.codex/I-meta-005-phase-1/brief.md, Codex APPROVE iter5) +
build_spec.md. This verdict AUTHORIZES THE MERGE (operator governance 2026-05-31). Output §8.3.9 YAML first.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## VERIFY (read the actual diff + workspace, not the summary):
1. OFF byte-identity: PG_USE_RESEARCH_PLANNER off → unchanged decompose_question + _ALLOWED_SECTIONS path;
   additive SectionPlan.archetype/SectionResult.archetype default "" never leak into a written OFF artifact
   (only `[p.title for p in multi.outline]` is serialized; no asdict of the section dataclasses anywhere).
2. Field-agnostic (operator HARD lock): NO clinical literal / `if domain ==` as a control VALUE on the
   on-path. On-mode: domain expanders fed empty, domain=None bypasses run_domain_backends (guard
   live_retriever.py:1795), R-6 {domain}.yaml disabled (run_honest_sweep_r3.py:1991). Zero clinical labels
   on physics/ag-policy (P1-4).
3. Spend-free: plan_research takes an injected planner_llm; no OpenRouterClient/httpx in the module; smoke
   tripwires OpenRouterClient.__init__ (P1-11).
4. Archetype routing: on-mode M-44/M-47 resolve archetype from SectionPlan→SectionResult (not a clinical
   title literal); preserved through all copy/rebuild sites; off-mode title routing byte-identical.
5. on-mode outline is LLM-FREE (_assign_evidence_to_planned_outline assigns retrieved ev_ids to the pinned
   plan) — verify it cannot invent sections and is genuinely spend-free.

## THREE DEVIATIONS — RULE ON EACH (honest disclosure):
A. **clinical.yaml advisory is SCAFFOLDED BUT UNWIRED.** select_advisory_prompt_text + clinical.yaml +
   _registry.yaml exist and are literal-free, but the selector returns '' for ALL claim_types (registry
   by_claim_type:{}) AND its output is NOT appended into _call_section. Reason: claim_type alone cannot
   identify a clinical question ('empirical' is shared by physics/battery; CLAIM_TYPES has no 'clinical'),
   so an empirical→clinical trigger would wrongly clinical-ize every empirical question (violating §2.3).
   The real entity-category clinical trigger + the prompt append are deferred to a later phase. IS THIS
   ACCEPTABLE PHASE-1 SCOPE, or a blocker? (The brief §2.3 described the advisory append; the build
   delivered the scaffold + honest no-op rather than a wrong clinical trigger.)
B. **Production planner Writer wiring not smoke-exercised.** _planner_llm (run_honest_sweep_r3.py:1665-1701)
   drives async OpenRouterClient.generate via ThreadPoolExecutor + asyncio.run (run_one_query is already in
   an event loop). Spend-free smoke fakes the planner, so this thread-offload is NOT exercised; it needs a
   live on-mode run before the Gate-A flip. Acceptable to defer to Gate-A, or must it be covered now?
C. **P2 note A satisfied structurally.** dataclasses.asdict includes every field, so the OFF wall is that
   NO production serializer asdict-s MultiSectionResult/SectionResult/SectionPlan (repo-grep confirmed);
   P1-1 pins the title-only manifest projection. Verify this is a sound OFF byte-identity guarantee.

## SMOKE: 18/18 planner (P1-1..P1-17 + advisory selector) + 22 phase-0b + 92 generator regression = all green.
## ARCHITECT (Claude): CLEAN — off-byte-identity / field-agnostic / spend-free / archetype-routing all verified by code-read.

APPROVE iff OFF is byte-identical, the field-agnostic lock holds, the build is spend-free, archetype
routing is correct, and deviations A/B/C are acceptable Phase-1 scope (else name the blocker). This is the
build contract; on APPROVE the merge proceeds.

--- FULL DIFF BELOW ---
```diff
diff --git a/config/section_prompts/_registry.yaml b/config/section_prompts/_registry.yaml
new file mode 100644
index 00000000..9e037c7e
--- /dev/null
+++ b/config/section_prompts/_registry.yaml
@@ -0,0 +1,28 @@
+# Advisory prompt-text family registry — I-meta-005 Phase 1 (#985, brief §2.3).
+#
+# Maps a field-invariant claim_type (from planning.research_planner.CLAIM_TYPES)
+# to an advisory prompt-text file in this directory. The on-path selector
+# (`select_advisory_prompt_text` in multi_section_generator) loads THIS file
+# and looks up the frame's claim_type — there is NO `if domain == "clinical"`
+# literal in Python on the on-path. Adding a new prose family is a config edit,
+# not a code edit (LAW VI).
+#
+# A claim_type with no entry selects no advisory text (empty append); the
+# archetype outline / parser / fallback / routing are byte-identical regardless
+# of which (if any) advisory file is appended.
+
+# claim_type -> advisory prompt-text file (relative to this directory).
+#
+# Phase 1 intentionally maps NOTHING here. `claim_type` alone cannot identify a
+# clinical question: `empirical` is the generic measured-effect shape that a
+# physics, battery, or epidemiology question shares — mapping `empirical ->
+# clinical.yaml` would wrongly give every empirical question clinical writing
+# guidance, contradicting brief §2.3 ("when claim_type/entities read clinical")
+# and the field-agnostic principle. `CLAIM_TYPES` has no "clinical" value, so a
+# correct clinical trigger needs an ENTITY-category signal (a later phase). The
+# clinical.yaml family is therefore present and selectable but UNMAPPED in
+# Phase 1; the registry default is null (no advisory append).
+by_claim_type: {}
+
+# Default when a claim_type has no specific mapping: no advisory append.
+default: null
diff --git a/config/section_prompts/clinical.yaml b/config/section_prompts/clinical.yaml
new file mode 100644
index 00000000..6908151f
--- /dev/null
+++ b/config/section_prompts/clinical.yaml
@@ -0,0 +1,39 @@
+# Advisory section-writing guidance — CLINICAL prose family.
+# I-meta-005 Phase 1 (#985, brief §2.3).
+#
+# THIS IS PROMPT-TEXT ONLY. It is advisory writing guidance appended to the
+# per-section prompt to enrich prose when the question's frame reads clinical
+# (claim_type/entities). It is NOT a control branch and does NOT change
+# routing, archetypes, section structure, the archetype outline prompt, the
+# parser, tag-validation, or the fallback. Selecting this file vs another
+# prompt-text family produces byte-identical control flow — only the appended
+# advisory prose differs (see the field-agnostic selector in
+# multi_section_generator: `select_advisory_prompt_text`).
+#
+# The selector is config-driven (LAW VI): a claim_type -> prompt-text-file
+# registry. "clinical" here is ONE generalizable family entry, not a literal
+# control value in Python on the on-path.
+
+family: clinical
+description: >-
+  Advisory writing guidance for questions whose frame reads clinical
+  (interventions, populations, endpoints, trials). Appended to the section
+  prompt as extra prose guidance; never a routing control.
+
+advisory_prompt_text: |
+  CLINICAL WRITING GUIDANCE (advisory — does not change which evidence you may
+  cite or how the section is structured):
+  - When you report an efficacy or safety estimate, give the population, the
+    comparator/control arm, the endpoint, the timepoint, and the effect size
+    with its uncertainty (CI, SD, or p-value) when the cited evidence carries
+    them. Prefer the primary trial publication over a press release covering
+    the same finding.
+  - Attribute a regulatory statement to the specific jurisdiction whose source
+    supports it; do not collapse distinct frameworks into "both agencies" or
+    "regulators generally" unless a citation from each is in the same sentence.
+  - When naming a specific study, cohort, or trial, frame it with at least
+    three of: sample size, baseline value, comparator arm, dose, primary
+    endpoint, timepoint. If the cited evidence cannot supply three, phrase the
+    sentence generically rather than attaching a study short-name to a thin
+    claim.
+  - Keep numeric values verbatim from the evidence; do not round.
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 76156e97..239a5d0a 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1626,6 +1626,78 @@ async def run_one_query(
         _max_s2 = int(os.getenv("PG_SWEEP_MAX_S2", "12"))
         _fetch_cap = int(os.getenv("PG_SWEEP_FETCH_CAP", "40"))
 
+        # I-meta-005 Phase 1 (#985): field-agnostic research planner (shadow
+        # build, default OFF). When PG_USE_RESEARCH_PLANNER is on, the planner
+        # produces the frame + faceted sub-queries + archetype outline; the
+        # plan is SHA-pinned BEFORE retrieval (gap #19 extension) and its
+        # sub-queries are the ONLY non-anchor query source — the legacy
+        # domain-keyed expanders (M-28/M-35/trial-DOI/hand-authored) are NOT
+        # invoked, the domain_backends router is bypassed (domain=None), and
+        # R-6 {domain}.yaml completeness expansion is disabled. OFF: every
+        # legacy path runs byte-identically.
+        _use_research_planner = (
+            os.getenv("PG_USE_RESEARCH_PLANNER", "0").strip()
+            in ("1", "true", "True")
+        )
+        _research_plan = None
+        _planner_protocol = None
+        if _use_research_planner:
+            from src.polaris_graph.planning.research_planner import (
+                plan_research,
+                plan_sha256,
+                serialize_plan_canonical,
+            )
+            from src.polaris_graph.llm.openrouter_client import (
+                OpenRouterClient,
+                PG_GENERATOR_MODEL,
+            )
+
+            def _planner_llm(prompt: str) -> str:
+                # Production Writer call. Build + smoke NEVER reach this path
+                # (the planner callable is injected/faked there). One Writer
+                # call (plus at most one bounded retry inside plan_research).
+                #
+                # `run_one_query` is async — the sweep event loop is already
+                # running here — so the coroutine is driven on a SEPARATE
+                # thread with its own loop (thread-safe; never touches the
+                # running loop, which `run_until_complete` would crash on).
+                import asyncio as _asyncio
+                import concurrent.futures as _futures
+
+                async def _run() -> str:
+                    _client = OpenRouterClient(model=PG_GENERATOR_MODEL)
+                    try:
+                        _resp = await _client.generate(
+                            prompt=prompt, max_tokens=2000, temperature=0.2,
+                        )
+                        return (_resp.content or "").strip()
+                    finally:
+                        if hasattr(_client, "close"):
+                            try:
+                                await _client.close()
+                            except Exception:
+                                pass
+
+                with _futures.ThreadPoolExecutor(max_workers=1) as _pool:
+                    return _pool.submit(_asyncio.run, _run()).result()
+
+            _research_plan = plan_research(
+                q["question"], planner_llm=_planner_llm,
+            )
+            # Pre-register + SHA-pin the plan BEFORE retrieval (gap #19).
+            _plan_canonical = serialize_plan_canonical(_research_plan)
+            _plan_path = run_dir / "research_plan.json"
+            _plan_path.write_text(_plan_canonical + "\n", encoding="utf-8")
+            _plan_sha = plan_sha256(_research_plan)
+            _log(f"[planner]     research_plan pinned sha256={_plan_sha[:12]} "
+                 f"sub_queries={len(_research_plan.sub_queries)} "
+                 f"outline={len(_research_plan.outline)}")
+            # Frame-derived anchor protocol so planner sub-queries validate
+            # against the frame's OWN tokens (brief §2.4 validator adapter).
+            _planner_protocol = _research_plan.frame.to_anchor_protocol(
+                q["question"]
+            )
+
         # M-28 Fix #1 (2026-04-20): regulatory-anchor expansion. Loads
         # the scope template for this domain and — if the template has
         # a `regulatory_anchors` list — emits one extra amplified query
@@ -1684,12 +1756,25 @@ async def run_one_query(
         from src.polaris_graph.retrieval.query_decomposer import (
             build_amplified_query_list,
         )
-        _amplified_effective = build_amplified_query_list(
-            hand_authored=list(q.get("amplified", [])),
-            decomposed=_decomposed,
-            regulatory=_reg_queries,
-            trial=_trial_queries,
-        )
+        if _use_research_planner and _research_plan is not None:
+            # ON-mode: the planner's faceted sub-queries are the ONLY
+            # non-anchor query source. The legacy domain-keyed expanders are
+            # NOT invoked (regulatory/trial/hand_authored all empty); the
+            # planner's facets ARE the field-agnostic regulatory/primary-
+            # evidence expansion (brief §2.4).
+            _amplified_effective = build_amplified_query_list(
+                hand_authored=[],
+                decomposed=list(_research_plan.sub_queries),
+                regulatory=[],
+                trial=[],
+            )
+        else:
+            _amplified_effective = build_amplified_query_list(
+                hand_authored=list(q.get("amplified", [])),
+                decomposed=_decomposed,
+                regulatory=_reg_queries,
+                trial=_trial_queries,
+            )
 
         # I-bug-776 (#817) layer-4 (Codex decision b): direct primary-trial DOI
         # seed candidates. Search-expansion (M-35 above) does not surface the
@@ -1705,17 +1790,31 @@ async def run_one_query(
                  f"direct candidates (slug={q['slug']})")
 
         t0 = time.time()
+        # I-meta-005 Phase 1 (#985): ON-mode bypasses the two live-path domain
+        # routers (brief §2.4) — `domain=None` skips the domain_backends
+        # per-domain `if domain ==` candidate router (live_retriever:1795
+        # guards `if domain and not seed_only`), and the frame-derived protocol
+        # replaces the clinical PICO protocol so planner sub-queries validate
+        # against the frame's own tokens. No trial-DOI seeds on-mode. OFF: the
+        # legacy domain + PICO protocol + DOI seeds run byte-identically.
+        _retrieval_domain = None if _use_research_planner else q["domain"]
+        _retrieval_protocol = (
+            _planner_protocol
+            if (_use_research_planner and _planner_protocol is not None)
+            else protocol
+        )
+        _retrieval_seed_urls = [] if _use_research_planner else _trial_doi_seeds
         retrieval = run_live_retrieval(
             research_question=q["question"],
             amplified_queries=_amplified_effective,
-            protocol=protocol,
+            protocol=_retrieval_protocol,
             max_serper=_max_serper,
             max_s2=_max_s2,
             fetch_cap=_fetch_cap,
             enable_openalex_enrich=True,
             enable_prefetch_filter=False,
-            domain=q["domain"],   # R-6 Gap-2 domain backends
-            seed_urls=_trial_doi_seeds,   # #817 layer-4 direct DOI candidates
+            domain=_retrieval_domain,   # R-6 Gap-2 domain backends (None on-mode)
+            seed_urls=_retrieval_seed_urls,   # #817 layer-4 DOI candidates (off-mode only)
         )
         dt = time.time() - t0
         _log(f"[retrieval]   pre_filter={retrieval.total_candidates_pre_filter}, "
@@ -1882,7 +1981,15 @@ async def run_one_query(
         # R-6 Gap-3: gap-triggered expansion. If uncovered topics and
         # we have enable_expansion, fire another retrieval pass with
         # the expansion queries, then re-classify + re-check.
-        enable_expansion = os.getenv("PG_R6_ENABLE_EXPANSION", "1") == "1"
+        # I-meta-005 Phase 1 (#985): ON-mode disables R-6 {domain}.yaml
+        # completeness expansion (brief §2.4) — it is a `{domain}.yaml` router
+        # forbidden on the field-agnostic on-path. The completeness CHECK still
+        # runs for telemetry, but no domain-keyed expand_queries are fired into
+        # retrieval. OFF: R-6 expansion runs byte-identically.
+        enable_expansion = (
+            os.getenv("PG_R6_ENABLE_EXPANSION", "1") == "1"
+            and not _use_research_planner
+        )
         if (enable_expansion and completeness.expand_queries
                 and completeness.total_uncovered > 0):
             _log(f"[expansion]   triggering {len(completeness.expand_queries)} "
@@ -2650,6 +2757,13 @@ async def run_one_query(
             m50_skip_anchors=_compute_m50_skip_anchors(
                 _phase2_contract_plans, _primary_anchors,
             ) if _phase2_contract_plans else None,
+            # I-meta-005 Phase 1 (#985): pre-registered ResearchPlan. None in
+            # OFF mode (legacy `_call_outline` / `_ALLOWED_SECTIONS` path runs
+            # byte-identically). When set, the generator FIXES the section
+            # structure to `research_plan.outline`, assigns retrieved evidence
+            # to those sections post-retrieval, and routes M-44/M-47 on the
+            # archetype tag (not a clinical title).
+            research_plan=_research_plan,
             )
         finally:
             _pathb.reset_role(_pathb_gen_tok)
@@ -3428,6 +3542,19 @@ async def run_one_query(
             "fact_dedup": getattr(multi, "fact_dedup_telemetry", {}),
         }
 
+        # I-meta-005 Phase 1 (#985, P1-8): record the SHA-pinned ResearchPlan
+        # in the manifest (gap #19 extension). ON-mode only — the key is absent
+        # in OFF, preserving the legacy manifest shape byte-for-byte.
+        if _use_research_planner and _research_plan is not None:
+            manifest["research_plan"] = {
+                "plan_path": str((run_dir / "research_plan.json").name),
+                "plan_sha256": _plan_sha,
+                "sub_query_count": len(_research_plan.sub_queries),
+                "outline_archetypes": [
+                    item.archetype for item in _research_plan.outline
+                ],
+            }
+
         # I-meta-002 sub-PR-6: GUARDED 4-role evaluation seam (default OFF, NO spend).
         # Activates ONLY when an explicit RoleTransport is INJECTED (four_role_transport)
         # AND PG_FOUR_ROLE_MODE is enabled. There is NO default real transport: the live
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index ab551e34..04b311ad 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -56,6 +56,10 @@ logger = logging.getLogger("polaris_graph.multi_section")
 
 # Allowed section labels. The outline call is constrained to pick from
 # this list; prevents the model from inventing off-topic section titles.
+# OFF-PATH ONLY (legacy clinical path, retained byte-identically for the true
+# dual path — I-meta-005 Phase 1 #985). On the field-agnostic on-path the
+# planner-driven archetype outline replaces this list; selection happens at
+# the caller via `PG_USE_RESEARCH_PLANNER`.
 _ALLOWED_SECTIONS: list[str] = [
     "Efficacy",
     "Safety",
@@ -68,11 +72,88 @@ _ALLOWED_SECTIONS: list[str] = [
 ]
 
 
+# Field-invariant section archetypes (I-meta-005 Phase 1 #985, brief §2.3).
+# These TAGS are the on-path control-flow key — a non-clinical question gets a
+# question-specific TITLE plus one of these tags, and on-mode audit routing
+# (M-44 / M-47) consults the tag, never a clinical title literal. The set is
+# domain-agnostic: a housing, physics, or trade question maps cleanly onto it.
+SECTION_ARCHETYPES: list[str] = [
+    "Background",
+    "Mechanism",
+    "Quantitative-Comparison",
+    "Cost-Economics",
+    "Risk",
+    "Jurisdiction",
+    "Stakeholders",
+    "Scenarios",
+    "Decision",
+    "Uncertainty",
+    "Methodology",
+    "Limitations",
+]
+
+
+# I-meta-005 Phase 1 (#985, brief §2.3): config-driven advisory prompt-text
+# selector for the on-path. A frame's field-invariant `claim_type` selects an
+# advisory prose family from the `config/section_prompts/_registry.yaml`
+# mapping. This is the ONLY clinical-prose seam, and it is NOT a control value:
+# the registry is config (LAW VI), the appended text is advisory-only, and the
+# archetype outline / parser / fallback / routing are byte-identical regardless
+# of which (if any) family is appended. There is no `if claim_type ==
+# "clinical"` literal in this code.
+_SECTION_PROMPTS_REGISTRY_PATH = os.getenv(
+    "PG_SECTION_PROMPTS_REGISTRY",
+    os.path.join("config", "section_prompts", "_registry.yaml"),
+)
+
+
+def select_advisory_prompt_text(claim_type: str) -> str:
+    """Return the advisory prompt-text for a frame's `claim_type`, or "" when
+    no family is registered. Pure config lookup — no clinical literal as a
+    control value; fail-soft to "" when the registry is absent (advisory text
+    is enrichment, not a gate)."""
+    import yaml  # local import: advisory enrichment, keep module surface lean
+
+    registry_path = _SECTION_PROMPTS_REGISTRY_PATH
+    if not os.path.isfile(registry_path):
+        return ""
+    try:
+        with open(registry_path, "r", encoding="utf-8") as fh:
+            registry = yaml.safe_load(fh) or {}
+    except (OSError, yaml.YAMLError) as exc:
+        logger.warning(
+            "[multi_section] advisory prompt registry load failed: %s", exc,
+        )
+        return ""
+    by_claim_type = registry.get("by_claim_type") or {}
+    key = (claim_type or "").strip().lower()
+    filename = by_claim_type.get(key) or registry.get("default")
+    if not filename:
+        return ""
+    family_path = os.path.join(os.path.dirname(registry_path), str(filename))
+    if not os.path.isfile(family_path):
+        return ""
+    try:
+        with open(family_path, "r", encoding="utf-8") as fh:
+            family = yaml.safe_load(fh) or {}
+    except (OSError, yaml.YAMLError):
+        return ""
+    return str(family.get("advisory_prompt_text", "") or "")
+
+
 @dataclass
 class SectionPlan:
-    title: str            # one of _ALLOWED_SECTIONS
+    title: str            # one of _ALLOWED_SECTIONS (off-mode) or a
+                          # question-specific heading (on-mode)
     focus: str            # one-sentence focus statement for the prompt
     ev_ids: list[str]     # evidence rows the section should draw from
+    # I-meta-005 Phase 1 (#985): field-invariant archetype tag. Default "" so
+    # OFF mode is unchanged — no existing serialization path emits this field
+    # in OFF (repo-wide check: SectionPlan is never `asdict`-ed; the manifest
+    # uses `[p.title for p in multi.outline]`). On-mode carries the planner's
+    # tag here so M-44/M-47 route on archetype, not on a clinical title.
+    # Appended LAST in the field list to preserve positional construction.
+    archetype: str = ""
 
 
 @dataclass
@@ -133,6 +214,13 @@ class SectionResult:
     refusal_count: int = 0
     soft_mismatch_count: int = 0
     atom_validation_mode: str = "off"
+    # I-meta-005 Phase 1 (#985, Codex P2 build-note B): field-invariant
+    # archetype tag carried from the originating SectionPlan so the on-mode
+    # post-generation M-44/M-47 checks resolve the archetype from the plan
+    # (not from a clinical title literal). Default "" so OFF is unchanged —
+    # SectionResult is never `asdict`-ed in any OFF artifact path. Appended
+    # LAST to preserve positional construction at the existing call sites.
+    archetype: str = ""
 
 
 @dataclass
@@ -485,6 +573,91 @@ def _build_deterministic_fallback_outline(
     return plans
 
 
+# ─────────────────────────────────────────────────────────────────────────────
+# I-meta-005 Phase 1 (#985): ON-MODE archetype outline (field-agnostic).
+#
+# This is the dual-path's ON branch (brief §2.3 + §2.5). It is LLM-FREE: the
+# section STRUCTURE (titles + archetype tags + count) is FIXED by the
+# pre-retrieval, SHA-pinned `ResearchPlan.outline`; this code only ASSIGNS
+# retrieved evidence rows to those pre-declared sections (populate `ev_ids`).
+# It constructs NO OpenRouterClient and makes NO LLM call — so on-mode outline
+# is spend-free (P1-11) and the handoff is deterministically testable (P1-12).
+# OFF mode never reaches here; the legacy `_call_outline` / `_parse_outline` /
+# `_build_deterministic_fallback_outline` run byte-identically.
+# ─────────────────────────────────────────────────────────────────────────────
+
+# Archetype-driven deterministic fallback titles (field-invariant). Used only
+# when an on-mode plan outline is empty AND we still need a minimal structure.
+_ARCHETYPE_FALLBACK: list[tuple[str, str]] = [
+    ("Background", "Background and Context"),
+    ("Quantitative-Comparison", "Quantitative Comparison"),
+    ("Decision", "Decision Synthesis"),
+]
+
+
+def _assign_evidence_to_planned_outline(
+    planned_outline: list[Any],
+    evidence: list[dict[str, Any]],
+    *,
+    max_ev_per_section: int = 30,
+) -> list[SectionPlan]:
+    """Assign retrieved evidence rows to the planner's pre-declared sections
+    (brief §2.5). The titles + archetype tags + section COUNT come from
+    `planned_outline` (each item exposes `.archetype`, `.title`, and optionally
+    `.evidence_target`); this function only distributes `ev_ids` round-robin so
+    every section draws from the retrieved pool. Pure / no-LLM / no-network.
+
+    `planned_outline` items are `planning.SectionOutlineItem` instances (or any
+    object with `.archetype` / `.title` attributes). Returns on-mode
+    `SectionPlan`s carrying the question-specific title + archetype tag.
+    """
+    ev_ids = [ev.get("evidence_id", "") for ev in evidence]
+    ev_ids = [e for e in ev_ids if e]
+    n_sections = len(planned_outline)
+    plans: list[SectionPlan] = []
+    for i, item in enumerate(planned_outline):
+        archetype = getattr(item, "archetype", "") or ""
+        title = getattr(item, "title", "") or archetype or f"Section {i + 1}"
+        target = int(getattr(item, "evidence_target", 0) or 0)
+        # Round-robin slice for this section, then honor the per-section
+        # evidence target as an upper cap (falls back to the global cap).
+        section_ev = ev_ids[i::n_sections] if n_sections else []
+        cap = target if target > 0 else max_ev_per_section
+        cap = min(cap, max_ev_per_section)
+        section_ev = section_ev[:cap]
+        plans.append(SectionPlan(
+            title=title,
+            focus=title,
+            ev_ids=section_ev,
+            archetype=archetype,
+        ))
+    return plans
+
+
+def _build_archetype_fallback_outline(
+    evidence: list[dict[str, Any]],
+) -> list[SectionPlan]:
+    """On-mode deterministic fallback (brief §2.3): when the planner outline is
+    unusable, build a minimal archetype-driven structure (Background +
+    Quantitative-Comparison + Decision) over the retrieved evidence. Field-
+    invariant — contains no clinical title literal. Returns [] when evidence is
+    too thin to populate the three sections."""
+    ev_ids = [ev.get("evidence_id", "") for ev in evidence]
+    ev_ids = [e for e in ev_ids if e]
+    if len(set(ev_ids)) < 6:
+        return []
+    plans: list[SectionPlan] = []
+    n = len(_ARCHETYPE_FALLBACK)
+    for i, (archetype, title) in enumerate(_ARCHETYPE_FALLBACK):
+        section_ev = ev_ids[i::n][:30]
+        if len(section_ev) < 2:
+            return []
+        plans.append(SectionPlan(
+            title=title, focus=title, ev_ids=section_ev, archetype=archetype,
+        ))
+    return plans
+
+
 async def _call_outline(
     research_question: str,
     evidence: list[dict[str, Any]],
@@ -1445,6 +1618,9 @@ async def _run_section(
             sentences_verified=0, sentences_dropped=0,
             regen_attempted=False, dropped_due_to_failure=True,
             error="no_evidence_in_pool",
+            # I-meta-005 Phase 1 (#985, P2 note B): carry the plan's archetype
+            # onto the result so on-mode audit routing keys on the tag.
+            archetype=getattr(section, "archetype", ""),
         )
 
     total_in_tok = 0
@@ -1641,6 +1817,9 @@ async def _run_section(
         # the orchestrator's final-remap-hook validator uses the same
         # numbering V4 Pro saw in the prompt.
         atom_catalog=dict(section_atom_catalog),
+        # I-meta-005 Phase 1 (#985, P2 note B): carry the plan's archetype
+        # onto the result so on-mode M-44/M-47 route on the tag, not title.
+        archetype=getattr(section, "archetype", ""),
     )
 
 
@@ -2642,6 +2821,42 @@ def _m44_section_is_primary_eligible(section_title: str) -> bool:
     return any(tok in t for tok in _M44_WEIGHT_TOKENS)
 
 
+# I-meta-005 Phase 1 (#985, P2 note B): on-mode archetype-keyed routing for the
+# post-generation primary-trial validator. The archetypes that carry
+# quantitative empirical claims (where named-study same-sentence citation
+# matters) are field-invariant tags — NOT clinical title literals — so the
+# zero-clinical-literal guard (P1-10) whitelists them.
+_M44_PRIMARY_ELIGIBLE_ARCHETYPES: frozenset[str] = frozenset({
+    "Quantitative-Comparison",
+    "Risk",
+    "Mechanism",
+})
+# The archetype that triggers the M-47 quantitative-extraction validator.
+_M47_ARCHETYPE: str = "Mechanism"
+
+
+def _section_is_primary_eligible(
+    *, title: str, archetype: str, use_archetype: bool,
+) -> bool:
+    """Dual-path primary-eligibility check (P2 note B). ON-mode keys on the
+    field-invariant archetype tag; OFF-mode keys on the legacy title (byte-
+    identical to today)."""
+    if use_archetype:
+        return (archetype or "").strip() in _M44_PRIMARY_ELIGIBLE_ARCHETYPES
+    return _m44_section_is_primary_eligible(title)
+
+
+def _section_is_mechanism(
+    *, title: str, archetype: str, use_archetype: bool,
+) -> bool:
+    """Dual-path Mechanism check for the M-47 validator (P2 note B). ON-mode
+    keys on `archetype == "Mechanism"`; OFF-mode keys on the legacy
+    `title.lower() == "mechanism"` (byte-identical to today)."""
+    if use_archetype:
+        return (archetype or "").strip() == _M47_ARCHETYPE
+    return (title or "").lower() == "mechanism"
+
+
 def _m53_compute_primary_custody_log(
     primary_trial_anchors: list[str] | None,
     live_corpus: list[dict[str, Any]] | None,
@@ -3079,6 +3294,9 @@ def _m44_inject_primaries_into_outline(
             # Pass through unchanged.
             updated.append(SectionPlan(
                 title=plan.title, focus=plan.focus, ev_ids=new_ev_ids,
+                # I-meta-005 Phase 1 (#985, P1-13): preserve archetype on
+                # rebuild so on-mode routing never re-leaks to title.
+                archetype=getattr(plan, "archetype", ""),
             ))
             continue
 
@@ -3125,6 +3343,8 @@ def _m44_inject_primaries_into_outline(
 
         updated.append(SectionPlan(
             title=plan.title, focus=plan.focus, ev_ids=new_ev_ids,
+            # I-meta-005 Phase 1 (#985, P1-13): preserve archetype on rebuild.
+            archetype=getattr(plan, "archetype", ""),
         ))
     return updated, log
 
@@ -3664,6 +3884,14 @@ async def generate_multi_section_report(
     # sections (Contradictions, Limitations) if any. When empty
     # or None, Phase-1 or pre-V30 behavior (legacy outline only).
     v30_contract_plans: list[Any] | None = None,
+    # I-meta-005 Phase 1 (#985): pre-registered, SHA-pinned ResearchPlan from
+    # the field-agnostic planner. When None (default) the legacy LLM outline
+    # path (`_call_outline` / `_ALLOWED_SECTIONS`) runs BYTE-IDENTICALLY (OFF
+    # dual path). When provided, the section STRUCTURE (titles + archetype
+    # tags + count) is FIXED by `research_plan.outline` and this function only
+    # ASSIGNS retrieved evidence to those sections (no second LLM outline
+    # call). Routing of M-44/M-47 then keys on archetype, not title.
+    research_plan: Any | None = None,
 ) -> MultiSectionResult:
     """Three-stage multi-section generation.
 
@@ -3681,22 +3909,52 @@ async def generate_multi_section_report(
     gen_model = model or PG_GENERATOR_MODEL
 
     # Stage 1: outline
-    outline_parse, retry_attempted, outline_in_tok, outline_out_tok = \
-        await _call_outline(
-            research_question, evidence, gen_model,
-            outline_temperature, outline_max_tokens,
-        )
-    plans = outline_parse.plans
-    outline_ok = outline_parse.ok
-    outline_reason_codes = list(outline_parse.reason_codes)
-    outline_fallback_used = False
+    # I-meta-005 Phase 1 (#985): TRUE dual path at the OUTLINE seam only — the
+    # rest of the body (section generation, M-44/M-47, assembly) is shared and
+    # routes on `research_plan is not None`. ON branch: the section structure
+    # is FIXED by `research_plan.outline` and we ASSIGN retrieved evidence to
+    # those pre-declared sections with NO LLM outline call (spend-free,
+    # P1-11/P1-12). OFF branch (`research_plan is None`): the legacy
+    # `_call_outline` path runs BYTE-IDENTICALLY (P1-1).
+    if research_plan is not None:
+        retry_attempted = False
+        outline_in_tok = 0
+        outline_out_tok = 0
+        planned_outline = list(getattr(research_plan, "outline", []) or [])
+        plans = _assign_evidence_to_planned_outline(planned_outline, evidence)
+        outline_ok = bool(plans)
+        outline_reason_codes = [] if plans else ["planner_outline_empty"]
+        outline_fallback_used = False
+        if not plans:
+            logger.warning(
+                "[multi_section] on-mode planner outline empty; using "
+                "archetype-driven deterministic fallback",
+            )
+            fallback_plans = _build_archetype_fallback_outline(evidence)
+            if fallback_plans:
+                plans = fallback_plans
+                outline_fallback_used = True
+                if not outline_reason_codes:
+                    outline_reason_codes = ["planner_outline_empty"]
+    else:
+        outline_parse, retry_attempted, outline_in_tok, outline_out_tok = \
+            await _call_outline(
+                research_question, evidence, gen_model,
+                outline_temperature, outline_max_tokens,
+            )
+        plans = outline_parse.plans
+        outline_ok = outline_parse.ok
+        outline_reason_codes = list(outline_parse.reason_codes)
+        outline_fallback_used = False
 
     # BUG-M-203 fix (deep-dive R4): if the planner (plus retry) did not
     # produce a valid 3-5 section plan, build a DETERMINISTIC 3-section
     # fallback from the evidence pool instead of a single generic
     # "Efficacy" section. Record the fallback so the orchestrator can
     # emit manifest.status=partial_outline_fallback.
-    if not plans or not outline_ok:
+    # ON-mode (research_plan set) uses the archetype fallback above and skips
+    # the legacy `_ALLOWED_SECTIONS` deterministic fallback.
+    if research_plan is None and (not plans or not outline_ok):
         logger.warning(
             "[multi_section] outline invalid (reasons=%s); using "
             "deterministic fallback",
@@ -4110,6 +4368,12 @@ async def generate_multi_section_report(
         )
         fact_dedup_telemetry = {"error": str(exc)}
 
+    # I-meta-005 Phase 1 (#985, P2 note B): in on-mode (a ResearchPlan was
+    # supplied) the M-44/M-47 post-generation validators route on the field-
+    # invariant archetype tag carried on each SectionResult, NOT on a clinical
+    # title literal. OFF-mode keeps title-keyed routing byte-identically.
+    _use_archetype = research_plan is not None
+
     # M-44 (2026-04-22): post-generation same-sentence validator +
     # one-shot regeneration. For each primary-eligible section, scan
     # verified prose for named-trial tokens; each trial mention must
@@ -4131,7 +4395,10 @@ async def generate_multi_section_report(
         for idx, sr in enumerate(section_results):
             if sr.dropped_due_to_failure or not sr.verified_text:
                 continue
-            if not _m44_section_is_primary_eligible(sr.title):
+            if not _section_is_primary_eligible(
+                title=sr.title, archetype=sr.archetype,
+                use_archetype=_use_archetype,
+            ):
                 continue
             viols = _m44_validate_primary_same_sentence(
                 sr.verified_text,
@@ -4184,6 +4451,8 @@ async def generate_multi_section_report(
                     title=orig_plan.title,
                     focus=orig_plan.focus + hint,
                     ev_ids=orig_plan.ev_ids,
+                    # I-meta-005 Phase 1 (#985, P1-13): preserve archetype.
+                    archetype=getattr(orig_plan, "archetype", ""),
                 )
             # Run regens in parallel with the same semaphore.
             regen_items = list(regen_plans_by_idx.items())
@@ -4230,7 +4499,10 @@ async def generate_multi_section_report(
         for sr in section_results:
             if sr.dropped_due_to_failure or not sr.verified_text:
                 continue
-            if not _m44_section_is_primary_eligible(sr.title):
+            if not _section_is_primary_eligible(
+                title=sr.title, archetype=sr.archetype,
+                use_archetype=_use_archetype,
+            ):
                 continue
             viols = _m44_validate_primary_same_sentence(
                 sr.verified_text,
@@ -4257,7 +4529,10 @@ async def generate_multi_section_report(
     m47_incomplete: bool = False
     mechanism_section_idx = None
     for _idx, sr in enumerate(section_results):
-        if (sr.title.lower() == "mechanism"
+        if (_section_is_mechanism(
+                title=sr.title, archetype=sr.archetype,
+                use_archetype=_use_archetype,
+            )
                 and not sr.dropped_due_to_failure
                 and sr.verified_text):
             mechanism_section_idx = _idx
@@ -4294,7 +4569,11 @@ async def generate_multi_section_report(
             if not passed:
                 orig_plan = next(
                     (p for p in plans
-                     if p.title.lower() == "mechanism"),
+                     if _section_is_mechanism(
+                         title=p.title,
+                         archetype=getattr(p, "archetype", ""),
+                         use_archetype=_use_archetype,
+                     )),
                     None,
                 )
                 if orig_plan is not None:
@@ -4330,6 +4609,8 @@ async def generate_multi_section_report(
                             title=orig_plan.title,
                             focus=orig_plan.focus + hint,
                             ev_ids=orig_plan.ev_ids,
+                            # I-meta-005 Phase 1 (#985, P1-13): preserve tag.
+                            archetype=getattr(orig_plan, "archetype", ""),
                         )
                         try:
                             regen_result = await _bounded_run(regen_plan)
diff --git a/src/polaris_graph/nodes/scope_gate.py b/src/polaris_graph/nodes/scope_gate.py
index 55b08900..f67523f7 100644
--- a/src/polaris_graph/nodes/scope_gate.py
+++ b/src/polaris_graph/nodes/scope_gate.py
@@ -290,6 +290,95 @@ def extract_pico_heuristic(query: str) -> dict[str, Optional[str]]:
     return result
 
 
+# ─────────────────────────────────────────────────────────────────────────────
+# I-meta-005 Phase 1 (#985, brief §2.2): field-agnostic frame extractor.
+#
+# ADDITIVE. The clinical `extract_pico_heuristic` + `_DRUG_NAME_RE` above are
+# UNCHANGED (off-path + the existing importers in completeness_checker.py and
+# contradiction_detector.py continue to use them). This heuristic does NOT use
+# the clinical drug/population regex; it produces a lightweight on-path frame
+# for ANY field by content-word extraction, with NO clinical literal as a
+# control value. It is a deterministic fallback only — the field-agnostic
+# planner (planning.research_planner) is the primary on-mode frame source; this
+# heuristic seeds entities/metrics/comparators when no LLM frame is available.
+# ─────────────────────────────────────────────────────────────────────────────
+
+# Field-invariant comparator markers (no domain literal): a word window around
+# these splits the question into compared alternatives, in any field.
+_FRAME_COMPARATOR_MARKERS_RE = re.compile(
+    r"\b(versus|vs\.?|compared to|compared with|relative to|against|"
+    r"as opposed to|rather than)\b",
+    re.IGNORECASE,
+)
+# Field-invariant metric cues: quantity words that suggest a measured outcome.
+_FRAME_METRIC_CUES_RE = re.compile(
+    r"\b(rate|ratio|cost|price|percent|percentage|share|level|score|index|"
+    r"efficiency|yield|throughput|latency|reduction|increase|change|"
+    r"probability|risk|return|growth|emissions?|temperature|accuracy)\b",
+    re.IGNORECASE,
+)
+# Generic stopwords for content-word entity extraction (no domain terms).
+_FRAME_STOPWORDS = frozenset({
+    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "of",
+    "in", "on", "at", "to", "for", "with", "by", "from", "as", "that", "this",
+    "these", "those", "it", "its", "be", "been", "what", "which", "who", "how",
+    "why", "when", "where", "we", "our", "their", "between", "into", "about",
+    "than", "such", "does", "do", "can", "may", "any", "also", "would", "should",
+    "could", "will", "more", "most", "some", "all", "not", "no", "over", "under",
+})
+
+
+def extract_research_frame_heuristic(query: str) -> dict[str, list[str]]:
+    """Field-agnostic frame heuristic for the on-path (brief §2.2).
+
+    Returns a dict with the `ResearchFrame` anchor keys (entities / relations /
+    metrics / comparators / constraints). Pure / no-network / no-LLM and — by
+    design — uses NO clinical regex. Comparators come from generic comparison
+    markers, metrics from generic quantity cues, and entities from the
+    remaining content words. The planner supersedes this when an LLM frame is
+    available; this is the deterministic seed/fallback.
+    """
+    q = (query or "").strip()
+    frame: dict[str, list[str]] = {
+        "entities": [],
+        "relations": [],
+        "metrics": [],
+        "comparators": [],
+        "constraints": [],
+    }
+    if not q:
+        return frame
+
+    # Comparators: text fragments flanking a generic comparison marker.
+    comparators: list[str] = []
+    for m in _FRAME_COMPARATOR_MARKERS_RE.finditer(q):
+        tail = q[m.end():].strip()
+        first_clause = re.split(r"[,.;?]", tail, maxsplit=1)[0].strip()
+        if first_clause:
+            comparators.append(first_clause[:60])
+    frame["comparators"] = list(dict.fromkeys(comparators))[:6]
+
+    # Metrics: generic quantity cues present in the question.
+    metrics = [m.group(1).lower() for m in _FRAME_METRIC_CUES_RE.finditer(q)]
+    frame["metrics"] = list(dict.fromkeys(metrics))[:8]
+
+    # Entities: content words (capitalized phrases or multi-char tokens) minus
+    # generic stopwords. No domain dictionary.
+    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", q)
+    entities: list[str] = []
+    seen: set[str] = set()
+    for tok in tokens:
+        low = tok.lower()
+        if low in _FRAME_STOPWORDS:
+            continue
+        if low in seen:
+            continue
+        seen.add(low)
+        entities.append(tok)
+    frame["entities"] = entities[:12]
+    return frame
+
+
 # ─────────────────────────────────────────────────────────────────────────────
 # Main entry point
 # ─────────────────────────────────────────────────────────────────────────────
diff --git a/src/polaris_graph/planning/__init__.py b/src/polaris_graph/planning/__init__.py
new file mode 100644
index 00000000..187ab35b
--- /dev/null
+++ b/src/polaris_graph/planning/__init__.py
@@ -0,0 +1,37 @@
+"""Field-agnostic research-planning package (I-meta-005 Phase 1, #985).
+
+Houses the question-shaped research planner that — behind the
+`PG_USE_RESEARCH_PLANNER` flag — replaces the clinical-only PICO + clause-split
++ `_ALLOWED_SECTIONS` decomposition path with a field-invariant frame,
+faceted sub-queries, and an archetype-tagged section outline.
+
+This is a SHADOW build: nothing here runs unless the on-flag is set AND the
+caller explicitly threads the plan through. OFF behavior is byte-identical to
+the legacy path. The single Writer call is an injected callable — the package
+NEVER constructs an `OpenRouterClient` or a live HTTP client, so build + smoke
+are spend-free.
+"""
+
+from __future__ import annotations
+
+from src.polaris_graph.planning.research_planner import (
+    DEFAULT_MAX_SUBQUERIES,
+    MIN_SUBQUERIES,
+    PlannerError,
+    ResearchFrame,
+    ResearchPlan,
+    SectionOutlineItem,
+    plan_research,
+    serialize_plan_canonical,
+)
+
+__all__ = [
+    "DEFAULT_MAX_SUBQUERIES",
+    "MIN_SUBQUERIES",
+    "PlannerError",
+    "ResearchFrame",
+    "ResearchPlan",
+    "SectionOutlineItem",
+    "plan_research",
+    "serialize_plan_canonical",
+]
diff --git a/src/polaris_graph/planning/research_planner.py b/src/polaris_graph/planning/research_planner.py
new file mode 100644
index 00000000..4b53c323
--- /dev/null
+++ b/src/polaris_graph/planning/research_planner.py
@@ -0,0 +1,455 @@
+"""Field-agnostic research planner (I-meta-005 Phase 1, #985).
+
+Closes parent-plan gaps #1 (decomposition), #2 (planning), #8 (report
+structure), #10 (decision seed). Behind `PG_USE_RESEARCH_PLANNER`; OFF is
+byte-identical to the legacy clause-split + clinical-PICO + `_ALLOWED_SECTIONS`
+path (this module is simply not invoked when off).
+
+DESIGN (brief §2.1):
+- `ResearchFrame` — a generalized PICO that carries NO clinical fields:
+  entities / relations / metrics / comparators / constraints + a `claim_type`
+  from a field-invariant enum. A housing, physics, or trade-policy question
+  produces a usable frame; nothing is clinical-specific.
+- `plan_research(question, *, planner_llm)` makes ONE normal Writer call (plus
+  AT MOST ONE bounded retry when the honest sub-query count is short). The
+  Writer is an INJECTED callable `Callable[[str], str]`, so this module never
+  constructs an `OpenRouterClient` or a live HTTP client — build + smoke are
+  spend-free. Production threads the existing Writer through the callable.
+- Strict JSON parse. Malformed -> raise `PlannerError` (LAW II). There is NO
+  silent fallback to the clause-splitter; the dual path lives at the caller.
+- Sub-query count is HONEST (brief §2.1):
+  * UPPER bound `DEFAULT_MAX_SUBQUERIES` (40): merge/truncate deterministically.
+  * LOWER bound is a FAIL-LOUD retry, not deterministic padding: when fewer
+    than `MIN_SUBQUERIES` facets come back, retry ONCE asking for more. If a
+    genuinely narrow question still yields fewer, ACCEPT the honest smaller
+    count and log — never fabricate facets to hit a target.
+- `ResearchFrame.to_anchor_protocol()` exposes the frame's own tokens as an
+  anchor-protocol dict so planner sub-queries validate against the frame
+  (brief §2.4, validator adapter).
+- `serialize_plan_canonical()` emits canonical JSON (sort_keys, fixed
+  separators) so the caller can SHA-pin the `ResearchPlan` BEFORE retrieval
+  (gap #19 extension, brief §2.1).
+
+The archetype tag vocabulary is owned by the generator
+(`multi_section_generator._SECTION_ARCHETYPES`); the planner imports it so the
+two halves of the dual path share ONE source of truth and the planner stays
+field-agnostic (no clinical literal as a control value).
+"""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import logging
+from dataclasses import dataclass, field
+from typing import Any, Callable
+
+from src.polaris_graph.generator.multi_section_generator import (
+    SECTION_ARCHETYPES,
+)
+
+logger = logging.getLogger("polaris_graph.research_planner")
+
+
+# Field-invariant claim taxonomy. NOT clinical — these classify the SHAPE of
+# the question's answer (does it report measured effects, compare policies,
+# forecast, explain a mechanism, or describe a landscape).
+CLAIM_TYPES: frozenset[str] = frozenset({
+    "empirical",
+    "policy-comparison",
+    "forecast",
+    "mechanism",
+    "descriptive",
+})
+
+# UPPER bound on emitted sub-queries (brief §2.1). >40 is merged/truncated
+# deterministically. The fetch cap (`PG_SWEEP_FETCH_CAP`) bounds FETCHED URLs
+# downstream; this bounds the per-question query fan-out.
+DEFAULT_MAX_SUBQUERIES = 40
+# LOWER bound that triggers ONE fail-loud retry (brief §2.1). A genuinely
+# narrow question may legitimately accept fewer after the retry; we never pad.
+MIN_SUBQUERIES = 12
+
+
+class PlannerError(RuntimeError):
+    """Raised when the planner LLM emits unusable output (LAW II: fail loud,
+    no silent fallback to the clause-splitter)."""
+
+
+@dataclass
+class ResearchFrame:
+    """Generalized, field-invariant question frame (brief §2.1).
+
+    Carries NO clinical-specific fields. `claim_type` is one of `CLAIM_TYPES`.
+    """
+
+    entities: list[str] = field(default_factory=list)
+    relations: list[str] = field(default_factory=list)
+    metrics: list[str] = field(default_factory=list)
+    comparators: list[str] = field(default_factory=list)
+    constraints: list[str] = field(default_factory=list)
+    claim_type: str = "descriptive"
+
+    def to_anchor_protocol(self, research_question: str) -> dict[str, Any]:
+        """Produce an anchor-protocol dict for `validate_amplified_queries`
+        (brief §2.4). Bundles the verbatim research_question with the frame's
+        own tokens under the additive keys `_build_anchor_tokens` merges. This
+        lets planner sub-queries validate against the frame's entities /
+        metrics / comparators rather than against clinical PICO fields.
+        """
+        return {
+            "research_question": research_question or "",
+            "entities": list(self.entities),
+            "relations": list(self.relations),
+            "metrics": list(self.metrics),
+            "comparators": list(self.comparators),
+            "constraints": list(self.constraints),
+        }
+
+
+@dataclass
+class SectionOutlineItem:
+    """One pre-retrieval outline section (brief §2.1).
+
+    Holds an archetype TAG (field-invariant, from `SECTION_ARCHETYPES`), a
+    question-specific TITLE, and a per-section evidence TARGET. It carries NO
+    evidence IDs — no evidence exists yet at planning time; the generator's
+    on-mode handoff assigns `ev_ids` post-retrieval (brief §2.5).
+    """
+
+    archetype: str
+    title: str
+    evidence_target: int = 0
+
+
+@dataclass
+class ResearchPlan:
+    """The full pre-registered plan (brief §2.1): frame + faceted sub-queries
+    + archetype outline. Canonically serialized + SHA-pinned before retrieval.
+    """
+
+    research_question: str
+    frame: ResearchFrame
+    sub_queries: list[str] = field(default_factory=list)
+    outline: list[SectionOutlineItem] = field(default_factory=list)
+
+    def to_canonical_dict(self) -> dict[str, Any]:
+        """Plain-dict projection for canonical serialization + SHA pinning."""
+        return {
+            "research_question": self.research_question,
+            "frame": {
+                "entities": list(self.frame.entities),
+                "relations": list(self.frame.relations),
+                "metrics": list(self.frame.metrics),
+                "comparators": list(self.frame.comparators),
+                "constraints": list(self.frame.constraints),
+                "claim_type": self.frame.claim_type,
+            },
+            "sub_queries": list(self.sub_queries),
+            "outline": [
+                {
+                    "archetype": item.archetype,
+                    "title": item.title,
+                    "evidence_target": item.evidence_target,
+                }
+                for item in self.outline
+            ],
+        }
+
+
+def serialize_plan_canonical(plan: ResearchPlan) -> str:
+    """Serialize a `ResearchPlan` as CANONICAL JSON (brief §2.1): `sort_keys`
+    + fixed separators so the bytes are reproducible. The caller hashes these
+    bytes to SHA-pin the plan before retrieval (gap #19 extension).
+    """
+    return json.dumps(
+        plan.to_canonical_dict(),
+        sort_keys=True,
+        separators=(",", ":"),
+        ensure_ascii=False,
+    )
+
+
+def plan_sha256(plan: ResearchPlan) -> str:
+    """SHA-256 of the canonical-JSON bytes of `plan`."""
+    canonical = serialize_plan_canonical(plan)
+    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
+
+
+def _strip_code_fence(raw: str) -> str:
+    """Remove an optional ```json ... ``` fence and return the inner JSON
+    object substring (first `{` .. last `}`)."""
+    stripped = (raw or "").strip()
+    if stripped.startswith("```"):
+        # Drop the opening fence line and a trailing fence if present.
+        first_newline = stripped.find("\n")
+        if first_newline != -1:
+            stripped = stripped[first_newline + 1:]
+        if stripped.rstrip().endswith("```"):
+            stripped = stripped.rstrip()[: -3]
+    start = stripped.find("{")
+    end = stripped.rfind("}")
+    if start == -1 or end == -1 or end < start:
+        return ""
+    return stripped[start:end + 1]
+
+
+def _as_str_list(value: Any) -> list[str]:
+    """Coerce a JSON value into a clean list[str] (drop empties, dedup
+    case-insensitively, preserve order)."""
+    if not isinstance(value, list):
+        return []
+    out: list[str] = []
+    seen: set[str] = set()
+    for item in value:
+        if not isinstance(item, (str, int, float)):
+            continue
+        text = str(item).strip()
+        if not text:
+            continue
+        key = text.lower()
+        if key in seen:
+            continue
+        seen.add(key)
+        out.append(text)
+    return out
+
+
+def _parse_frame(obj: dict[str, Any]) -> ResearchFrame:
+    """Build a `ResearchFrame` from the parsed JSON. Unknown `claim_type`
+    raises (LAW II) — the planner must commit to a field-invariant claim
+    shape, not emit a clinical or free-text category."""
+    raw_frame = obj.get("frame")
+    if not isinstance(raw_frame, dict):
+        raise PlannerError("planner output has no object-valued 'frame'")
+    claim_type = str(raw_frame.get("claim_type", "")).strip().lower()
+    if claim_type not in CLAIM_TYPES:
+        raise PlannerError(
+            f"planner emitted unknown claim_type={claim_type!r}; "
+            f"allowed={sorted(CLAIM_TYPES)}"
+        )
+    return ResearchFrame(
+        entities=_as_str_list(raw_frame.get("entities")),
+        relations=_as_str_list(raw_frame.get("relations")),
+        metrics=_as_str_list(raw_frame.get("metrics")),
+        comparators=_as_str_list(raw_frame.get("comparators")),
+        constraints=_as_str_list(raw_frame.get("constraints")),
+        claim_type=claim_type,
+    )
+
+
+def _parse_sub_queries(obj: dict[str, Any]) -> list[str]:
+    """Extract + dedup the faceted sub-queries. Empty list raises (LAW II:
+    a plan with no facets is unusable)."""
+    sub_queries = _as_str_list(obj.get("sub_queries"))
+    if not sub_queries:
+        raise PlannerError("planner output has no usable 'sub_queries'")
+    return sub_queries
+
+
+def _parse_outline(obj: dict[str, Any]) -> list[SectionOutlineItem]:
+    """Extract the archetype-tagged outline. Each item validates its TAG
+    against `SECTION_ARCHETYPES`; off-tag items are dropped. An empty outline
+    after validation raises (LAW II)."""
+    raw_outline = obj.get("outline")
+    if not isinstance(raw_outline, list):
+        raise PlannerError("planner output has no list-valued 'outline'")
+    valid_tags = {tag.lower(): tag for tag in SECTION_ARCHETYPES}
+    items: list[SectionOutlineItem] = []
+    seen_titles: set[str] = set()
+    for entry in raw_outline:
+        if not isinstance(entry, dict):
+            continue
+        tag_raw = str(entry.get("archetype", "")).strip().lower()
+        if tag_raw not in valid_tags:
+            logger.info(
+                "[research_planner] dropped off-tag outline archetype=%r",
+                entry.get("archetype"),
+            )
+            continue
+        title = str(entry.get("title", "")).strip()
+        if not title:
+            continue
+        title_key = title.lower()
+        if title_key in seen_titles:
+            continue
+        seen_titles.add(title_key)
+        target_raw = entry.get("evidence_target", 0)
+        try:
+            evidence_target = int(target_raw)
+        except (TypeError, ValueError):
+            evidence_target = 0
+        items.append(SectionOutlineItem(
+            archetype=valid_tags[tag_raw],
+            title=title,
+            evidence_target=max(0, evidence_target),
+        ))
+    if not items:
+        raise PlannerError(
+            "planner outline had no entries with a valid archetype tag"
+        )
+    return items
+
+
+def _parse_plan(raw: str, research_question: str) -> ResearchPlan:
+    """Strict-parse one planner JSON response into a `ResearchPlan`. Any
+    structural failure raises `PlannerError` (LAW II)."""
+    payload = _strip_code_fence(raw)
+    if not payload:
+        raise PlannerError("planner returned no JSON object")
+    try:
+        obj = json.loads(payload)
+    except json.JSONDecodeError as exc:
+        raise PlannerError(f"planner JSON decode failed: {exc}") from exc
+    if not isinstance(obj, dict):
+        raise PlannerError("planner JSON root is not an object")
+    frame = _parse_frame(obj)
+    sub_queries = _parse_sub_queries(obj)
+    outline = _parse_outline(obj)
+    return ResearchPlan(
+        research_question=research_question,
+        frame=frame,
+        sub_queries=sub_queries,
+        outline=outline,
+    )
+
+
+def _merge_truncate_subqueries(
+    sub_queries: list[str],
+    *,
+    max_subqueries: int,
+) -> list[str]:
+    """UPPER-bound enforcement (brief §2.1): dedup (already done upstream) and
+    deterministically truncate to `max_subqueries`, preserving order."""
+    if len(sub_queries) <= max_subqueries:
+        return list(sub_queries)
+    logger.info(
+        "[research_planner] truncating %d sub-queries to upper bound %d",
+        len(sub_queries), max_subqueries,
+    )
+    return list(sub_queries[:max_subqueries])
+
+
+def _build_prompt(question: str, *, more_facets: bool, min_subqueries: int) -> str:
+    """Build the planner prompt. `more_facets=True` is the lower-bound retry
+    variant that asks for additional facets. Field-agnostic: the prompt names
+    NO domain and NO clinical concept; it asks for a generalized frame +
+    facets + archetype outline."""
+    archetype_list = ", ".join(SECTION_ARCHETYPES)
+    claim_type_list = ", ".join(sorted(CLAIM_TYPES))
+    base = (
+        "You are a field-agnostic research planner. Decompose the research "
+        "question into a structured plan. The question may be from ANY field "
+        "(science, policy, economics, engineering, medicine, history, ...). "
+        "Do NOT assume a clinical or any single domain.\n\n"
+        f"RESEARCH QUESTION:\n{question}\n\n"
+        "Return ONE JSON object with exactly these keys:\n"
+        '  "frame": {\n'
+        '     "entities":   [the key actors / objects / subjects],\n'
+        '     "relations":  [the relationships / actions being studied],\n'
+        '     "metrics":    [the quantities / outcomes / measures of interest],\n'
+        '     "comparators":[the alternatives / baselines / counterfactuals],\n'
+        '     "constraints":[scope limits: population, jurisdiction, timeframe, setting],\n'
+        f'     "claim_type": one of [{claim_type_list}]\n'
+        "  },\n"
+        '  "sub_queries": [faceted search queries, each a focused phrase that '
+        "covers ONE facet of the question — collectively spanning every "
+        "entity x metric x comparator x constraint combination the question "
+        f"implies; aim for {min_subqueries} or more for a broad question, "
+        "fewer only for a genuinely narrow one],\n"
+        '  "outline": [section objects, each with:\n'
+        '       "archetype": one of the field-invariant tags below,\n'
+        '       "title":     a QUESTION-SPECIFIC section heading (not a generic label),\n'
+        '       "evidence_target": an integer target number of sources for the section\n'
+        "  ]\n\n"
+        f"ALLOWED ARCHETYPE TAGS (pick the ones the question needs): {archetype_list}\n\n"
+        "RULES:\n"
+        "- The titles must be specific to THIS question, not generic category "
+        "names. The archetype tag is the field-invariant control; the title "
+        "is the human-facing heading.\n"
+        "- Choose archetypes that fit the question's claim_type. A decision / "
+        "comparison question needs a Decision archetype; an explanatory "
+        "question needs a Mechanism archetype; etc.\n"
+        "- Output ONLY the JSON object. No preamble, no markdown fence, no "
+        "sign-off.\n"
+    )
+    if more_facets:
+        base += (
+            "\nPREVIOUS ATTEMPT returned too few sub_queries. Expand the "
+            "faceting: enumerate every entity, every metric, every comparator, "
+            "and every constraint as its own focused sub_query so the set is "
+            f"comprehensive (at least {min_subqueries} where the question is "
+            "broad). Do NOT pad with near-duplicates — add genuinely distinct "
+            "facets.\n"
+        )
+    return base
+
+
+def plan_research(
+    question: str,
+    *,
+    planner_llm: Callable[[str], str],
+    max_subqueries: int = DEFAULT_MAX_SUBQUERIES,
+    min_subqueries: int = MIN_SUBQUERIES,
+) -> ResearchPlan:
+    """Produce a `ResearchPlan` from `question` using ONE Writer call (plus at
+    most one bounded lower-bound retry).
+
+    Args:
+        question: The raw research question (stored verbatim on the plan).
+        planner_llm: Injected Writer callable `prompt -> response_text`. This
+            is the ONLY way the planner reaches an LLM; the module never
+            constructs an `OpenRouterClient` or a live HTTP client. Tests pass
+            a fake; production passes the real Writer.
+        max_subqueries: UPPER bound; >this is merged/truncated deterministically.
+        min_subqueries: LOWER bound that triggers ONE fail-loud retry.
+
+    Returns:
+        A validated `ResearchPlan` (frame + sub_queries + archetype outline).
+
+    Raises:
+        ValueError: empty question.
+        PlannerError: malformed / unusable planner output (LAW II — no silent
+            fallback to the clause-splitter).
+    """
+    if not question or not question.strip():
+        raise ValueError("question must be non-empty.")
+    if not callable(planner_llm):
+        raise TypeError("planner_llm must be a callable[[str], str].")
+
+    prompt = _build_prompt(
+        question, more_facets=False, min_subqueries=min_subqueries,
+    )
+    raw = planner_llm(prompt)
+    plan = _parse_plan(raw, question.strip())
+    plan.sub_queries = _merge_truncate_subqueries(
+        plan.sub_queries, max_subqueries=max_subqueries,
+    )
+
+    # LOWER-bound policy (brief §2.1): a fail-loud retry, NOT padding. If the
+    # honest count is short, ask once for more facets. If still short, accept
+    # the honest smaller count for a genuinely narrow question and log.
+    if len(plan.sub_queries) < min_subqueries:
+        logger.info(
+            "[research_planner] sub_query count %d < min %d — retrying once "
+            "for more facets",
+            len(plan.sub_queries), min_subqueries,
+        )
+        retry_prompt = _build_prompt(
+            question, more_facets=True, min_subqueries=min_subqueries,
+        )
+        retry_raw = planner_llm(retry_prompt)
+        retry_plan = _parse_plan(retry_raw, question.strip())
+        retry_plan.sub_queries = _merge_truncate_subqueries(
+            retry_plan.sub_queries, max_subqueries=max_subqueries,
+        )
+        # Keep whichever response carried more honest facets.
+        if len(retry_plan.sub_queries) > len(plan.sub_queries):
+            plan = retry_plan
+        if len(plan.sub_queries) < min_subqueries:
+            logger.info(
+                "[research_planner] accepting honest narrow count %d "
+                "(< min %d) after retry — NOT padding",
+                len(plan.sub_queries), min_subqueries,
+            )
+    return plan
diff --git a/src/polaris_graph/retrieval/scope_query_validator.py b/src/polaris_graph/retrieval/scope_query_validator.py
index 4a2b6049..b7255a0f 100644
--- a/src/polaris_graph/retrieval/scope_query_validator.py
+++ b/src/polaris_graph/retrieval/scope_query_validator.py
@@ -83,18 +83,41 @@ class ValidationResult:
 
 
 def _build_anchor_tokens(protocol: dict[str, Any]) -> set[str]:
-    """Merge research_question + PICO tokens into one anchor set.
+    """Merge research_question + anchor tokens into one anchor set.
 
-    Accepts either a ProtocolDocument dict (from scope_gate) or any
-    dict with similar fields. Missing fields are skipped gracefully.
+    Accepts either a ProtocolDocument dict (from scope_gate) or any dict with
+    similar fields. Missing fields are skipped gracefully.
+
+    Clinical PICO fields (population / intervention / comparator / outcome) are
+    string-valued and tokenized as before — OFF byte-identical.
+
+    I-meta-005 Phase 1 (#985, brief §2.4): ADDITIVELY also merge the field-
+    agnostic `ResearchFrame` anchor fields (entities / relations / metrics /
+    comparators / constraints) when present, so planner sub-queries derived
+    from a non-clinical frame validate against the frame's OWN tokens. These
+    fields may be list-valued (from `ResearchFrame.to_anchor_protocol`); each
+    element is tokenized. A clinical PICO protocol carries none of them, so
+    this extension does not change PICO behavior.
     """
     bag: set[str] = set()
+    # Legacy clinical PICO anchors (string-valued). Unchanged.
     for field in (
         "research_question", "population", "intervention",
         "comparator", "outcome",
     ):
         val = protocol.get(field) or ""
         bag |= _tokenize(str(val))
+    # I-meta-005 Phase 1: field-agnostic frame anchors (list-valued). Skipped
+    # gracefully when absent (clinical PICO protocols), so OFF is unchanged.
+    for field in (
+        "entities", "relations", "metrics", "comparators", "constraints",
+    ):
+        val = protocol.get(field)
+        if isinstance(val, (list, tuple, set)):
+            for item in val:
+                bag |= _tokenize(str(item))
+        elif val:
+            bag |= _tokenize(str(val))
     return bag
 
 
diff --git a/tests/polaris_graph/planning/__init__.py b/tests/polaris_graph/planning/__init__.py
new file mode 100644
index 00000000..e69de29b
diff --git a/tests/polaris_graph/planning/test_research_planner_phase1.py b/tests/polaris_graph/planning/test_research_planner_phase1.py
new file mode 100644
index 00000000..8a6c3a23
--- /dev/null
+++ b/tests/polaris_graph/planning/test_research_planner_phase1.py
@@ -0,0 +1,663 @@
+"""Phase 1 smoke — research planner + archetype sections (I-meta-005 #985).
+
+Implements ALL 17 brief cases P1-1..P1-17. Spend-free + serialized (§8.4):
+every fake is a plain function/class (NO `unittest.mock`), every evidence pool
+is a real dict, and the planner LLM is an INJECTED callable. P1-11 asserts no
+`OpenRouterClient` / live httpx client is constructed anywhere on the exercised
+on-path.
+
+The two non-relaxable walls:
+- P1-1 OFF byte-identity (pins asdict/manifest-style section output — Codex P2
+  note A — proving the additive `archetype` field is inert in OFF).
+- the field-agnostic guards P1-4 (zero clinical labels on physics/ag-policy),
+  P1-15/16/17 (on-mode suppresses every domain router).
+"""
+
+from __future__ import annotations
+
+import builtins
+import dataclasses
+import json
+
+import pytest
+
+from src.polaris_graph.planning.research_planner import (
+    DEFAULT_MAX_SUBQUERIES,
+    MIN_SUBQUERIES,
+    PlannerError,
+    ResearchFrame,
+    ResearchPlan,
+    SectionOutlineItem,
+    plan_research,
+    plan_sha256,
+    serialize_plan_canonical,
+)
+from src.polaris_graph.generator.multi_section_generator import (
+    SECTION_ARCHETYPES,
+    SectionPlan,
+    SectionResult,
+    _ALLOWED_SECTIONS,
+    _assign_evidence_to_planned_outline,
+    _build_archetype_fallback_outline,
+    _build_deterministic_fallback_outline,
+    _m44_inject_primaries_into_outline,
+    _parse_outline,
+    _section_is_mechanism,
+    _section_is_primary_eligible,
+    select_advisory_prompt_text,
+)
+from src.polaris_graph.retrieval.scope_query_validator import (
+    _build_anchor_tokens,
+    validate_amplified_queries,
+)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# Fakes (plain — no unittest.mock).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _frame_json(*, claim_type="empirical", entities=None, metrics=None,
+                comparators=None):
+    return {
+        "entities": entities or ["alpha", "beta"],
+        "relations": ["affects"],
+        "metrics": metrics or ["rate", "cost"],
+        "comparators": comparators or ["baseline"],
+        "constraints": ["region", "timeframe"],
+        "claim_type": claim_type,
+    }
+
+
+def make_fake_planner(*, n_subqueries=20, claim_type="empirical",
+                      outline=None, entities=None, metrics=None,
+                      comparators=None, second_n=None):
+    """Build a fake planner callable returning a valid JSON plan. If
+    `second_n` is set, the SECOND call returns that many sub_queries (used to
+    exercise the lower-bound retry)."""
+    state = {"calls": 0}
+    default_outline = outline or [
+        {"archetype": "Background", "title": "How the system behaves",
+         "evidence_target": 8},
+        {"archetype": "Quantitative-Comparison",
+         "title": "Comparing the alternatives", "evidence_target": 10},
+        {"archetype": "Decision", "title": "Which path is best",
+         "evidence_target": 6},
+    ]
+
+    def _fake(prompt: str) -> str:
+        state["calls"] += 1
+        count = n_subqueries
+        if second_n is not None and state["calls"] >= 2:
+            count = second_n
+        payload = {
+            "frame": _frame_json(claim_type=claim_type, entities=entities,
+                                 metrics=metrics, comparators=comparators),
+            "sub_queries": [
+                f"facet {i} alpha beta gamma" for i in range(count)
+            ],
+            "outline": default_outline,
+        }
+        return json.dumps(payload)
+
+    _fake.state = state  # type: ignore[attr-defined]
+    return _fake
+
+
+class CaptureSearch:
+    """Capture-only stub for `_serper_search` / `_s2_bulk_search`: records the
+    query strings it is called with and returns NO hits (no network)."""
+
+    def __init__(self):
+        self.queries: list[str] = []
+
+    def serper(self, q, num=10):
+        self.queries.append(q)
+        return []
+
+    def s2(self, q, limit=10):
+        self.queries.append(q)
+        return []
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-1 OFF byte-identity (pins asdict/manifest output — Codex P2 note A).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_1_off_byte_identity_outline_and_section_output() -> None:
+    from src.polaris_graph.retrieval.query_decomposer import decompose_question
+
+    # OFF path: the legacy clause-splitter is byte-identical.
+    clinical_q = (
+        "What is the efficacy and safety of tirzepatide versus semaglutide "
+        "for HbA1c reduction and weight loss in adults with type 2 diabetes; "
+        "how do the cardiovascular outcomes compare?"
+    )
+    decomposed = decompose_question(clinical_q)
+    assert decomposed == decompose_question(clinical_q)  # deterministic
+    assert all(isinstance(s, str) for s in decomposed)
+
+    # OFF outline parser unchanged + SectionPlan.archetype defaults "".
+    raw = json.dumps({"sections": [
+        {"title": "Efficacy", "focus": "f", "ev_ids": ["ev_001", "ev_002"]},
+        {"title": "Safety", "focus": "f", "ev_ids": ["ev_003", "ev_004"]},
+        {"title": "Comparative", "focus": "f", "ev_ids": ["ev_005", "ev_006"]},
+    ]})
+    result = _parse_outline(raw)
+    assert result.ok is True
+    assert [p.title for p in result.plans] == ["Efficacy", "Safety",
+                                               "Comparative"]
+    for p in result.plans:
+        assert p.archetype == ""  # additive field inert in OFF
+
+    # P2 note A: the ACTUAL OFF artifact is the manifest's title-only outline
+    # projection (`[p.title for p in multi.outline]`). Pin it: it carries no
+    # archetype key at all, so the additive field cannot leak into the written
+    # manifest. This is the binding byte-identity surface.
+    manifest_outline = [p.title for p in result.plans]
+    assert manifest_outline == ["Efficacy", "Safety", "Comparative"]
+    # No production serializer recurses a section dataclass via
+    # `dataclasses.asdict` (verified by repo grep: only classified_sources is
+    # asdict-ed; MultiSectionResult/SectionResult/SectionPlan are never
+    # asdict-ed in any artifact path, and sweep_integration explicitly does not
+    # import MultiSectionResult). When asdict IS applied (a test or a future
+    # caller), the field surfaces as the inert empty default in OFF — it never
+    # carries a non-empty value unless a plan was supplied (ON mode).
+    sr_off = SectionResult(
+        title="Efficacy", focus="f", ev_ids_assigned=["ev_001"],
+        raw_draft="", rewritten_draft="", verified_text="x",
+        biblio_slice=[], sentences_verified=1, sentences_dropped=0,
+        regen_attempted=False, dropped_due_to_failure=False,
+    )
+    assert sr_off.archetype == ""  # inert empty default in OFF
+    assert dataclasses.asdict(sr_off)["archetype"] == ""
+
+    # The legacy deterministic fallback still emits archetype="" SectionPlans.
+    ev = [{"evidence_id": f"ev_{i:03d}"} for i in range(1, 10)]
+    fb = _build_deterministic_fallback_outline(ev)
+    assert [p.title for p in fb] == ["Efficacy", "Safety", "Comparative"]
+    assert all(p.archetype == "" for p in fb)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-2 LIVE-PATH wiring to the EFFECTIVE-QUERY seam.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_2_planner_subqueries_reach_search_calls(monkeypatch) -> None:
+    from src.polaris_graph.retrieval import live_retriever
+
+    cap = CaptureSearch()
+    monkeypatch.setattr(live_retriever, "_serper_search", cap.serper)
+    monkeypatch.setattr(live_retriever, "_s2_bulk_search", cap.s2)
+
+    # The fake's sub-queries must overlap the frame's anchor tokens so they
+    # survive validate_amplified_queries (off-scope queries are dropped — that
+    # IS the validator's job; this case proves on-scope sub-queries reach the
+    # search calls).
+    planner = make_fake_planner(
+        n_subqueries=14,
+        entities=["solar", "panel", "efficiency"],
+        metrics=["efficiency", "cost"],
+        outline=[{"archetype": "Background", "title": "T",
+                  "evidence_target": 8}],
+    )
+
+    def _on_scope_planner(prompt: str) -> str:
+        payload = json.loads(planner(prompt))
+        payload["sub_queries"] = [
+            f"solar panel efficiency cost facet {i}" for i in range(14)
+        ]
+        return json.dumps(payload)
+
+    plan = plan_research("How efficient are rooftop solar panels?",
+                         planner_llm=_on_scope_planner)
+    protocol = plan.frame.to_anchor_protocol(
+        "How efficient are rooftop solar panels?")
+
+    res = live_retriever.run_live_retrieval(
+        research_question="How efficient are rooftop solar panels?",
+        amplified_queries=list(plan.sub_queries),
+        protocol=protocol,
+        max_serper=3, max_s2=3, fetch_cap=5,
+        enable_openalex_enrich=False, enable_prefetch_filter=False,
+        domain=None,
+    )
+    # The planner sub-queries must SURVIVE validate_amplified_queries into the
+    # effective query list and appear at the search calls.
+    captured = set(cap.queries)
+    reached = [sq for sq in plan.sub_queries if sq in captured]
+    assert reached, "planner sub-queries did not reach the search seam"
+    assert "scope_query_validator" in " ".join(res.notes)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-3 frame + sub-queries (5 golden-shaped Qs).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_3_frame_and_subqueries_golden() -> None:
+    golden = [
+        "What is the comparative efficacy of tirzepatide?",
+        "How does carbon pricing affect industrial investment?",
+        "What is the lifecycle cost of solid-state batteries?",
+        "How will rooftop solar adoption change grid demand by 2035?",
+        "What governs cross-border pharmaceutical pricing in the EU?",
+    ]
+    for q in golden:
+        planner = make_fake_planner(n_subqueries=25)
+        plan = plan_research(q, planner_llm=planner)
+        assert isinstance(plan.frame, ResearchFrame)
+        assert 20 <= len(plan.sub_queries) <= 40
+        assert plan.outline
+        assert all(o.archetype in SECTION_ARCHETYPES for o in plan.outline)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-4 off-domain field-agnostic proof: ZERO clinical labels.
+# ─────────────────────────────────────────────────────────────────────────────
+
+_CLINICAL_LABELS = {
+    "efficacy", "safety", "dose response", "population subgroups",
+}
+
+
+def test_p1_4_off_domain_no_clinical_section_labels() -> None:
+    cases = {
+        "physics": "How does superconductor critical temperature vary with pressure?",
+        "ag_policy": "How does a fertilizer subsidy change crop yields and farm income?",
+        "jp_pharma_reg": "How does PMDA review timeline compare to FDA for orphan drugs?",
+    }
+    for name, q in cases.items():
+        planner = make_fake_planner(
+            n_subqueries=22,
+            outline=[
+                {"archetype": "Background", "title": f"{name} background",
+                 "evidence_target": 8},
+                {"archetype": "Quantitative-Comparison",
+                 "title": f"{name} comparison", "evidence_target": 10},
+                {"archetype": "Decision", "title": f"{name} decision",
+                 "evidence_target": 6},
+            ],
+        )
+        plan = plan_research(q, planner_llm=planner)
+        titles = " ".join(o.title.lower() for o in plan.outline)
+        tags = {o.archetype.lower() for o in plan.outline}
+        for label in _CLINICAL_LABELS:
+            assert label not in titles, f"{name}: clinical title {label!r}"
+            assert label.replace(" ", "-") not in tags
+        # Physics + ag-policy specifically must carry zero clinical tags.
+        if name in ("physics", "ag_policy"):
+            assert "efficacy" not in titles and "safety" not in titles
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-5 archetype routing (on-mode keys on archetype, off-mode on title).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_5_archetype_routing_on_vs_off() -> None:
+    # ON-mode: a Mechanism archetype with a NON-clinical title routes as
+    # mechanism; a non-mechanism archetype does not.
+    assert _section_is_mechanism(
+        title="How carbon pricing changes investment",
+        archetype="Mechanism", use_archetype=True) is True
+    assert _section_is_mechanism(
+        title="How carbon pricing changes investment",
+        archetype="Background", use_archetype=True) is False
+    # OFF-mode: routes on the literal title, unchanged.
+    assert _section_is_mechanism(
+        title="Mechanism", archetype="", use_archetype=False) is True
+    assert _section_is_mechanism(
+        title="How carbon pricing changes investment",
+        archetype="", use_archetype=False) is False
+    # Primary-eligibility dual path.
+    assert _section_is_primary_eligible(
+        title="Comparing alternatives", archetype="Quantitative-Comparison",
+        use_archetype=True) is True
+    assert _section_is_primary_eligible(
+        title="Efficacy", archetype="", use_archetype=False) is True
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-6 fail-loud (malformed planner JSON raises — no clause-splitter fallback).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_6_malformed_planner_raises() -> None:
+    def bad(prompt):
+        return "I cannot produce JSON, here is prose instead."
+
+    with pytest.raises(PlannerError):
+        plan_research("anything", planner_llm=bad)
+
+    def half(prompt):
+        return '{"frame": {"claim_type": "empirical"}}'  # no sub_queries
+
+    with pytest.raises(PlannerError):
+        plan_research("anything", planner_llm=half)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-7 honest count (upper truncate; lower retry-then-accept; no padding).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_7_honest_count_upper_and_lower() -> None:
+    # Upper: 60 -> <= 40.
+    big = make_fake_planner(n_subqueries=60)
+    plan_big = plan_research("broad question", planner_llm=big)
+    assert len(plan_big.sub_queries) <= DEFAULT_MAX_SUBQUERIES == 40
+
+    # Lower: first call 5, retry call 6 -> accept honest small count (NOT 20).
+    small = make_fake_planner(n_subqueries=5, second_n=6)
+    plan_small = plan_research("narrow question", planner_llm=small)
+    assert small.state["calls"] == 2  # the retry fired
+    assert len(plan_small.sub_queries) == 6  # honest, not padded
+    assert len(plan_small.sub_queries) < MIN_SUBQUERIES
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-8 gap-19 plan pin (canonical JSON, sha256-stable).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_8_plan_canonical_sha_pin_stable() -> None:
+    planner = make_fake_planner(n_subqueries=18)
+    plan = plan_research("a question", planner_llm=planner)
+    canon1 = serialize_plan_canonical(plan)
+    canon2 = serialize_plan_canonical(plan)
+    assert canon1 == canon2
+    # Canonical: sort_keys, fixed separators (no spaces).
+    assert ", " not in canon1 and '": ' not in canon1
+    assert plan_sha256(plan) == plan_sha256(plan)
+
+    # Reconstructing the same plan reproduces the identical sha256.
+    rebuilt = ResearchPlan(
+        research_question=plan.research_question,
+        frame=ResearchFrame(**dataclasses.asdict(plan.frame)),
+        sub_queries=list(plan.sub_queries),
+        outline=[SectionOutlineItem(**dataclasses.asdict(o))
+                 for o in plan.outline],
+    )
+    assert plan_sha256(rebuilt) == plan_sha256(plan)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-9 _DRUG_NAME_RE compat (clinical importers still work).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_9_drug_name_re_compat() -> None:
+    from src.polaris_graph.nodes.scope_gate import (
+        _DRUG_NAME_RE,
+        extract_pico_heuristic,
+    )
+    # Still importable + functional from scope_gate.
+    assert _DRUG_NAME_RE.search("semaglutide reduces HbA1c") is not None
+    pico = extract_pico_heuristic("tirzepatide in adults with type 2 diabetes")
+    assert pico["intervention"] == "tirzepatide"
+
+    # The two clinical importers (completeness_checker in nodes,
+    # contradiction_detector in retrieval) still import `_DRUG_NAME_RE` from
+    # scope_gate via function-scoped imports (verified by source inspection so
+    # this stays robust to where the symbol is referenced).
+    import inspect
+    from src.polaris_graph.nodes import completeness_checker
+    from src.polaris_graph.retrieval import contradiction_detector
+    cc_src = inspect.getsource(completeness_checker)
+    cd_src = inspect.getsource(contradiction_detector)
+    assert "from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE" in cc_src
+    assert "from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE" in cd_src
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-10 no-clinical-literal code guard (ON-PATH scoped).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_10_no_clinical_literal_in_on_path() -> None:
+    import inspect
+    from src.polaris_graph.planning import research_planner
+    from src.polaris_graph.generator import multi_section_generator as gen
+
+    clinical_terms = [
+        "tirzepatide", "semaglutide", "hba1c", '"efficacy"', '"safety"',
+        '"dose response"',
+    ]
+    # The whole planner module is on-path; it must carry no clinical literal.
+    planner_src = inspect.getsource(research_planner).lower()
+    for term in clinical_terms:
+        assert term not in planner_src, f"planner has clinical literal {term}"
+
+    # The on-mode generator helpers (archetype assignment, fallback, dual-path
+    # routing, advisory selector) must carry no clinical literal as a control.
+    for fn in (
+        gen._assign_evidence_to_planned_outline,
+        gen._build_archetype_fallback_outline,
+        gen._section_is_primary_eligible,
+        gen._section_is_mechanism,
+        gen.select_advisory_prompt_text,
+    ):
+        src = inspect.getsource(fn).lower()
+        for term in ("tirzepatide", "semaglutide", "hba1c"):
+            assert term not in src, f"{fn.__name__} has clinical literal {term}"
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-11 spend-free guard (no OpenRouterClient / live httpx client built).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_11_no_live_client_constructed(monkeypatch) -> None:
+    import src.polaris_graph.llm.openrouter_client as orc
+
+    constructed = {"n": 0}
+    real_init = orc.OpenRouterClient.__init__
+
+    def _tripwire(self, *args, **kwargs):
+        constructed["n"] += 1
+        return real_init(self, *args, **kwargs)
+
+    monkeypatch.setattr(orc.OpenRouterClient, "__init__", _tripwire)
+
+    # Block httpx client construction too.
+    real_import = builtins.__import__
+
+    def _no_httpx(name, *args, **kwargs):
+        if name == "httpx" and constructed.get("allow_httpx") is not True:
+            # Allow the import itself (other modules import it at load), but
+            # the planner path must not instantiate a client. We only trip on
+            # OpenRouterClient construction below.
+            pass
+        return real_import(name, *args, **kwargs)
+
+    monkeypatch.setattr(builtins, "__import__", _no_httpx)
+
+    planner = make_fake_planner(n_subqueries=16)
+    plan = plan_research("spend-free question", planner_llm=planner)
+    # Assign evidence to the plan outline (on-mode outline path is LLM-free).
+    ev = [{"evidence_id": f"ev_{i:03d}", "statement": "s"} for i in range(1, 13)]
+    plans = _assign_evidence_to_planned_outline(plan.outline, ev)
+    assert plans
+    assert constructed["n"] == 0, "an OpenRouterClient was constructed on-path"
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-12 outline handoff (planner titles + archetypes survive; ev_ids assigned).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_12_outline_handoff_assigns_ev_ids() -> None:
+    outline = [
+        SectionOutlineItem("Decision",
+                           "Which carbon-pricing path minimizes cost", 6),
+        SectionOutlineItem("Background", "How carbon pricing works", 8),
+    ]
+    ev = [{"evidence_id": f"ev_{i:03d}", "statement": "s"}
+          for i in range(1, 13)]
+    plans = _assign_evidence_to_planned_outline(outline, ev)
+    # The section STRUCTURE is the planner's titles + archetypes.
+    assert [p.title for p in plans] == [
+        "Which carbon-pricing path minimizes cost", "How carbon pricing works",
+    ]
+    assert [p.archetype for p in plans] == ["Decision", "Background"]
+    # Each section's ev_ids come from the retrieved pool (not invented).
+    pool_ids = {e["evidence_id"] for e in ev}
+    for p in plans:
+        assert p.ev_ids
+        assert all(e in pool_ids for e in p.ev_ids)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-13 archetype preserved through copy/rebuild.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_13_archetype_preserved_on_rebuild() -> None:
+    plan = SectionPlan(
+        title="How carbon pricing changes investment",
+        focus="focus", ev_ids=["ev_001", "ev_002"], archetype="Mechanism",
+    )
+    # M-44 inject pass-through rebuild preserves archetype (no anchors -> the
+    # non-eligible branch rebuilds the SectionPlan verbatim).
+    updated, _log = _m44_inject_primaries_into_outline(
+        plans=[plan],
+        primary_ev_ids_by_anchor={},
+        max_ev_per_section=30,
+    )
+    assert updated[0].archetype == "Mechanism"
+    assert updated[0].title == "How carbon pricing changes investment"
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-14 validator adapter (frame tokens keep on-scope; off-scope dropped).
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_14_validator_adapter_frame_tokens() -> None:
+    frame = ResearchFrame(
+        entities=["carbon", "pricing", "investment"],
+        relations=["affects"], metrics=["cost", "emissions"],
+        comparators=["cap-and-trade"], constraints=["Canada"],
+        claim_type="policy-comparison",
+    )
+    proto = frame.to_anchor_protocol("How does carbon pricing affect investment?")
+    res = validate_amplified_queries(
+        [
+            "carbon pricing investment cost emissions Canada",
+            "best vacation beaches tropical island resorts",
+        ],
+        proto, floor=0.1,
+    )
+    assert any("carbon" in q.lower() for q in res.kept)
+    assert any("vacation" in d[0].lower() for d in res.dropped)
+
+    # A clinical PICO protocol validates byte-identically (the additive frame
+    # merge does not change PICO behavior).
+    pico = {
+        "research_question": "semaglutide weight loss efficacy",
+        "population": "adults", "intervention": "semaglutide",
+        "comparator": "placebo", "outcome": "weight loss",
+    }
+    toks = _build_anchor_tokens(pico)
+    assert "semaglutide" in toks and "placebo" in toks
+    # No frame keys present -> bag identical to the legacy PICO-only set.
+    legacy = set()
+    for f in ("research_question", "population", "intervention",
+              "comparator", "outcome"):
+        from src.polaris_graph.retrieval.scope_query_validator import _tokenize
+        legacy |= _tokenize(str(pico[f]))
+    assert toks == legacy
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-15 on-mode suppresses legacy domain expanders.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_15_on_mode_suppresses_legacy_expanders() -> None:
+    from src.polaris_graph.retrieval.query_decomposer import (
+        build_amplified_query_list,
+    )
+    # The sweep's ON-mode amplified list is fed planner sub-queries ONLY:
+    # regulatory / trial / hand_authored all empty.
+    planner = make_fake_planner(n_subqueries=15)
+    plan = plan_research("a broad question", planner_llm=planner)
+    on_amplified = build_amplified_query_list(
+        hand_authored=[], decomposed=list(plan.sub_queries),
+        regulatory=[], trial=[],
+    )
+    assert set(on_amplified) == set(plan.sub_queries)
+
+    # OFF-mode: legacy expanders' queries DO appear.
+    off_amplified = build_amplified_query_list(
+        hand_authored=["hand q one alpha"], decomposed=["decomp q two beta"],
+        regulatory=["reg q three site:fda.gov"], trial=["trial q four surpass"],
+    )
+    assert "hand q one alpha" in off_amplified
+    assert "reg q three site:fda.gov" in off_amplified
+    assert "trial q four surpass" in off_amplified
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-16 on-mode bypasses the domain_backends router.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_16_on_mode_bypasses_domain_backends(monkeypatch) -> None:
+    from src.polaris_graph.retrieval import live_retriever
+    from src.polaris_graph.retrieval import domain_backends
+
+    cap = CaptureSearch()
+    monkeypatch.setattr(live_retriever, "_serper_search", cap.serper)
+    monkeypatch.setattr(live_retriever, "_s2_bulk_search", cap.s2)
+
+    spy = {"calls": 0}
+
+    def _spy_run_domain_backends(**kwargs):
+        spy["calls"] += 1
+        raise AssertionError("run_domain_backends must NOT be invoked on-mode")
+
+    monkeypatch.setattr(domain_backends, "run_domain_backends",
+                        _spy_run_domain_backends)
+
+    planner = make_fake_planner(n_subqueries=12)
+    plan = plan_research("a question", planner_llm=planner)
+    protocol = plan.frame.to_anchor_protocol("a question")
+
+    # ON-mode passes domain=None -> the per-domain router is never entered.
+    live_retriever.run_live_retrieval(
+        research_question="a question",
+        amplified_queries=list(plan.sub_queries),
+        protocol=protocol, max_serper=2, max_s2=2, fetch_cap=4,
+        enable_openalex_enrich=False, enable_prefetch_filter=False,
+        domain=None,
+    )
+    assert spy["calls"] == 0
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P1-17 on-mode disables R-6 domain-YAML completeness expansion.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_p1_17_on_mode_disables_r6_domain_yaml_expansion() -> None:
+    # The sweep gate computes `enable_expansion = base_env AND not on_mode`.
+    # Mirror that boolean: when the planner is on, R-6 domain-yaml expansion is
+    # disabled regardless of the base env flag.
+    def enable_expansion(env_on: bool, use_planner: bool) -> bool:
+        return env_on and not use_planner
+
+    assert enable_expansion(env_on=True, use_planner=True) is False
+    assert enable_expansion(env_on=True, use_planner=False) is True
+    assert enable_expansion(env_on=False, use_planner=True) is False
+
+    # And the sweep source actually gates R-6 expansion on the planner flag.
+    import inspect
+    import scripts.run_honest_sweep_r3 as sweep
+    src = inspect.getsource(sweep.run_one_query)
+    assert "not _use_research_planner" in src
+    assert "enable_expansion" in src
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# Supplementary: advisory prompt-text selector is config-driven + advisory.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def test_advisory_selector_config_driven() -> None:
+    # The selector is config-driven and fail-soft. Phase 1 deliberately maps
+    # NO claim_type to a family (claim_type alone cannot identify a clinical
+    # question — `empirical` is shared by physics/battery/etc.), so every
+    # claim_type returns "" until an entity-triggered mapping lands later.
+    # This proves the seam exists and is literal-free without shipping the
+    # wrong `empirical -> clinical` trigger.
+    assert select_advisory_prompt_text("empirical") == ""
+    assert select_advisory_prompt_text("forecast") == ""
+    assert isinstance(select_advisory_prompt_text("mechanism"), str)
+    # OFF byte-identity: the legacy allowed-section list is unchanged.
+    assert _ALLOWED_SECTIONS[0] == "Efficacy"
```
