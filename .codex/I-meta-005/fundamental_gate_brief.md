# Codex gate — fundamental re-architecture plan (global source model, no allowlist): real, sound, no band-aid?

ADVERSARIAL §-1.1 auditor. Full plan: docs/polaris_fundamental_rearchitecture_plan.md (READ IT FULLY). It is the
FUNDAMENTAL (not band-aid) fix for gaps 1-21, centered on a SELF-ADAPTING GLOBAL source-authority model with NO
hardcoded allowlist (top sources for ANY field/region). Sub-agents searched online + may have erred — RE-VERIFY the
external claims (OpenAlex/Crossref fields, public-suffix-list gov grammar, the cited papers) and the POLARIS code
claims (esp. "PAL substrate exists but is UNWIRED from the sweep"). Use web search to confirm the API/paper claims.
Output YAML verdict FIRST. 5-cap; iter 1.

```yaml
verdict: SOUND | NEEDS_CHANGES | OVERCLAIMS
wrong_or_unverifiable_external_claims: [...]   # OpenAlex fields, PSL gov-suffix grammar, cited papers real + as-described?
wrong_code_claims: [...]                        # tier_classifier 1871-line frozensets? PAL substrate (code_executor/tool_registry/react_agent) real + UNWIRED from run_honest_sweep_r3?
is_it_actually_allowlist_free: <true|false>     # does the authority model TRULY avoid over-fit, or smuggle a list back in? is the grep-gate a real test?
band_aids_snuck_in: [...]                        # any per-domain allowlist / per-slug contract / keyword router still present?
wedge_preserved: <true|false>                    # do #13/14/17/19/23 survive intact through every phase?
thin_field_risk_real: <true|false>              # is the corroboration-as-sovereign-defense for thin-OpenAlex fields a genuine concern or overstated?
phase_plan_sound: <true|false>                   # is the 0a/0b-first dependency order + offline-exit-before-spend correct?
the_one_correction: "<or none>"
honest_one_line: "<for the operator>"
```

## The centerpiece to verify (global source model, no allowlist)
- Replace tier_classifier.py's ~1871 lines of biomedical host frozensets with COMPUTED signals: (A) scholarly-graph
  authority (OpenAlex/Crossref: is_peer_reviewed, cited_by_count, venue h_index/2yr_mean_citedness, is_core,
  is_in_doaj, is_retracted) — VERIFY these fields exist on the OpenAlex API; (B) institutional/primary via OpenAlex
  ROR type+country_code + the PUBLIC-SUFFIX-LIST government-suffix grammar (*.gov, *.gc.ca, *.go.jp, *.gov.uk,
  *.gouv.fr, *.gov.<cc>) — VERIFY the PSL has usable gov-suffix structure (is a finite grammar, not a host list);
  (C) structural junk detection (schema.org PressRelease, login-wall, /blog/, self-interest) — regex, no hosts;
  (D) CORROBORATION = independent-host agreement (Knowledge-Based Trust, arXiv 1502.03519) — the SOVEREIGN defense
  for thin-OpenAlex fields; (E) recency.
  Plus the FALSIFIABLE OVER-FIT GATE: grep the new module for ANY country/agency/field/journal name → must be ZERO.
- VERIFY the cited papers are real + as-described: KBT 1502.03519, SAFE 2403.18802, FActScore, VeriScore, MiniCheck,
  ALCE, PAL 2211.10435, STORM 2402.14207.

## The code claims to verify (file:line)
- tier_classifier.py = ~1871 lines of curated biomedical frozensets (I locally measured the line count — confirm the
  frozensets are named-host lists).
- THE LOAD-BEARING gap-9 claim: code_executor.py (PAL: AST import-allowlist numpy/pandas/scipy, subprocess, 30s
  timeout, generate_and_execute_analysis), tool_registry.py (execute_python/comparison_table/meta_analysis with
  source_evidence_ids), react_agent.py EXIST but run_honest_sweep_r3.py NEVER imports them (I locally grepped 0
  hits — confirm the substrate is real + genuinely unwired, so gap 9 is rewire+provenance not greenfield).

## The decisive checks
1. Is the authority model TRULY allowlist-free, or does it smuggle a curated list back in somewhere? Is the
   zero-host grep-gate a real, sufficient over-fit test?
2. Are the OpenAlex fields + the PSL gov-suffix grammar REAL (web-verify) and do they actually generalize to any
   region/field/language, or is non-English/grey-lit coverage a fatal hole?
3. Is the corroboration signal a sound sovereign defense for thin-OpenAlex fields, or hand-waving?
4. Is the gap-9 "PAL substrate exists, just unwired" claim TRUE? (decides whether gap 9 is rewire vs a big new build)
5. Does the faithfulness wedge (#13/14/17/19/23) survive every phase, and does the gap-9 [#calc:] provenance keep
   computed numbers inside the wedge?
6. Any band-aid (per-domain allowlist / per-slug contract / keyword router) sneaking back in?
7. Is the phase order (0a authority + 0b verification-mode FIRST, offline exit before the single Phase-8 spend) sound?

## Your ruling
SOUND / NEEDS_CHANGES / OVERCLAIMS. Verify external + code claims yourself (web + repo). The single most important
correction. Honest one-liner. This commits to docs/ + opens the build issue on APPROVE.
