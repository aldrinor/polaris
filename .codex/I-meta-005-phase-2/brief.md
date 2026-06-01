HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
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

# Codex BRIEF gate iter 4 — I-meta-005 Phase 2 (#986): source discovery by NEED-TYPE (not domain)

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
- A field-invariant `EvidenceNeed` enum (10, iter-2 — adds `company_filings` so the legacy
  due_diligence/sec_edgar capability is NOT lost): `primary_literature`, `regulatory`, `legal`,
  `statistical`, `standards`, `datasets`, `news_press`, `company_filings`, `code`, `open_web`. NO domain.
  (`standards` = engineering/ISO/IEC bodies; `datasets` = official data portals; `news_press` = current
  institutional statements; `company_filings` = securities/company filings, e.g. SEC EDGAR and
  jurisdiction equivalents — so "any field" questions reach the right authoritative issuer, never a bare
  open_web fallback, and ALL FOUR legacy specialized backends [arxiv/github→code, policy→regulatory,
  sec_edgar→company_filings, europe_pmc→primary_literature] remain reachable on-mode.)
- The planner emits an additive `evidence_needs: list[str]` on the `ResearchFrame` — the Writer declares
  WHAT KINDS of evidence the question needs. Additive, default `[]` → OFF unaffected.
- **Validation (iter-1 P2):** an evidence_need value NOT in the enum is MALFORMED → fail loud (raise/record
  as a malformed-plan error), NOT silently fallback. Only a MISSING/empty `evidence_needs` (older legacy
  plan) uses the safe fallback (§2.3).

### 2.1b NORMALIZED JURISDICTION contract (iter-2 P1 #1 — required for jurisdiction_scopes.yaml)
- `ResearchFrame.constraints` is free text and carries NO normalized jurisdiction; deriving CA/JP/EU from it
  in the router would be a heuristic (the very thing we forbid) OR silently miss the scope file. So the
  planner ALSO emits an additive `jurisdictions: list[str]` of **normalized codes** (ISO-3166 alpha-2 +
  `EU`/`INTL`; e.g. `["CA"]`, `["JP","US"]`). The planner prompt specifies the code set; the parser
  VALIDATES each code's SHAPE. Semantics (iter-3 P2 — distinguish shape vs membership): **absent/empty** →
  no jurisdiction scoping (issuer-need adapters emit no site filter, open_web+scholarly only);
  **valid-shape-but-unknown** code (e.g. `"ZZ"` — a well-formed alpha-2 not present in the data file) →
  that code contributes NO scope (logged, NOT parser-fatal); **malformed SHAPE** (non-code junk, not
  `^[A-Z]{2}$`/`EU`/`INTL`) → fail loud. Additive field, default `[]` → OFF unaffected.

