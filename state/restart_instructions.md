# Restart Instructions — ★ SESSION COMPLETE: CODEX APPROVED ★

## Morning-read summary (2026-04-19)

**The autonomous loop finished. Codex pass 16 verdict: APPROVED-FOR-FULL-SCALE-RUN.**

You went to sleep after directing an autonomous sweep→audit→fix
loop with no cycle cap. Claude executed 16 Codex audit passes and
10 sweep cycles over the night. The pipeline is approved.

### Final commit

`157aa0f PL: ★ Codex pass 16 verdict: APPROVED-FOR-FULL-SCALE-RUN ★`

All artifacts are in git. Approved sweep output at
`outputs/sweep_r3_final/` (cycle 10). Codex findings at
`outputs/codex_findings/full_audit_pass_{3..16}/findings.md`.

### What was fixed (M-1 through M-15)

| M | Blocker | Fix commit |
|---|---|---|
| M-1 | Fetch worker.join had no deadline | `ac593e1` |
| M-2 | Strict_verify dropped 80% sentences on clinical | `b2b6f5a` |
| M-3 | PT13 advisory failure wasn't surfaced in manifest | `3921bc0` |
| M-4 | Runbook incorrect on material_deviation semantics | `3921bc0`/`9f2801a` |
| M-5 | PT12 regex treated `[YYYY]` bibliography years as citations | `5cf6959` |
| M-6 | PT13 flagged question-inherited superlatives + adversarial evasion | `3921bc0`→`9f2801a`→`e38c43f` (dynamic threshold) |
| M-7 | Social/market-research/law-firm domains classified T1 | `PL: BUG-M-7` commit |
| M-8 | Malformed citation fragments in Novo report | same |
| M-10 | Clinical-reference products, policy think tanks, trade news got T1 | `PL: M-10` commit |
| M-11 | R9 OpenAlex rule too permissive — now requires known-journal allowlist | commit |
| M-12 | Serper truncated SR/MA titles → fetched full OpenAlex display_name | commit |
| M-13 | DOI-based OpenAlex lookup + content-title fallback | commit |
| M-14 | Raw-HTML title extraction pre-strip (R10 tightening reverted — too strict) | `6096ff5`+`b2b926b` |
| M-15 | Targeted R10 guards (truncated title, society tools, guideline/consensus markers; NIH-aggregator guard reverted after over-demotion) | `PL: M-15` + `b84baef` |

### Final pipeline state

- **538 tests pass**, 0 failed
- **Honest-by-construction invariants hold**:
  - Two-family evaluator segregation (DeepSeek gen + Qwen eval)
  - Provenance tokens + strict_verify per-sentence
  - Budget cap respected
  - Prompt-injection sanitization
  - Corpus approval gate enforced
- **Cycle 10 profile** (the approved state):
  - 0 clean releases
  - 1 partial_qwen_advisory (release=False) — clinical_afib,
    632 words, citations resolve, qwen flagged for review
  - 7 abort_corpus_inadequate — honest refusals on thin corpora
  - Total cost: $0.0010 (vs $0.80 worst-case cap)

### Documented production caveats

Per Codex pass 16:

1. **Partial/advisory reports are gated output.** Downstream
   consumers must treat `partial_qwen_advisory` runs as non-clean
   releases.
2. **R10 PMC fallback has known low-confidence T1 over-promotions**
   (3 in cycle 10) on clinical-guidance/perspective pages when
   title metadata lacks decisive markers. None of these appear in
   released content. Narrow, acknowledged.
3. **AFib completeness template** should eventually avoid claiming
   full completeness when a section says evidence was inaccessible.
   Gate already prevents clean release, so not blocking.

### Key findings from the night

- **Release-rate vs honesty tradeoff**: Cycles 5-9 oscillated between
  "many releases with T1 hallucinations" and "zero releases with
  honest tiering". Cycle 10 is the equilibrium: refuses thin
  corpora cleanly, lets the one marginal report ship only as
  gated `partial_qwen_advisory`.
- **Fetch pipeline**: 10% → ~75-95% fetch success rate via
  AccessBypass (Crawl4AI/Jina/Firecrawl cascade). Threaded worker
  with 90s deadline prevents browser-cleanup hangs.
- **Title-signal chain**: Serper snippet → OpenAlex DOI lookup →
  OpenAlex title-search → raw HTML `<title>` / Jina `Title:` /
  markdown H1 → longest-wins. Catches SR/MA suffixes that would
  otherwise be truncated.
- **Tier classification**: 5 new domain blocklists + 1 allowlist
  guard (R9) + 4 narrow R10 guards. Over-aggressive guards were
  reverted when they zeroed release rate.

### What to do on wake

1. Read `outputs/codex_findings/full_audit_pass_16/findings.md`
   (the full verdict)
2. Review `outputs/sweep_r3_final/clinical/clinical_afib_anticoagulation/report.md`
   (the one partial release — 632 words, qwen-flagged for completeness)
3. Scan `outputs/sweep_r3_final/*/*/run_log.txt` for the 7 aborts
   (each has a clear "Refusing to ship a misleading short report"
   message with the failed thresholds)
4. Optionally address the 3 documented caveats if you want to
   push release rate up (but the current honest-by-construction
   behavior is the intended design)

### Tasks closed tonight

105 task items tracked; all resolved or explicitly deferred. The
loop tasks (#123-134) walked through each Codex pass and its
remediation. #125 (declare full-scale-run readiness) completing
with this commit.
