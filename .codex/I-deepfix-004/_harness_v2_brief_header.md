# Codex diff-gate — Fetch cited-content harness (I-deepfix-004, branch bot/I-harness-fetch-cited)

[HARD ITERATION CAP 5. Front-load ALL findings. Reserve P0/P1 for real execution risks. APPROVE iff zero P0 AND zero P1.]

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this diff is (5-line summary)
1. A parallel fetch cited-content test harness per `.codex/I-deepfix-004/fable_fetch_harness_design.md`: it drives ONE real production seam, `refetch_for_extraction_with_diagnostics(url, max_chars)` in `live_retriever.py`, over 22 REAL labeled URLs and grades the returned `(quote, diagnostics)` against per-case expectations.
2. The verdict oracle is HARNESS-OWNED and INDEPENDENT — it does NOT import the production predicate under test (`is_issue_front_matter` / shell detectors); it re-derives front-matter / collision structure from its own high-precision rules (I-wire-013 independence, so a production regression cannot mask itself).
3. Flag-gate: at startup it asserts every fix-flag is ON (`pdf_cited_work_slice_enabled`, `span_cited_work_screen_enabled`, `cited_span_shell_detect_enabled`, `PG_REFETCH_FULL_BODY` not falsey, `PG_DISABLE_ACCESS_BYPASS!=1`) and `ZYTE_API_KEY` present; any OFF ⇒ prints `RESULT VOID`, writes NO pass, exit 2 (cannot fake a green).
4. Single-URL isolation: `--only <case|ev>`, `--rerun-failures <results.json>`, `--list`, and `--url <u> --expect <cls> --contains <stem>` ad-hoc mode; fan-out is a plain ThreadPoolExecutor with per-case + total timeouts; exit 0 green / 1 any FAIL or UNREACHABLE / 2 VOID / 3 internal.
5. Files: `scripts/fetch_cited_content_harness.py` (513 LOC), `config/fetch_harness_cases.yaml` (22 cases, data-only), `tests/polaris_graph/test_fetch_harness_oracle.py` (275 LOC, offline oracle unit tests against REAL banked span heads — the only offline part; live network is the rest of the test). NO src/ production code changed.

## Diff base
Reviewing `git diff bot/I-deepfix-004-frontmatter-core...bot/I-harness-fetch-cited` (PR-1 base is `bot/I-deepfix-004-frontmatter-core`, NOT main). 4 files, +1032 lines, all NEW files. No production `src/` code is modified by this diff.

## Correctness risks to VERIFY line-by-line (front-load anything real)
Grade these against the actual code in the diff below. These are the load-bearing invariants; confirm each holds or flag a P-finding.

A. ORACLE INDEPENDENCE. Confirm the harness verdict path never imports or calls the production front-matter/shell predicate (`is_issue_front_matter`, `clean_fetch_body`'s screen, the shell detector's classification). `front_matter_structural`, `identical_span_collision`, `group_distinctness_violations`, and `verdict_for` must decide purely from the returned quote/diagnostics + case labels. The ONLY production imports allowed are (a) the seam `refetch_for_extraction_with_diagnostics` and (b) the boolean FLAG getters in `check_flags()`. Flag getters are ON/OFF checks, not the predicate — is that a real independence leak or acceptable? Give a verdict.

B. PRECISION-FIRST — the 4 good controls (`article` class) must NEVER FAIL from an oracle false-positive. `front_matter_structural` fires on: ≥3 dot-leader-then-page lines, Cyrillic `редакционнаяколлегия`, `tableofcontents`, or (`editorialboard` AND `issn`). Could any of these plausibly fire on a real arxiv/FEDS-note/NBER-PDF/OECD-full-report article head (first ~2000 chars) and wrongly FAIL a good control? Assess the false-positive surface. Also: `contains_any` returns True on empty needle set (vacuous) — is that correct for every class that relies on it?

C. FLAG-GATE CANNOT FAKE A PASS. Trace `main()`: when `check_flags()` returns not-ok, does the code exit 2 BEFORE any case runs and BEFORE any results.json is written? Confirm no PASS/results artifact can be produced with a flag OFF. Confirm `_falsey` handles `PG_REFETCH_FULL_BODY` correctly (default "1" ⇒ ON; "0"/"false"/"off"/"no"/"disabled" ⇒ OFF) and that `PG_DISABLE_ACCESS_BYPASS` default "0" ⇒ bypass-enabled ⇒ OK.

D. NO NETWORK IN THE ORACLE UNIT TESTS. The test file loads the harness module by file path at import. Confirm module import does NOT trigger any network or heavy import (the seam import and flag imports are lazy, inside `_load_seam()` / `check_flags()`). Confirm `load_cases()` is pure file I/O. Confirm every test is deterministic and offline.

E. VERDICT LOGIC PER CLASS. Check `verdict_for` for each `expect` class against the design doc semantics:
   - `article`: PASS iff `failure_mode=='' AND eligible AND contains_any AND contains_none AND NOT front_matter_structural`; else UNREACHABLE iff fm in {fetch_failed,timeout,exception}; else FAIL.
   - `article_or_degrade` / `recover_or_disclose`: PASS as article else DEGRADED_OK on {wrong_content_front_matter,fetch_shell,paywall_shell,thin_content,fetch_failed,timeout} else FAIL.
   - `no_front_matter_span`: PASS iff fm=='wrong_content_front_matter' OR (eligible AND contains_none AND NOT front_matter_structural AND (contains_any where a positive list is declared)); DEGRADED_OK on honest refusal (not eligible); FAIL iff a front-matter/banned span was adopted.
   - `refused`: PASS iff NOT eligible; FAIL iff eligible.
   Flag any class where the code diverges from the design or where a wrong span could score PASS.

F. COLLISION OVERRIDE SOUNDNESS. `_apply_collisions` downgrades PASS/DEGRADED_OK → FAIL when an eligible span collides across ≥2 different works (global) or repeats within a `distinct_group`. Confirm it can only DOWNGRADE (never upgrade a FAIL/UNREACHABLE to PASS), and that `_work_id` keys on DOI when present else URL so two real distinct articles never falsely collide.

G. SEAM FAILURE-MODE COVERAGE. The real seam (`live_retriever.py:3209-3218` docstring) can also emit `refetch_capped` (per-URL cap, in-process negative cache) and `empty_url` — modes NOT in the design's enumerated set. In a fresh single-fetch-per-URL harness run these should be unreachable (each URL fetched once ⇒ never capped; all cases have non-empty URLs). Confirm they cannot occur in normal operation; if one did occur, note that for `article` class it would score FAIL (not UNREACHABLE) since `refetch_capped` ∉ `_UNREACHABLE_MODES`. Judge whether this is a real execution risk or a non-issue.

H. FAN-OUT / TIMEOUT / RESOURCE HYGIENE. `run_all` uses a ThreadPoolExecutor with per-case `future.result(timeout=remaining)` where `remaining = max(1, min(case_timeout, deadline - now))`. Confirm a timed-out or exception-raising case yields an honest UNREACHABLE/exception result (never a silent PASS), that the pool is context-managed (cleaned up), and that no case can hang the whole run past the total timeout in a way that blocks green dishonestly. Note: on total-timeout expiry, `remaining` floors at 1s per remaining future — confirm that still resolves rather than hangs.

## Output schema (REQUIRED — last line must be the verdict)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
End with a single final line exactly: `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.

---

## FULL DIFF UNDER REVIEW (bot/I-deepfix-004-frontmatter-core...bot/I-harness-fetch-cited)

