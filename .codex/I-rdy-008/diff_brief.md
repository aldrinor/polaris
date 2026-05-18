# Codex DIFF review — I-rdy-008 / GH #504 slice 2: frontend AuditIR client + types

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 2** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1).
**1 file, +240 — `web/lib/api.ts`.**

Slice 2 of ~12 for #504 (Option A). Frontend-lib only — adds the AuditIR
types + `getAuditRun()` client. Do NOT flag "the UI still uses `getBundle()`"
— the UI migration is slice 3.

## 2. The change

`web/lib/api.ts` gains 17 `AuditIr*` interfaces mirroring the `to_json_dict()`
projection of the `AuditIR` dataclass tree, and `getAuditRun(runId)` → the
slice-1 route `GET /api/inspector/runs/{run_id}`.

## 3. Verify

1. **Faithful 1:1 mirror of the loader shape.** Cross-check the `AuditIr*`
   interfaces against `src/polaris_graph/audit_ir/loader.py` dataclasses —
   field names + types. Especially: `AuditIrRun` top-level (`ir_schema_version`,
   `run_id`, `artifact_dir`, `report_md`, `manifest`, `bibliography`,
   `contradictions`, `frame_coverage`, `tier_mix`, `verified_report`,
   `model_provenance`, `protocol`, `adequacy`, `corpus_approval`); the nullable
   ones (`model_provenance`/`protocol`/`adequacy`/`corpus_approval` →
   `| null`; `retrieval_stats`, `http_status`, `doi`, `pmid`,
   `failure_reason`, `human_curated_provenance`, `semantics_warning` → `| null`).
   `tier: string` (raw, NOT a T1|T2|T3 union — the Option-A faithfulness point).
2. **No collision** with the existing `EvidenceContract`/`SourceSpan`/
   `VerifiedSentence` block — every new symbol is `AuditIr*`-prefixed.
3. **`getAuditRun` pattern-consistent** with `getRun`/`getBundle` —
   `authFetch` + `asJsonOrThrow<AuditIrRun>`; `encodeURIComponent(runId)`;
   path `${BACKEND_URL}/api/inspector/runs/...`.
4. **No `web/app/**` or `src/` change** — slice 2 is the lib only.

## 4. Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/loader.py` — the dataclass tree the TS mirrors;
  NOT modified.
- `src/polaris_v6/api/inspector.py` (slice 1) — the route `getAuditRun`
  targets; NOT modified.
- `web/lib/api.ts` `EvidenceContract` block — left intact; NOT modified.

## 5. Smoke state

`web/`: `prettier --check lib/api.ts` clean; `tsc --noEmit` no errors;
`eslint` 0 errors (3 pre-existing warnings elsewhere, not `lib/api.ts`);
`npm run build` OK. The `lint + format + typecheck + build` CI job is in
scope for this web/ PR and is expected green.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
