# Phase 2 BUILD SPEC — source discovery by need-type (#986). BINDING.

**The APPROVED brief `.codex/I-meta-005-phase-2/brief.md` (Codex APPROVE iter 5) is the detailed design
contract. Implement it EXACTLY.** This spec is the checklist + the 2 Codex iter-5 P2 build notes.

## HARD CONSTRAINTS (brief §0 — do not relax)
1. Everything behind `PG_USE_RESEARCH_PLANNER` (default off). **OFF byte-identical** — the legacy
   `run_domain_backends` `if domain ==` switch + US-only `_POLICY_SITE_FILTERS` retained + selected when off.
2. **NO `if domain ==` / domain enum / clinical literal as a control value on the on-path.** EXIT: on-path
   `if domain ==` count = 0 (whole wiring incl. sweep seam).
3. **BUILD + SMOKE spend-free** — adapters injected/stubbed; assert no live HTTP client constructed.
4. snake_case; explicit imports; no `unittest.mock` in `src/`; knowledge in versioned DATA not code literals.

## FILE-BY-FILE (implement brief §2)
1. **NEW `config/discovery/jurisdiction_scopes.yaml` + `config/discovery/VERSION`** (brief §2.4): per-need
   `site:` scope arrays per jurisdiction (regulatory/legal/statistical/standards/company_filings/datasets/
   news_press) + `INTL` (iso.org/iec.ch) + `schema_version`/`provenance`/`fetch_date`. Bootstrap US/CA/GB/
   EU/JP/AU (extensible by editing DATA). **P2-note-2: normalize wildcard entries** — store canonical hosts
   (`gc.ca`) and a documented alias rule; the adapter emits `site:gc.ca` (NOT `site:*.gc.ca`) since search
   operators handle wildcard hosts inconsistently.
2. **`src/polaris_graph/planning/research_planner.py`** (brief §2.1/2.1b): additive `evidence_needs:
   list[str]` + `jurisdictions: list[str]` on `ResearchFrame` (defaults `[]` → OFF unaffected); planner
   prompt emits both; parser validates — evidence_need NOT in the 10-enum OR jurisdiction malformed SHAPE
   (`^[A-Z]{2}$`/`EU`/`INTL`) → raise a distinct `MalformedPlanError`; valid-shape-unknown jurisdiction is
   NON-fatal (membership checked later by the scope loader). `EvidenceNeed` 10-enum.
3. **NEW `src/polaris_graph/discovery/__init__.py` + `source_adapter_registry.py`** (brief §2.2): registry
   maps each EvidenceNeed → adapter set (primary_literature → OpenAlex-search+arxiv+europe_pmc, NOT S2;
   code → github; company_filings → sec_edgar/issuer; regulatory/legal/statistical/standards/datasets/
   news_press → jurisdiction-scoped via the yaml; open_web → Serper). Injected callables. NO domain literal.
4. **NEW `src/polaris_graph/discovery/need_type_router.py`** (brief §2.3): `route_needs_to_adapters(frame)`
   → deduped adapter union for `frame.evidence_needs`; empty → {primary_literature, open_web} fallback; NO
   `if domain ==`. The scope loader resolves jurisdiction membership non-fatally (unknown code → no scope).
5. **`src/polaris_graph/retrieval/domain_backends.py`** (brief §2.4): dual path — ON-mode dispatch via the
   registry; OFF-mode the legacy `if domain ==` switch byte-identical. `_POLICY_SITE_FILTERS` off-path only.
6. **`scripts/run_honest_sweep_r3.py` + `src/polaris_graph/retrieval/live_retriever.py`** (brief §2.5):
   on-mode passes `evidence_needs` + `jurisdictions`; the registry replaces `run_domain_backends` at the
   `:1795` seam; core Serper+S2-over-sub-queries baseline UNCHANGED. **P2-note-1: validate the plan
   (evidence_needs enum + jurisdiction shape) UP-FRONT — before ANY live discovery incl. the core Serper/S2
   baseline** — so a malformed frame fails loud (MalformedPlanError) WITHOUT spending or partially populating
   candidates. Adapter/network errors stay fail-OPEN; validation errors propagate (distinct from the
   fail-open wrapper).

## SMOKE — `tests/polaris_graph/discovery/test_source_discovery_phase2.py`
Implement ALL brief cases P2-1..P2-11 + P2-malformed (serialized §8.4; plain-class stubs, no unittest.mock).
Non-relaxable: **P2-1 OFF byte-identity** (adapters+query set/order+policy-filter text/order+dedupe order+
backends_used/per_backend_counts+unknown-domain empty+Europe-PMC kill switch), **P2-4 zero `if domain ==`
whole-wiring**, **P2-11 actual-invocation** (code-only frame → {core Serper,S2,github} ONLY), **P2-malformed**
(malformed plan fails loud BEFORE any discovery, not swallowed by fail-open; assert NO core Serper/S2 call
fired). Run `python -m pytest tests/polaris_graph/discovery/ -q -p no:cacheprovider` → green; then a
domain_backends regression subset confirming OFF byte-identity.