### 2.2 NEW `src/polaris_graph/discovery/source_adapter_registry.py`
- A registry mapping each `EvidenceNeed` → a set of discovery adapter callables (the EXISTING functions,
  re-keyed off the NEED, NOT the domain), covering ALL 10 needs:
  - `primary_literature` → OpenAlex-SEARCH (the /works keyword-search discovery adapter, DISTINCT
    from the existing OpenAlex enrichment /works/{id} path — iter-3 P2) + S2 + arxiv + europe_pmc
  - `code` → github
  - `company_filings` → sec_edgar (+ jurisdiction-scoped issuer-filing sites from 2.4 for non-US, e.g.
    `sedarplus.ca`) — **keeps the legacy due_diligence/sec_edgar capability reachable on-mode (iter-2 P1 #2)**
  - `regulatory` / `legal` / `statistical` / `standards` → jurisdiction-scoped gov/issuer/standards discovery
    via `jurisdiction_scopes.yaml` (see 2.4); `standards` also includes the cross-jurisdiction bodies
    (iso.org, iec.ch) from the scope file's `INTL` key
  - `datasets` → official data-portal scopes (jurisdiction `datasets` entries, e.g. `data.gov`,
    `open.canada.ca`) from the scope file
  - `news_press` → institutional-press discovery (the issuer's own newsroom via jurisdiction scopes) +
    Serper; NOT a generic-news allowlist
  - `open_web` → Serper
  Adapters are registered by need-type; the registry has NO domain literal. Each adapter is an injected
  callable so tests stub them.

### 2.3 NEW `src/polaris_graph/discovery/need_type_router.py`
- `route_needs_to_adapters(frame) -> list[adapter]`: reads `frame.evidence_needs` (field-agnostic) and
  returns the union of adapters for those needs, deduped. NO `if domain ==`. If `evidence_needs` is empty
  (older plan), fall back to {primary_literature, open_web} (the safe generic set) — never to a domain.

### 2.4 `domain_backends.py` refactor (dual path)
- ON-mode: `run_domain_backends` is replaced on the on-path by the need-type registry dispatch
  (`route_needs_to_adapters(frame)` → run those adapters). The `if domain ==` switch is NOT reached on-mode
  → on-path `if domain ==` count = 0. OFF-mode: the legacy `if domain ==` switch runs byte-identical.
- **Jurisdiction-scoped gov discovery — NEW versioned data contract (iter-1 P1 fix):** the flat
  `config/authority/psl_gov_suffixes.txt` is a DNS-suffix pre-filter and CANNOT produce `canada.ca`/
  statistical-agency/legal-issuer scopes (its own header says so: "a gov-style suffix MISSES canada.ca …
  resolve via ROR institution-type"). So Phase 2 adds a NEW versioned data file
  `config/discovery/jurisdiction_scopes.yaml` (with `schema_version`, `provenance`, `fetch_date`, and a
  `config/discovery/VERSION` — iter-3 P2), mapping each jurisdiction code (US/CA/GB/EU/JP/AU/… ; extensible
  by editing the DATA, not code) → per-need `site:` scope arrays covering ALL SCOPED needs (iter-3 P1 #1):
  `{regulatory: [...], legal: [...], statistical: [...], standards: [...], company_filings: [...],
  datasets: [...], news_press: [...]}` (e.g. CA → regulatory `canada.ca`,`*.gc.ca`; statistical
  `statcan.gc.ca`; legal `canlii.org`,`laws-lois.justice.gc.ca`; company_filings `sedarplus.ca`; datasets
  `open.canada.ca`; news_press the issuer newsroom). A `INTL` key holds cross-jurisdiction bodies
  (iso.org/iec.ch for standards). A scoped need with NO entry for a jurisdiction → no scope for that need
  (never collapses silently to a fabricated default; logged). The
  regulatory/legal/statistical/standards adapters read THIS file scoped to the jurisdiction(s) the planner
  extracted into the frame. Provenance + fetch_date + VERSION in the file (LAW VI: knowledge in versioned
  DATA, zero on-path host literals in code). Unknown/absent jurisdiction → those issuer-need adapters emit
  NO site filter (fall back to open_web + scholarly), never a fabricated/US-default scope. Off-path keeps
  the legacy US-only `_POLICY_SITE_FILTERS` byte-identical.

### 2.5 Wiring into the sweep + ON-MODE COMPOSITION (iter-3 P1 #2 — pin the actual invocation)
- **Composition (explicit baseline + need-keyed adds):** `run_live_retrieval` runs the CORE Serper+S2
  search over the planner sub-queries (`live_retriever.py:1728`) — this is the ALWAYS-ON baseline open-web +
  scholarly search of the actual queries (the universal {open_web, primary_literature(S2)} needs), UNCHANGED
  and intentional. The need-type registry REPLACES `run_domain_backends` (`:1795`) and ADDS the SPECIALIZED
  issuer-class adapters for the frame's declared needs BEYOND that baseline: primary_literature →
  arxiv+europe_pmc+OpenAlex-search (S2 already in core); code → github; company_filings → sec_edgar/issuer;
  regulatory/legal/statistical/standards/datasets/news_press → jurisdiction-scoped Serper site-queries (a
  DIFFERENT query than the core, so no double-count). So a `code`-only frame's ACTUAL on-mode discovery =
  core Serper+S2-over-sub-queries (baseline) + github (the declared need) — pinned, not "open-web leaking
  outside the need set."
- `run_honest_sweep_r3.py` on-mode (Phase 1 set `domain=None`): passes `evidence_needs` + normalized
  `jurisdictions` so the registry runs the right specialized adapters with the right jurisdiction scopes.
  Off-mode: unchanged (`domain=q["domain"]` → legacy switch).
- **Pin order/dedupe/caps/api_calls:** the on-mode path preserves the existing dedupe-by-URL, per-backend
  caps, and `api_calls` accounting; the registry adapters' candidates merge into the same candidate list
  with the same dedupe/cap discipline.

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4) — `tests/polaris_graph/discovery/test_source_discovery_phase2.py`
- **P2-1 OFF byte-identity (strengthened, iter-1 P2):** off → `run_domain_backends` is byte-identical to
  pre-Phase-2 across ALL observable behavior, not just adapter selection: the selected-adapter set per
  domain, the query set + ORDER, the `_POLICY_SITE_FILTERS` text + order, the dedupe-by-URL order,
  `backends_used` + `per_backend_counts`, the unknown-domain empty-result behavior, AND the clinical
  Europe-PMC `PG_CLINICAL_EUROPE_PMC` kill-switch. Pin all of these on the frozen fixture.
- **P2-2 need-type routing (the field-agnostic core):** stub adapters; a frame with
  `evidence_needs=[primary_literature, code]` → exactly {OpenAlex,S2,arxiv,europe_pmc,github} adapters
  selected, NO domain consulted.
- **P2-3 EXIT issuer-class breadth:** a NON-CLINICAL frame (housing-policy: regulatory+statistical+legal+
  open_web) → ≥3 DISTINCT authoritative issuer-classes selected (gov-regulatory, statistical-agency,
  legal-issuer). A physics frame (primary_literature+code) → ≥3 (scholarly-graph, preprint, code-host).
- **P2-4 zero `if domain ==` on-path (whole-wiring, iter-1 P2):** a grep-style test asserts the ENTIRE
  on-mode discovery wiring — the registry + router AND the sweep/`live_retriever` seam that invokes them —
  consults NO `q["domain"]` and takes no domain-derived branch on-mode (not only the new files). The legacy
  `if domain ==` switch + `q["domain"]` read are whitelisted OFF-path only.
- **P2-5 jurisdiction-scoped gov (from the new data file, iter-1 P1):** a CA-jurisdiction frame → the
  regulatory/statistical/legal adapters emit the CA scopes from `config/discovery/jurisdiction_scopes.yaml`
  (`canada.ca`,`*.gc.ca`,`statcan.gc.ca`,`canlii.org`), NOT US `_POLICY_SITE_FILTERS`; a JP frame → the JP
  scopes; an unknown jurisdiction → NO site filter (open_web + scholarly only). US-only `_POLICY_SITE_FILTERS`
  appears only off-path. Also pin `config/discovery/VERSION` (or the file's VERSION field) is present.
- **P2-6 empty-needs fallback:** a frame with `evidence_needs=[]` → {primary_literature, open_web} (safe
  generic), never a domain.
- **P2-7 spend-free:** no live HTTP client constructed; adapters are the injected stubs.
- **P2-8 jurisdiction contract (iter-2 P1 #1):** a frame with `jurisdictions=["CA"]` resolves CA scopes from
  `jurisdiction_scopes.yaml`; `jurisdictions=[]` → no scope (open_web+scholarly); an UNKNOWN code (e.g.
  `["ZZ"]`) → that code contributes no scope (logged, not fabricated); a MALFORMED value (non-code junk) →
  fail loud. Planner-parse validates codes against the data-file key set.
- **P2-9 company_filings reachable on-mode (iter-2 P1 #2):** a frame with `company_filings` →
  `sec_edgar` (US) selected; a non-US `company_filings`+`jurisdictions=["CA"]` → the CA issuer-filing scope.
  Proves the legacy due_diligence/sec_edgar capability is NOT lost on-mode.
- **P2-10 new-needs routing (iter-2 P2):** frames exercising `standards`, `datasets`, `news_press` each
  route to their mapped adapter/scope (standards→iso/iec + jurisdiction standards; datasets→data-portal
  scope; news_press→issuer newsroom+Serper), NOT a bare open_web fallback.
- **P2-malformed (iter-2 P2):** an explicit planner-parse/router test — a plan with an evidence_need NOT in
  the 10-enum raises/records malformed (not silent fallback); only empty `evidence_needs` → safe fallback.
- **P2-11 whole-wiring actual-invocation (iter-3 P1 #2):** stub the core Serper/S2 + every registry adapter
  (capture-only). For a `code`-only frame, assert the ACTUAL adapters invoked on-mode = {core Serper, core
  S2 (baseline over sub-queries), github} and NOTHING else (no regulatory/clinical/sec_edgar); for a
  `regulatory`+`jurisdictions=["CA"]` frame, assert the CA-scoped Serper site-queries fire. Pin the merged
  candidate dedupe-by-URL order + `api_calls` counts. This tests REAL invocation, not just router selection.
- Plus a regression subset confirming OFF byte-identity didn't break existing domain_backends tests.

## 4. EXIT CRITERIA (issue #986)
On-path `if domain ==` count = 0 (whole wiring incl. sweep seam, P2-4); a non-clinical question reaches ≥3
distinct authoritative issuer-classes (P2-3); jurisdiction-scoped gov discovery via the NEW versioned
`config/discovery/jurisdiction_scopes.yaml` (no US-only frame on-path, unknown-jurisdiction → no fabricated
scope); malformed `evidence_needs` fails loud (only empty → safe fallback); OFF byte-identical across all
observable behavior (P2-1); all smoke green; spend-free.

## 5. WHAT I HAVE ALSO CHECKED
- Phase 1 on-mode `domain=None` bypass (`run_honest_sweep_r3.py`) is the hook Phase 2 fills with the registry.
- `_POLICY_SITE_FILTERS` (`:150-161`) US-only — replaced on-path by the NEW versioned
  `config/discovery/jurisdiction_scopes.yaml` (PSL `psl_gov_suffixes.txt` stays an authority pre-filter, NOT
  the discovery-scope source — its header confirms it misses `canada.ca`).
- The discovery adapters (arxiv_search/github_search_repos/sec_edgar_search/europe_pmc_search/
  policy_targeted_serper) are reused, re-keyed by need-type — no adapter logic rewrite.

## 6. REVIEW QUESTIONS FOR CODEX
1. Is "planner emits `evidence_needs`" the right field-agnostic source of need-type, vs. inferring need from
   the frame in the router? (Planner-emitted avoids a heuristic; but is an additive frame field + a planner-
   prompt change the right cut for Phase 2, or should the need-inference live in need_type_router?)
2. Is the EvidenceNeed taxonomy (10 needs incl. company_filings/standards/datasets/news_press) complete enough for "any field, any region," or missing a class
   (e.g. news/press, datasets, standards-bodies)?
3. Is the versioned `config/discovery/jurisdiction_scopes.yaml` the right replacement for `_POLICY_SITE_FILTERS`
   (PSL stays an authority pre-filter only), and is the normalized `jurisdictions` frame contract sound?
4. Is the empty-needs fallback to {primary_literature, open_web} safe (never a domain), and is "≥3 issuer-
   classes" the right EXIT measure offline (with stubbed adapters)?
5. Scope: is need-type discovery the right Phase-2 boundary, with multi-round saturation (Phase 4) and
   relevance-floor/dedup (Phase 5) still separate?

APPROVE iff the acceptance criteria are correct, the no-domain-enum/field-agnostic lock holds, OFF stays
byte-identical, and the spend-free offline build is sound. This is the build contract.
