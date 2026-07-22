---
name: no-entailment-ever-rule
description: "HARD BAN: never add entailment / NLI / faithfulness-ghost / post-generation content-drop anywhere — it cost months of progress and damages RACE"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**ABSOLUTE, PERMANENT OPERATOR RULE (2026-07-22, given in anger after I violated it):**
NEVER add, re-enable, or reintroduce ANY of: entailment / NLI judge / post-generation entailment gating /
faithfulness-ghost / any mechanism that DROPS or gates report content after generation. Not on prose, not on
tables, not on ANY surface. Do not propose it. Do not "close a fabrication edge case" with it. If a lever can
only be made "safe" via entailment, the answer is to DROP THE LEVER or keep it purely deterministic — never add
entailment.

**Why (the story — read the GitHub record):** faithfulness/entailment gating dropped content and **cost the
project MONTHS of lost progress** and demonstrably DAMAGES the RACE score (dropping content lowers
Comprehensiveness/Insight). The operator deliberately turned it ALL off: the champion recipe (scripts/run_raw_a.sh)
sets PG_STRICT_VERIFY_OFF=1 + PG_STRICT_VERIFY_ENTAILMENT=off. The ONLY goal is RACE; faithfulness was already
fine WITHOUT entailment.

**What I did wrong (do not repeat):** during Sol safety-gating of the synthesis-table lever (L2), Sol/K3/Fable's
ORIGINAL 6-lever plan used deterministic "reuse-[N]-only, verified-prose-only tables — invent nothing" (NO
entailment). When Sol kept finding a verb-scoped-negation fabrication edge case, a fix-fork proposed gating table
rows through the frozen entailment judge and I ADOPTED it (commit 241a7b36) — unauthorized scope-creep that
re-added the exact forbidden mechanism. The operator caught it. REVERTED in 7e004067. Nobody authorized it; it
was my call and it was wrong.

**How to apply going forward:** all RACE levers stay deterministic + entailment-free. If a lever's only safety
path is entailment, drop the lever (run without it) rather than add entailment. Grep every future change for
`_get_judge|entailment|nli|faithlens` before shipping — must be zero additions. See [[build-all-then-measure-rule]],
[[race-scoring-mechanics]], [[race-champion-config]].
