# OPERATOR SECTION DIRECTIVES — walk of the pipeline sequence (2026-07-10)

The operator is reviewing the S0→S7 sequence section by section and giving a refinement on
each. Captured here verbatim-in-intent so none is lost. These AMEND the design docs + master
plan and are folded into the section designs in a consolidated pass (one editor, to avoid
plan-file collisions). Status column tracks fold-in.

| Stage | Operator directive | Status |
|---|---|---|
| **S1.b RETRIEVE (query-gen)** | Confirm we are STILL generating queries by the **FS-Researcher method** (to-do-list sub-topics + checklist re-plan), NOT a replacement. Design 7 only adds the breadth resolver (how many queries / searches, from the user ask, bounded by env) + scope flowing into query wording and backend filters ON TOP. Separately we complete the REST of the FS-Researcher paper we skipped. | Confirmed to operator; design already says this (doc 07 + master §1.1). No change needed. |
| **S2 SELECT+WEIGH** | Sharpen the drop policy. **Credibility → WEIGHT (never drop a credible on-topic in-scope source).** THREE DROP triggers only: (1) OFF-TOPIC → drop; (2) OUT-OF-USER-SCOPE → drop (user's explicit scope from RunConfig: dates/recency/type/geo/lang/author); (3) JUNK → drop. **LINE-LEVEL:** the section must READ EVERY LINE of each source and decide HOW MANY LINES to drop — drop the off-topic/out-of-scope/junk lines, KEEP the on-topic in-scope lines (not just whole-source). Fail-open on uncertainty; every drop disclosed. | Fable revising doc 01 + master S2 + §-1.3 reconciliation (IN PROGRESS). |
| **S5 COMPOSE** | Be like FS-Researcher: **each small section of the writing must trace to each source.** Keep the per-sentence source tie tight through composition. | Confirmed to operator: POLARIS provenance tokens `[#ev:<id>:<start>-<end>]` + strict_verify already enforce per-sentence source-tie; S5 reinforces write-from-own-baskets + tie survives holistic review. TO FOLD into doc 04/05 + master S5. |
| **S6 VERIFY** | **UNFREEZE the faithfulness engine.** Operator relaxes the LOCKED "untouchable / only-hard-gate" rule (§-1.3): S6 is now TOUCHABLE — tune / re-wire / and DELETE the piece that backfires. Rationale: too much time spent on the INVISIBLE faithfulness property while VISIBLE quality (depth, coverage, chrome, readability) was starved. Visible quality now > invisible faithfulness. | Confirmed to operator. PLAN: rewire silent-**DROP** → **LABEL + REPAIR** (verifier labels weak claims weak, keeps the claim + confidence, repairs via NLI — the operator's own `feedback_always_release_verifier_labels_never_holds` rule). Preserves the clinical-safety SIGNAL, kills the thin-report backfire. If a piece still backfires after that, delete it. TO FOLD into master S6 (was "none/untouched; wiring only" → now "rewire DROP→LABEL+REPAIR, touchable"). |

## §-1.3 RECONCILIATION (from S2 directive — the axis split)
- **Credibility = WEIGHT.** A credible, on-topic, in-scope source is NEVER dropped; a low tier just carries low weight. (§-1.3 principle 1 intact.)
- **Off-topic / out-of-user-scope / junk = DROP**, at LINE granularity (read every line). (§-1.3.1 carve-out, now extended to out-of-scope + line-level.)
- The user's explicit scope is the user's HARD filter — distinct from credibility weighting.

## Awaiting further operator directives on: S0 INTAKE, S3 CONSOLIDATE, S4 OUTLINE, S6 VERIFY, S7 RENDER, S-X thin-section re-fetch.
