HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding. Same quality bar.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; P2/P3 for the rest.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1. Verdict APPROVE iff zero P0 AND zero P1.

Output the §8.3.9 YAML verdict FIRST:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Codex BRIEF gate — I-meta-005 Phase 2 (#986): source discovery by NEED-TYPE (not domain)

Reviewing ACCEPTANCE-CRITERIA correctness. Parent plan #982 row 48. Phase 2 closes gap #4 (source reach).
Phase 1 (#985, merged PR #998) on-mode currently passes `domain=None` into `run_live_retrieval`, BYPASSING
`run_domain_backends` entirely — so on-mode discovery is generic Serper/S2 fan-out only. Phase 2 replaces the
bypassed domain switch with a field-agnostic need-type registry so on-mode regains issuer-class breadth
WITHOUT a domain enum.

## 0. HARD CONSTRAINTS (operator-locked — NOT Codex-consultable; do not offer the relaxed option)
- **NO `if domain ==` / domain enum / clinical literal as a control value on the on-path.** EXIT requires
  the on-path `if domain ==` count = 0. Discovery is keyed on DECLARED EVIDENCE-NEED + extracted
  JURISDICTION, both from the planner frame — never a domain.
- **OFF byte-identical.** Gated on the existing `PG_USE_RESEARCH_PLANNER` (default off). Off = the current
  `domain_backends.run_domain_backends` `if domain ==` switch + US-only `_POLICY_SITE_FILTERS`, byte-for-
  byte (legacy code retained + selected when off). On = the need-type registry.
- **BUILD + SMOKE spend-free.** All discovery adapters (arxiv/github/sec_edgar/europe_pmc/serper/OpenAlex/
  S2) are injected/stubbed in tests; smoke asserts no live HTTP client constructed.
- **Sovereignty (narrow, LLM-path only — unchanged):** discovery adapters may call non-US data APIs; the
  sovereignty lock is only the LLM inference path. No change here.

## 1. THE PROBLEM (grounded in running code)
- `retrieval/domain_backends.py:443-457` `run_domain_backends` routes with `if domain == "tech"`
  (arxiv+github) / `"policy"` (policy_targeted_serper) / `"due_diligence"` (sec_edgar) / `"clinical"`
  (europe_pmc) — a 4-branch DOMAIN enum switch. A question outside those 4 domains gets NO specialized
  issuer-class discovery.
- `domain_backends.py:150-161` `_POLICY_SITE_FILTERS` is a US-only gov allowlist (federalregister/fda/cms/
  hhs/ftc/sec/treasury + ema/nice) — wrong for a CA/JP/EU/AU question; a hard frame.

## 2. THE BUILD (behind PG_USE_RESEARCH_PLANNER; field-agnostic registry)

### 2.1 EVIDENCE-NEED taxonomy + planner emission (additive)
- A field-invariant `EvidenceNeed` enum: `primary_literature`, `regulatory`, `legal`, `statistical`,
  `code`, `open_web`. NO domain. The planner (`research_planner.plan_research`) emits an additive
  `evidence_needs: list[str]` on the `ResearchFrame` (and/or per sub-query) — the Writer declares WHAT KINDS
  of evidence the question needs (a physics question → primary_literature+code; a housing-policy question →
  regulatory+statistical+legal+open_web). Additive field, default `[]` → OFF unaffected.

### 2.2 NEW `src/polaris_graph/discovery/source_adapter_registry.py`
- A registry mapping each `EvidenceNeed` → a set of discovery adapter callables (the EXISTING functions,
  re-keyed off the need, NOT the domain): primary_literature → OpenAlex + S2 + arxiv + europe_pmc; code →
  github; regulatory/legal/statistical → jurisdiction-scoped gov/issuer discovery (see 2.4); open_web →
  Serper. Adapters are registered by need-type; the registry has NO domain literal. Each adapter is an
  injected callable so tests stub them.

### 2.3 NEW `src/polaris_graph/discovery/need_type_router.py`
- `route_needs_to_adapters(frame) -> list[adapter]`: reads `frame.evidence_needs` (field-agnostic) and
  returns the union of adapters for those needs, deduped. NO `if domain ==`. If `evidence_needs` is empty
  (older plan), fall back to {primary_literature, open_web} (the safe generic set) — never to a domain.

### 2.4 `domain_backends.py` refactor (dual path)
- ON-mode: `run_domain_backends` is replaced on the on-path by the need-type registry dispatch
  (`route_needs_to_adapters(frame)` → run those adapters). The `if domain ==` switch is NOT reached on-mode
  → on-path `if domain ==` count = 0. OFF-mode: the legacy `if domain ==` switch runs byte-identical.
- **Jurisdiction-scoped gov discovery (replaces US-only `_POLICY_SITE_FILTERS`):** the regulatory/legal/
  statistical adapters scope their `site:` filters to the jurisdiction(s) extracted into the frame
  (`frame.constraints`/jurisdiction) via the Phase-0a PSL gov-suffix data (`config/authority/
  psl_gov_suffixes.txt`) — e.g. a CA question → `site:*.gc.ca`/`canada.ca`; a JP question → `site:*.go.jp`.
  NO hard-coded US agency list on the on-path. Off-path keeps `_POLICY_SITE_FILTERS`.

### 2.5 Wiring into the sweep
- `run_honest_sweep_r3.py` on-mode (Phase 1 set `domain=None` to bypass `run_domain_backends`): now passes
  the frame's `evidence_needs` + jurisdiction so the need-type registry runs the right adapters. Off-mode:
  unchanged (`domain=q["domain"]` → legacy switch).

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4) — `tests/polaris_graph/discovery/test_source_discovery_phase2.py`
- **P2-1 OFF byte-identity:** off → `run_domain_backends` `if domain ==` switch selects the same adapters as
  pre-Phase-2 for tech/policy/due_diligence/clinical (pin the selected-adapter set per domain).
- **P2-2 need-type routing (the field-agnostic core):** stub adapters; a frame with
  `evidence_needs=[primary_literature, code]` → exactly {OpenAlex,S2,arxiv,europe_pmc,github} adapters
  selected, NO domain consulted.
- **P2-3 EXIT issuer-class breadth:** a NON-CLINICAL frame (housing-policy: regulatory+statistical+legal+
  open_web) → ≥3 DISTINCT authoritative issuer-classes selected (gov-regulatory, statistical-agency,
  legal-issuer). A physics frame (primary_literature+code) → ≥3 (scholarly-graph, preprint, code-host).
- **P2-4 zero `if domain ==` on-path:** a grep-style test asserts the on-mode discovery path
  (registry+router) contains no `if domain ==` / domain-enum branch; the legacy switch is whitelisted
  off-path only.
- **P2-5 jurisdiction-scoped gov:** a CA-jurisdiction frame → regulatory adapter emits `*.gc.ca`/`canada.ca`
  site filters (from PSL suffixes), NOT US `_POLICY_SITE_FILTERS`; a JP frame → `*.go.jp`. US-only filter
  appears only off-path.
- **P2-6 empty-needs fallback:** a frame with `evidence_needs=[]` → {primary_literature, open_web} (safe
  generic), never a domain.
- **P2-7 spend-free:** no live HTTP client constructed; adapters are the injected stubs.
- Plus a regression subset confirming OFF byte-identity didn't break existing domain_backends tests.

## 4. EXIT CRITERIA (issue #986)
On-path `if domain ==` count = 0; a non-clinical question reaches ≥3 distinct authoritative issuer-classes;
OFF byte-identical; jurisdiction-scoped gov discovery (no US-only frame on-path); all smoke green; spend-free.

## 5. WHAT I HAVE ALSO CHECKED
- Phase 1 on-mode `domain=None` bypass (`run_honest_sweep_r3.py`) is the hook Phase 2 fills with the registry.
- `_POLICY_SITE_FILTERS` (`:150-161`) US-only — replaced on-path by PSL-suffix jurisdiction scoping (Phase-0a
  `psl_gov_suffixes.txt` already in repo).
- The discovery adapters (arxiv_search/github_search_repos/sec_edgar_search/europe_pmc_search/
  policy_targeted_serper) are reused, re-keyed by need-type — no adapter logic rewrite.

## 6. REVIEW QUESTIONS FOR CODEX
1. Is "planner emits `evidence_needs`" the right field-agnostic source of need-type, vs. inferring need from
   the frame in the router? (Planner-emitted avoids a heuristic; but is an additive frame field + a planner-
   prompt change the right cut for Phase 2, or should the need-inference live in need_type_router?)
2. Is the EvidenceNeed taxonomy (6 needs) complete enough for "any field, any region," or missing a class
   (e.g. news/press, datasets, standards-bodies)?
3. Is PSL-suffix jurisdiction scoping the right replacement for `_POLICY_SITE_FILTERS`, and does it correctly
   reuse the Phase-0a authority data without a new allowlist?
4. Is the empty-needs fallback to {primary_literature, open_web} safe (never a domain), and is "≥3 issuer-
   classes" the right EXIT measure offline (with stubbed adapters)?
5. Scope: is need-type discovery the right Phase-2 boundary, with multi-round saturation (Phase 4) and
   relevance-floor/dedup (Phase 5) still separate?

APPROVE iff the acceptance criteria are correct, the no-domain-enum/field-agnostic lock holds, OFF stays
byte-identical, and the spend-free offline build is sound. This is the build contract.
