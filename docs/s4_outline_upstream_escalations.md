# S4 outline — cross-section UPSTREAM escalations (ride the wheel)

These are NOT S4-local code bugs. They are upstream (S2 select / S3 consolidate) quality gaps
that S4 can only MITIGATE or DISCLOSE, never fully fix. They are recorded here so they ride the
section-modular wheel as cross-section escalations and do NOT die as code comments. Each names the
measured symptom, the S4 mitigation already shipped, and the real upstream fix owed.

Campaign anchor: I-deepfix-001 (#1369) s4-outline. Pipeline DNA: CLAUDE.md §-1.3 (weight-and-
consolidate) + §-1.3.1 (junk-deletion carve-out, topic-judge FAIL-OPEN).

---

## E1 — S3 representative_statement falls back to the row TITLE (title-like claims)

- MEASURED (real cp3 drb_72 bank, 686 rows / 69 baskets): ~61/69 basket representative claims are
  title-like, and ~604/686 statements are byte-copies of the row title. The outline planner is
  therefore still choosing sections from TITLES, not claim sentences.
- S4 mitigation SHIPPED: `outline_digest.py` PUSH-4 member-scan picks the first non-title-like
  member statement per basket when the representative is title-like; the residual is now measured
  as `digest_stats.title_like_claim_fraction` (Fable item 9). Singleton `statement == title` rows
  suppress the duplicate render ("title | title" -> "title"), saving thousands of prompt chars.
- REAL FIX OWED (upstream, S3/S2): `representative_statement` selection in S3 consolidate and the
  S2 statement extraction MUST emit a CLAIM SENTENCE, not the row title. The member-scan cannot
  help when nearly every member is title-like. This is the single biggest input-quality lever left
  for beating ChatGPT/Gemini on this section — it must be worked as an S3 wheel item, not patched
  in S4.

## E2 — S2 off-topic leak into the credible pool

- MEASURED: the unassigned high-tier disclosure list on the real run includes plainly OFF-TOPIC
  rows — cosmetic-safety opinions (triclosan, Homosalate), EMF SCHEER, ICSID arbitration, wrongful
  convictions, Dr. Seuss children's literature, pharmacovigilance GVP — all visible in plan.log.
  These are high-tier by venue but off-topic to the Generative-AI-labor question.
- S4 mitigation SHIPPED: the cp4 audit now labels every unassigned high-tier row `disposition:
  "unassigned"` (NOT "reassign_candidate"), and the revision_audit note REQUIRES the §-1.3.1
  topic-judge (FAIL-OPEN) before any actual compose-stage reassignment. So S4 will not pull junk
  into a section as-is (Fable item 10).
- REAL FIX OWED (upstream, S2 select): these rows should have been topic-judge-DELETED (§-1.3.1
  carve-out) or at least weight-floored at S2. The S2 wheel let them through; fix the S2 topic
  screen so off-topic whole sources never reach S3/S4.

## E3 — cp3 same_work_groups UNDER-detection (Fable item 11, measured)

- MEASURED: on the real cp3 bank, same-work detection produced only ~51 groups / very few singleton
  folds — the exact drb_72 payload carried NO `same_work_groups` key at all, so S4 fell back to
  row-level corroboration (every row its own work). Under-detected same-work groups inflate
  apparent corroboration (N rows of one work read as N works) and under-fold singleton copies.
- S4 mitigation SHIPPED: `outline_digest.py` PUSH-A already renders WORK-level corroboration
  ("xK works (N rows)") and folds same-work singleton copies WHEN `same_work_groups` is supplied,
  and the accounting identity (Fable item 2) covers folded aliases so no row goes unaccounted.
- REAL FIX OWED (upstream, S3 consolidate / cp3): improve same_work detection (url/doi/title-key
  clustering) so cp3 emits complete `same_work_groups`, and ensure the S4 caller threads them into
  the outline call. Until then S4 corroboration counts are ROW-level (an honest over-count that is
  disclosed, never a silent inflation).

---

Owner: S2/S3 wheel maintainers. S4 has done everything it can locally (mitigate + measure +
disclose); the levers above are upstream and must be scheduled as their own section-wheel items.
