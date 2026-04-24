# POLARIS full-audit pass 5 — M-1 timeout + M-2 span-finder review

You are re-auditing POLARIS after addressing two Codex pass 4
mediums and surfacing two new downstream issues.

## Context

Commits since pass 4:
- `ac593e1` — M-1 fix: worker.join(timeout=PG_FETCH_DEADLINE_SECONDS)
- `b2f9dc2` — docs sync (todo_list + session_log)
- `b2b6f5a` — **M-2 fix: content-aware span finder**

Pass 4 declared CONDITIONAL with 4 mediums:
- M-1 (gating): worker.join() unbounded → fixed in `ac593e1`
- M-2: content starvation on clinical (146 words, 80% drop rate) →
  root-cause-diagnosed and fixed in `b2b6f5a`
- M-3: PT13 advisory failure vs release_allowed=True → accepted
- M-4: tier material_deviation → accepted as documentation

## Your mandate — critical review of M-1 AND M-2 together

### 1. M-1 timeout substantivity check

Read `src/polaris_graph/retrieval/live_retriever.py` lines 302-325
(the new timeout block). Answer:

- Is `worker.join(timeout=deadline)` with `worker.is_alive()`-after
  the right guard? Specifically: if the worker finishes exactly at
  the deadline boundary, can we still race and incorrectly fall
  back to naive httpx? (I believe join() returns on timer OR on
  completion, so `is_alive()` afterwards is authoritative.)
- The daemon thread is left to die with the interpreter when the
  worker wedges. On Windows, do daemon threads holding a subprocess
  (Chromium) handle actually release those handles cleanly?
- `PG_FETCH_DEADLINE_SECONDS=0` disables the deadline. Is that a
  foot-gun for the 8-query sweep if someone sets it while running?
- Regression test `test_fetch_content_times_out_falls_back`
  monkeypatches a hanging bypass. Does it actually exercise the
  thread path you'd hit in production, or is the mock too thin?

### 2. M-2 span-finder substantivity check

Read `src/polaris_graph/generator/live_deepseek_generator.py` —
the new `_find_best_span_for_sentence` function and the rewired
`_rewrite_draft_with_spans`. Answer:

- Does the sliding window (default 500 chars, stride 100) correctly
  satisfy the strict_verify contract? Specifically:
  - `_decimals_in(window_text)` must be a superset of sentence
    decimals (hard requirement)
  - `_content_words(window_text)` overlap with sentence content words
    must be maximized
- Is the imported private helper usage
  (`_content_words`, `_decimals_in`, `_strip_dose_patterns`,
  `_PLACEBO_COMPARATOR_RE`, `_THRESHOLD_RE`) a layering violation I
  should refactor? Or is exposing them as a public preprocessing
  API the right move?
- Is there a span-selection bug I'm missing? For example, if the
  LLM emitted a citation for ev_000 but the actual support is in
  ev_001, the finder doesn't re-route — it just picks the best
  window in ev_000. Is that the right choice?
- Span width concerns: 500 chars is much wider than the original
  30 chars around decimals. Does this trivialize the verifier?
  Specifically: a 500-char window of random academic prose might
  coincidentally contain 2+ content words from many sentences,
  falsely passing them.

### 3. Empirical validation I ran

The smoke artifacts are at:
- `outputs/m2_diag_clinical/clinical/clinical_tirzepatide_t2dm/` (BEFORE fix)
- `outputs/m2_fixed_clinical/clinical/clinical_tirzepatide_t2dm/` (AFTER fix)
- `outputs/smoke_retrieve_v5/tech/tech_rag_architectures_2024/` (BEFORE fix, from pass 4)
- `outputs/m2_fixed_tech_v2/tech/tech_rag_architectures_2024/` (AFTER fix)

Each has `manifest.json` + `verification_details.json` + `report.md`.
Measured changes:

| Domain | Drop rate | Words | Sections kept | Release |
|---|---|---|---|---|
| clinical BEFORE | 80% (20/25) | 174 | 2/4 | False |
| clinical AFTER | 15% (4/26) | 605 | 4/4 | True |
| tech BEFORE | 32% (8/25) | 529 | 4/4 | True |
| tech AFTER | 3.7% (1/27) | 689 | 4/4 | False* |

