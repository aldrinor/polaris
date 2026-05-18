# Codex ARCHITECTURE CONSULT — I-rdy-008 (#504) slice 7: the evidence-pool / EvidencePane migration is blocked

This is a **decision consult**, not a brief/diff gate review. Investigate the
repo, then return a verdict + a slice decomposition. Decide in ONE pass —
front-load the full reasoning; do not drip-feed.

## 1. Context

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI"). Per your
earlier arch-decision consult (`.codex/I-rdy-008/arch_decision_verdict.txt`,
verdict A: serve the faithful `AuditIR`; do NOT wholesale-mount the legacy
1400-line `polaris_graph/audit_ir/inspector_router.py`), the inspector page
is being migrated tab-by-tab onto `getAuditRun()` / `AuditIrRun`. Slices 1-6
merged (PR #590-#595): v6 route, frontend types, shell + Executive-summary,
verified-sentences, frame-coverage, contradictions tabs.

Slice 7 was scoped as "migrate `PoolTab` + `EvidencePane` off `getBundle()`/
`EvidenceContract`." Grounding for slice 7 surfaced a blocker that the
verdict-A 12-slice decomposition did not anticipate. **This consult decides
how to resolve it.**

## 2. The blocker — grounded against `polaris` HEAD `06fbf61a`

1. **`getBundle()` is golden-fixture-only.** `web/lib/api.ts` `getBundle()`
   → `GET /runs/{run_id}/bundle`. That route (`src/polaris_v6/api/bundle.py`)
   serves a hardcoded `_GOLDEN_RUN_INDEX` of 7 run_ids → static fixture JSON
   files under `tests/v6/fixtures/evidence_contract_v1/`; **for any other
   run_id it raises HTTPException(404)**. So `getBundle()` returns data only
   for 7 golden fixtures — never for a live run.
2. **The inspector page is therefore golden-fixture-only RIGHT NOW.**
   `web/app/inspector/[runId]/page.tsx` (post-slice-6) dual-fetches
   `getAuditRun()` + `getBundle()` and gates its whole body on
   `{ir && bundle && (...)}` (added slice 3). For a live run `getAuditRun()`
   succeeds (the slice-1 route resolves run_id → artifact_dir →
   `load_audit_ir()` for any completed live run) but `getBundle()` 404s →
   `bundle` stays `null` → the body is hidden and the error panel renders.
   **#504's stated goal — "wire LIVE runs into the rich UI" — is not met by
   slices 1-6 and cannot be met by a frontend-only slice 7. The page only
   works for the 7 golden fixtures.**
3. **AuditIR carries no evidence span text.** `PoolTab` + `EvidencePane`
   display the exact verified source span — `SourceSpan.span_text` (the
   ≤500-char cited span), `span_start`/`span_end` char offsets, `source_url`,
   `source_tier`. This is the F5 clinical-audit core: an auditor verifies a
   claim against the exact cited span. The faithful `AuditIR`
   (`src/polaris_graph/audit_ir/loader.py`) has **no span text anywhere** —
   `BibliographyEntry` is `{num, evidence_id, statement, tier, url}`;
   `statement` is a one-line bibliography statement, NOT the verified span.
   `verification_details.json` sentences carry `tokens`
   (`{evidence_id, start, end}` — char offsets) but the loader resolves no
   evidence *text* for those offsets to index into.
4. **Candidate span sources checked and ruled out:**
   - `live_corpus_dump.json` (in every run artifact_dir) — a list of corpus
     *sources*: `{domain, tier, tier_confidence, tier_reasons, title, url}`.
     No `evidence_id`, no span text. It is the retrieved-source list, not an
     evidence-pool-with-text.
   - `bibliography.json` → `AuditIrBibliographyEntry` — no span text.
5. **Cascading consumers of `getBundle()`** (so "remove getBundle()" is not
   just PoolTab/EvidencePane): the `SentencesTab` contradiction-in-section
   badge reads `bundle.contradictions[].section_id`; the "Export bundle
   JSON" header button calls `downloadBundleAsJson(bundle)`; `evidenceById`
   resolves `bundle.evidence_pool`.

## 3. The rejected option (for completeness)

**Option A — frontend-only: migrate `EvidencePane`/`PoolTab` to
`ir.bibliography`, show `statement` instead of the verified span, drop
`getBundle()`.** This makes the page work for live runs in one frontend
slice — but it **silently degrades the clinical-audit core**: `statement`
is not the verified ≤500-char span an auditor checks a claim against.
POLARIS `CLAUDE.md` §-1.1 (clinical line-by-line audit standard) + LAW II
(no silent downgrade) forbid this. **Do not pick A.** It is named only so
you can confirm the rejection.

## 4. What this consult must decide

**Investigate the repo** (you can read any file) and return:

1. **WHERE the per-evidence verified span text lives for a LIVE run** — if
   anywhere. Trace it: `strict_verify` consumes evidence spans to verify
   sentences against `[#ev:id:start-end]` tokens; the golden
   `EvidenceContract` fixtures have a populated `evidence_pool: SourceSpan[]`
   with `span_text`. For a real sweep run, what artifact (if any) in the run
   `artifact_dir` holds the evidence-id → span-text mapping? Check the
   pipeline-A generator/verifier (`src/polaris_graph/generator/`,
   `clinical_generator/strict_verify.py`, `provenance.py`) and the sweep
   runner. If the span text is NOT persisted as a clean artifact for live
   runs, say so explicitly — that materially changes the decomposition.

2. **The decomposition** to finish #504 without degrading any audit surface.
   The proposed split is:
   - **slice 7a (backend):** make the per-evidence verified spans available
     on the live-run AuditIR path — either extend `load_audit_ir()` /
     `AuditIR` with an evidence-pool block, or add a v6 facade route
     (e.g. `GET /api/inspector/runs/{id}/evidence`). If 7a depends on a
     generator/verifier change to PERSIST spans first (because they aren't
     persisted today), call that out as slice 7a-pre.
   - **slice 7b (frontend):** migrate `PoolTab` + `EvidencePane` onto 7a;
     drop `getBundle()`; flip the page gate `ir && bundle` → `ir &&` so the
     page works for live runs; resolve the cascading consumers (SentencesTab
     badge, Export button, `evidenceById`).
   Confirm this split, or propose a better one. Specify each slice's exact
   scope and ordering.

3. **The `getBundle()` removal call:** can it be fully removed at 7b, or
   must the page keep a bundle path for the 7 golden fixtures (e.g. for
   tests/demos)? Rule.

4. **Sanity-check the 6 merged slices:** slices 3-6 migrated rendering to
   AuditIR but kept the `ir && bundle` gate. Was that the right incremental
   path, or should the gate have been `ir &&`-only from slice 3 (so the
   page worked for live runs as each tab migrated)? This is for the
   trajectory record — no rework is proposed, but confirm whether the merged
   slices are sound.

## 5. Output — required schema

```yaml
verdict: <one-paragraph decision>
span_text_source_for_live_runs: <file/artifact, or "not persisted — needs generator change">
decomposition:
  - slice: 7a (or 7a-pre / 7a)
    layer: backend
    scope: <exact scope>
  - slice: 7b
    layer: frontend
    scope: <exact scope>
  - <any further slices>
getbundle_removal: <full removal at 7b | keep golden-fixture path | other>
merged_slices_1_6_sound: <yes | yes-with-note: ... | no: ...>
risks: [...]
```
