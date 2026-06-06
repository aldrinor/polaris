# FX-16a (#1131) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P1 fail-closed chromium preflight gate (FX-16a code half). Diff:
`.codex/I-ready-017/fx16_codex_diff.patch` (vs FX-12 verified tip `ffa74071`, 2 files, 180 insertions).
FX-16b (VM `playwright install chromium` + post-install live fetch) is operator-gated (Q5), out of scope.

## Your iter-1 findings — ALL addressed
**P1 (remaining_blocker) — FIXED: preflight↔production semantics now match exactly.**
You found: preflight SKIP'd on `PG_DISABLE_ACCESS_BYPASS in {1,true,True}`, but production
(`live_retriever.py:1764`) disables the cascade ONLY on `os.getenv("PG_DISABLE_ACCESS_BYPASS","0") ==
"1"`. So `=true` + chromium absent would SKIP the LIVE gate while production still runs the dead
Crawl4AI tier → silent httpx-naive fallback. **Now the probe uses the IDENTICAL check**
`os.getenv("PG_DISABLE_ACCESS_BYPASS","0") == "1"` (no strip, no truthy set). Verified all
PG_DISABLE_ACCESS_BYPASS reads in live_retriever.py are this exact form (only :1764). Proven by
`test_probe_disable_semantics_match_production_exactly`: `true/True/yes/on/0/""/"  1  "` → do NOT skip
→ FAIL in LIVE when chromium absent; only exact `"1"` → SKIP.

**P2-1 — FIXED: cache-root coverage.** `_find_chromium_binary` now searches, in order,
`PLAYWRIGHT_BROWSERS_PATH` (official override; skips the special "0"), then per-OS defaults
(Linux `~/.cache/ms-playwright`, Windows `~/AppData/Local/ms-playwright`, macOS
`~/Library/Caches/ms-playwright`). No false-FAIL on non-Linux/relocated installs. Proven by
`test_find_chromium_honors_playwright_browsers_path`.

**P2-2 — FIXED: file check.** Only a real `is_file()` launcher passes; a partial cache dir whose
launcher PATH is a directory no longer passes. Proven by `test_find_chromium_ignores_non_file_match`.
(The static gate remains weaker than "browser launches" — that is FX-16b's post-install live fetch,
operator-gated. Acceptable for a pre-spend probe.)

## Evidence
- Offline smoke `test_fx16_chromium_preflight_iready017.py` → **11 passed** (8 original + 3 new for the
  iter-1 P1/P2 fixes).
- §-1.1: `outputs/audits/I-ready-017/fx16_s11_audit.md` — held drb_72 fetch 74/145 = 0.51 (the silent
  downgrade); the LIVE probe now fails closed pre-spend when chromium absent, with production-matched
  semantics so it cannot green-light a run production won't bypass.

## Faithfulness
Additive fail-closed gate — observability/safety only. No grounding / strict_verify / 4-role change.
Can only ABORT a paid run that would silently degrade; never weakens a check. DRY non-breaking.

## Question
Are the preflight↔production semantics now exactly aligned (P1), the cache-root coverage + is_file
checks correct (P2), and the gate faithfulness-safe? Anything blocking APPROVE?