*Tech AFTER release=False because of two newly-surfaced evaluator
issues (section 4 below), not because of M-2.

Verify my claim: run the before/after verification_details.json
diff yourself. Does the drop-reason distribution shift from
"mostly no_content_word_overlap" to "mostly genuinely unsupported"
as I claim?

### 4. Two newly-surfaced downstream issues — are they gating?

**PT12 `max_marker=2025 but evidence_pool has 19`** on tech:
- Evaluator PT12 treats `[2025]` in the report as an out-of-range
  citation marker. But `[2025]` is almost certainly a year in a
  parenthetical, not a citation. Either:
  - The evaluator regex is too permissive (catches any
    `[<number>]` as a citation marker)
  - The LLM generated `[2025]` deliberately and the evaluator
    correctly flags it as unresolvable
- Open `outputs/m2_fixed_tech_v2/tech/tech_rag_architectures_2024/report.md`
  and find the `[2025]` occurrence. Is it a year or a mis-emitted
  citation marker?
- If it's a year: PT12 regex needs tightening (e.g., exclude
  4-digit numbers that look like years, or require citations to
  come immediately after a word, not a space). This would be
  another pass-5-surface medium.
- If it's a real citation error from the LLM: we need prompt
  reinforcement that citation markers must reference numbered
  bibliography entries only.

**PT13 6 unhedged superlatives** on tech:
- Evaluator flags "best" (in title "best practices" — directly
  from the question) and "superior", "best" in prose.
- Is PT13 supposed to ignore superlatives that come from the
  research question itself? The title "best practices" comes
  from the user's question, not the generator's assertion.
- Should the generator's prompt explicitly instruct it to hedge
  superlatives, or is PT13 a soft advisory that shouldn't gate
  release?

### 5. Full-suite test status

The pass-4 Codex reported 2 failed / 23 errors on `test_scope_gate.py`
in the Codex pytest subprocess but my local tree shows 15/15 pass.
Please re-run and see whether the discrepancy persists at commit
`b2b6f5a`. If it reproduces, narrow to the specific failure — is
it an environment issue (PG_* env vars, import cache) or a genuine
regression?

### 6. Verdict

One of:
- **READY-FOR-8-QUERY-SWEEP**: M-1 and M-2 are sound, PT12/PT13
  are non-gating, any new issues are documented follow-ups
- **NOT-READY**: one of the fixes is unsound, or PT12/PT13 is gating
- **CONDITIONAL**: ship with a specific guardrail (e.g., PT12 fix
  required first)

### READY BAR

Same as pass 3 & 4:
- Zero blockers
- ≤3 mediums, each with explicit acceptable-risk rationale
- M-1 and M-2 fixes must be substantive; span-finder changes must
  not trivialize strict_verify
- No new silent-failure modes discoverable in 20-30 min of probing

## Output

Write to `outputs/codex_findings/full_audit_pass_5/findings.md`
with frontmatter:

```yaml
---
verdict: READY-FOR-8-QUERY-SWEEP | NOT-READY | CONDITIONAL
pass: 5
commit: b2b6f5a
m1_substantive: true | false
m2_substantive: true | false
pt12_gating: true | false
pt13_gating: true | false
new_blockers: <int>
new_mediums: <int>
rationale: |
  <2-4 sentence executive summary>
---
```

Followed by:
- `## 1. M-1 timeout review`
- `## 2. M-2 span-finder review`
- `## 3. Empirical validation check`
- `## 4. PT12 and PT13 disposition`
- `## 5. Test suite state`
- `## 6. Final verdict`

## Authentication

OAuth (chatgpt). No API-key burn.

## Expected duration

20-30 minutes.

---

Start:

```
git log --oneline 81b18de..HEAD | head
git show b2b6f5a --stat
python -m pytest tests/polaris_graph/ -q 2>&1 | tail -3
```

Then walk sections 1-6.
