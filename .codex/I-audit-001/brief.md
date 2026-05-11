```
HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

# I-audit-001 — Extend line-by-line audit to read resolved [N] + bibliography.json + pool

## Output schema (binding)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Problem

`scripts/run_line_by_line_audit.py` (I-bakeoff-A-001, PR #391) audits the
**pre-resolution** verified-sentence stream that retains `[#ev:id:start-end]`
provenance tokens. Two existing inputs:

- `--verified-sentences <jsonl>` — canonical token-bearing input from
  generator2/strict_verify (one record per line).
- `--report <md> --pool <json>` — legacy direct text containing tokens.

**Production gap:** the delivered `report.md` is the *post-resolution* artifact
produced by `resolve_provenance_to_citations()` at
`src/polaris_graph/generator/provenance_generator.py:1026-1093`. That function
strips the `[#ev:...]` tokens and replaces them with numbered `[N]` citation
markers. Bibliography is persisted alongside as `bibliography.json`:

```json
[{"num": 1, "evidence_id": "ev_001", "tier": "T1", "url": "...", "statement": "..."}, ...]
```

So the audit harness **cannot directly read real production output**. For
BEAT-BOTH head-to-head against ChatGPT DR + Gemini DR, we need a path
that reads `report.md` (with `[N]`) + `bibliography.json` ({num → evidence_id}) +
`evidence_pool.json` (the source spans). That is the I-audit-001 deliverable.

Per CLAUDE.md §-1.1: this is the clinical-safety-critical audit lane.
Per CLAUDE.md §-1.2: GH issue #398 created first; this brief is step 4
(comprehensive grep done; offline smoke design done; this is the brief).

## Files I have ALSO checked and they're clean

- `src/polaris_graph/generator/provenance_generator.py:1026-1093` —
  `resolve_provenance_to_citations()` is the canonical token-to-[N] converter;
  bibliography format is `{num, evidence_id, url, tier, statement}`. Verified.
- `outputs/I-bug-088_validate/clinical/clinical_tirzepatide_t2dm/{report.md,bibliography.json,live_corpus_dump.json}`
  — sample production output. report.md has 7 `[N]` markers, 0 `[#ev:...]`
  tokens. bibliography.json has 5 entries `{num, evidence_id, statement, tier, url}`.
  Note: `live_corpus_dump.json` is a tier dump (url/title/tier only, no full_text);
  the actual evidence pool with `full_text`/`direct_quote` lives in a separate
  `evidence_pool.json` per existing `--pool` contract. This PR does NOT change
  the pool contract.
- `tests/scripts/test_run_line_by_line_audit.py` (240 lines, 15 tests) — covers
  audit_sentence + run_line_by_line_audit + _render_audit_md + _normalize_pool +
  _normalize_sentence. New tests will append, not modify existing.
- `scripts/run_paid_evaluator_scoring.py` — uses the same {num, evidence_id}
  bibliography shape via `_load_sentences_with_spans_from_jsonl`; my loader
  follows the same broken-pointer pattern (preserve UNREACHABLE state).
- `scripts/run_entailment_fpr_audit.py` — does NOT depend on bibliography
  resolution; orthogonal.
- `tests/scripts/test_run_paid_evaluator_scoring.py` — broken-pointer
  propagation pattern reused.
- `src/polaris_graph/generator/provenance_generator.py:_PROVENANCE_TOKEN_RE` —
  matches `\[#ev:([^:]+):(\d+)-(\d+)\]`. My new regex `\[(\d+)\]` for resolved
  [N] markers is disjoint (no `#ev:` prefix) — no clash.

## Design (revised after iter-3 P1)

Add a third audit mode: `--resolved-report <path>` + `--bibliography <path>`
(reuses `--pool <path>`). The loader inverts `resolve_provenance_to_citations`:

1. Parse `bibliography.json` → build `{num: evidence_id}` map.
2. **Isolate the claim body via explicit named-heading scope rules**
   (iter-3 P1-1 fix). Walk the report line-by-line, tracking the current
   level-2 heading. The scope rules use **named heading allowlists**, NOT
   the first-`##`-stops rule (which fails on Per-Trial Summaries +
   Analyst Synthesis insertions before Methods per
   `scripts/run_honest_sweep_r3.py:2038,2158`):

   - `_TERMINAL_H2_HEADINGS` (case-insensitive exact match on heading
     text after `## `): `{methods, contradiction disclosures,
     bibliography, v30 phase-1 retrieval coverage disclosure}`. On
     encountering one, break — everything after is appended substrate.
   - `_EXCLUDED_SYNTHESIS_H2_HEADINGS` (this audit's scope is the
     strict-verify'd `resolve_provenance_to_citations` output;
     synthesis layers have different source-text contracts —
     `_m42b_refetched_quote` for M50 per
     `src/polaris_graph/generator/multi_section_generator.py:2008-2018`
     — and need a separate audit lane per iter-3 P1-2):
     `{per-trial summaries, analyst synthesis}`. On encountering one,
     enter "skipping section" mode until the next `##` heading or end
     of file; record the heading name in
     `manifest["excluded_synthesis_sections"]`.
   - Default (unknown `##` heading not in either set): record name in
     `manifest["unrecognized_h2_sections"]` and **KEEP** the content
     (defensive: don't silently drop unfamiliar sections; future-proof
     against new claim-body section types).
   - Strip level-3+ heading lines (`^#{3,}\s+`) — `### Efficacy` etc.
     are section labels, not claims.
   - Skip the leading `# ` title line.
   - If no `^##\s+` line is found, the entire post-title body is treated
     as claim body (some legacy artifacts may not have appended substrate).
   - Sentences without any `[N]` marker inside KEPT body still produce
     UNSUPPORTED verdicts (correct: a body claim that lost its citation
     should be visible to the audit as UNSUPPORTED, not silently dropped).
3. Split the cleaned body into sentences with the existing `_split_sentences`.
4. For each sentence, find every `[N]` marker via
   `_RESOLVED_CITATION_RE = re.compile(r"\[(\d+)\]")`.
5. For each `[N]`:
   - If `N` not in bibliography → emit synthetic `[#ev:__unresolved_<N>__:0-0]` token
     so existing `audit_sentence` returns `UNREACHABLE` (evidence_id not in pool).
   - If `N` in bibliography → look up `ev_id = bibliography[N]`. If `ev_id` not in
     pool → emit `[#ev:<ev_id>:0-0]` (UNREACHABLE via "unknown_evidence_id").
   - If `ev_id` in pool: use the normalized `direct_quote` field which
     `_normalize_pool` already populates via the fallback chain
     `direct_quote or full_text or snippet` (iter-1 P2-1 fix). Emit
     `[#ev:<ev_id>:0-len(direct_quote)>]`.
6. Rewrite sentence: strip `[N]` markers, append synthesized `[#ev:...]` tokens,
   feed through existing `run_line_by_line_audit_records()`.

This means **the entire `direct_quote`/`full_text`/`snippet` (whichever
`_normalize_pool` selected) becomes the audit span** — coarser than the
token-bearing path which uses per-sentence span boundaries. Document this
explicitly in the manifest as `verdict_semantics_note_resolved` and in the
function docstring.

## Acceptance criteria

1. New CLI flag `--resolved-report <path>` (mutually exclusive with `--report`
   and `--verified-sentences`).
2. New CLI flag `--bibliography <path>` (required iff `--resolved-report` set;
   error otherwise).
3. `_load_sentences_with_resolved_citations(report_path, bibliography_path, pool) -> list[str]`
   helper that returns token-bearing sentences ready to feed existing audit logic.
4. Sentence with `[N]` where `N` not in bibliography → `UNREACHABLE` verdict
   with reason exactly `unknown_evidence_id:__unresolved_<N>__` (iter-3 P2-2
   fix: this is the single user-visible contract; we reuse the existing
   audit path which produces this literal string when the synthesized
   evidence_id `__unresolved_<N>__` is not in the pool).
5. Sentence with `[N]` where `evidence_id` not in pool → `UNREACHABLE` with
   reason `unknown_evidence_id:<ev_id>`.
6. Sentence with `[N]` resolving to a valid `full_text` → mechanical checks
   run against `full_text` (decimals subset, content-word overlap ≥ min_overlap).
7. Manifest carries `verdict_semantics_note_resolved` field documenting
   coarseness — span = entire normalized evidence text selected by
   `_normalize_pool` (`direct_quote` or `full_text` or `snippet`), no
   per-sentence boundaries; weaker than the token-bearing path; useful
   for production output where tokens are stripped (iter-2 P2-1 fix).
8. Tests added to `tests/scripts/test_run_line_by_line_audit.py`:
   - resolved [N] resolves to valid ev_id → VERIFIED
   - resolved [N] with N not in bibliography → UNREACHABLE
   - resolved [N] with ev_id not in pool → UNREACHABLE
   - multiple [N1][N2] in same sentence → both tokens synthesized
   - no `[N]` marker → UNSUPPORTED (no provenance token)
   - resolved + bibliography arg validation (missing --bibliography errors)
   - manifest contains `verdict_semantics_note_resolved`
   - **Realistic production-report fixture (iter-3 P2-1 fix — count
     made consistent):** synthetic report mirroring I-bug-088 shape.
     Body:
     * `# Research report: ...` (title, skipped)
     * `### Efficacy` heading
     * one body sentence with `[1]` marker (→ VERIFIED)
     * one body sentence with `[2]` marker (→ VERIFIED)
     * `### Limitations` heading
     * one body sentence WITHOUT any `[N]` marker (→ UNSUPPORTED)
     * `## Per-Trial Summaries` (synthesis section, EXCLUDED from audit)
     * one body sentence with `[1]` marker (must NOT be audited)
     * `## Methods` (terminal substrate — break here)
     * Methods prose + `## Bibliography` with `[1]` `[2]` ref list lines
       + `## V30 Phase-1 Retrieval Coverage Disclosure` section.
     Assertions: (a) `result["summary"]["total_sentences"] == 3` exactly
     (2 VERIFIED + 1 UNSUPPORTED); (b) NO per_sentence record contains
     any of the bibliography ref-list text; (c) NO per_sentence record
     contains the Per-Trial-Summaries body sentence; (d)
     `manifest["excluded_synthesis_sections"] == ["per-trial summaries"]`.
   - **Pool with only `snippet` key (iter-1 P2-1 fix):** loader uses
     `_normalize_pool` so a pool whose entries have ONLY `snippet` (no
     `direct_quote` or `full_text`) is auditable with non-zero span.
   - **Arg-validation symmetry (iter-2 P2-2 fix):** `--bibliography`
     supplied without `--resolved-report` errors with exit 1.

## Test plan

```bash
# Unit tests pass
PYTHONPATH=. pytest tests/scripts/test_run_line_by_line_audit.py -v

# Smoke against real I-bug-088 output (after synthesizing an evidence_pool.json
# from live_corpus_dump.json + adding full_text stubs — out of scope, this is
# infra; if pool unavailable for smoke, just unit tests suffice)
```

## Why this matters

User asked the readiness question for BEAT-BOTH: "Are we ready to run a serious
line-by-line audit head-to-head?" Answer: token-bearing audit is ready
(I-bakeoff-A-001) but production output strips tokens, so we cannot directly
audit delivered reports. This PR closes that gap. After merge, BEAT-BOTH
audit can run against `outputs/<run>/report.md` + `bibliography.json` +
`evidence_pool.json` triple — exactly what production emits — and produce
per-claim VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE verdicts per
CLAUDE.md §-1.1.

## Scope discipline

- LOC budget: ~80 production + ~80 test = ~160 LOC. Well under 200.
- No changes to `_normalize_pool`, `audit_sentence`, `run_line_by_line_audit`,
  `_render_audit_md`. Reuse only.
- No changes to `provenance_generator.py` — read-only consumer of its output.
- No new dependencies.
