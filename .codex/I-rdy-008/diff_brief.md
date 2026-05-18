# Codex DIFF review — I-rdy-008 / GH #504 slice 7a: v6 inspector evidence-span route

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 7a** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1, 2 P2).
**2 files: `src/polaris_v6/api/inspector.py` + `tests/v6/test_inspector_route.py`.**

Slice 7a is the backend half of the slice-7 split your architecture consult
decided (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`): a new
evidence-span route so the slice-7b frontend can migrate `PoolTab`/
`EvidencePane` off the golden-fixture-only `getBundle()`. Backend only — no
`web/**` (that is 7b).

## 2. The change

- `_resolve_completed_artifact_dir(run_id)` — extracted from
  `get_inspector_run` (run_store lookup + 404/409/422 + artifact_dir checks);
  `get_inspector_run` now calls it. **Behavior-preserving refactor.**
- `_load_evidence_pool(artifact_dir, run_id)` — reads `evidence_pool.json`
  (bare list OR `{"sources": […]}`; row id = `evidence_id` or `source_id`);
  absent/malformed/not-a-list → 422.
- `_evidence_body(row)` — `full_text`/`direct_quote`/`snippet` precedence.
- `GET /api/inspector/runs/{run_id}/evidence` → `get_inspector_run_evidence`:
  resolve dir → load pool → `load_audit_ir` → walk
  `verified_report.sections[].sentences[].tokens[]`, de-dup by `(evidence_id,
  start, end)` → `{run_id, spans:[{evidence_id, span_start, span_end,
  span_text, tier, source_url, claim_ids}]}`.
- `tests/v6/test_inspector_route.py` — `_write_artifact_dir_with_evidence` +
  `_seed_completed` helpers + 10 evidence-route tests.

## 3. Verify

1. **`span_text` is the exact slice.** `span_text == _evidence_body(row)
   [start:end]`. `_evidence_body` returns the first non-empty of `full_text`/
   `direct_quote`/`snippet`. No truncation, no transformation.
2. **Fail-loud taxonomy.** 422 for: missing/malformed/non-list
   `evidence_pool.json`; token `evidence_id` not in the pool; row with empty
   body; `start<0` / `start>end` / `end>len(body)`. No clamping, no
   `statement` fallback. Confirm 422 (not 404/500) is right for all, and that
   the route fails loud rather than skipping the offending span.
3. **Range-key de-dup.** Spans keyed by `(evidence_id, start, end)`;
   `claim_ids` aggregates every citing sentence `claim_id`. Two sentences
   citing one range → one span, two claim_ids.
4. **Shared resolver is behavior-preserving.** `get_inspector_run`'s
   404/409/422 outcomes + detail strings are unchanged by the extraction.
5. **Zero-token run → 200 `{spans:[]}`** — not an error.
6. **No coercion.** `tier` is the raw string; nothing narrows it to T1-T3.
7. **Scope** — only the 2 named files; no `web/**`, no loader/serializer, no
   `bundle.py`.

## 4. Files I have ALSO checked and they're clean

- `src/polaris_v6/api/artifact_to_slice_chain.py` — `_full_text_for_evidence_id`
  (the `evidence_pool.json` shape precedent the resolver mirrors); NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `EvidenceSpanToken` /
  `ReportSentence` (the token walk relies on `token.evidence_id/start/end`
  and `sentence.claim_id`); NOT modified.
- `src/polaris_v6/api/app.py` — mounts `inspector_router`; the new route
  rides the existing mount; NOT modified.
- `src/polaris_v6/api/bundle.py` — the golden-fixture `getBundle()` route;
  intentionally untouched (stays for legacy/F15).

## 5. Smoke state

`ast.parse` — both files clean. `PYTHONPATH='src;.' pytest
tests/v6/test_inspector_route.py` — **15 passed** (5 slice-1 regression + 10
new). No web/ change → no web smoke. The `lint + format + typecheck + build`
CI job is NOT in scope (no web/ change); the python test job covers this.

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
