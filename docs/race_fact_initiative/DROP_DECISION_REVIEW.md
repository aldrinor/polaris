# Drop-decision independent review + reconciled build plan (U3 / U4 / U2 / U13)

**Context.** After recon showed the plan's original seams for U3/U4/U2/U13 were dead/default-off on the Gate-B/V30
path, Opus delivered U3/U4/U7/U10 as ONE prompt directive (`PG_ANALYTICAL_SYNTHESIS`) and DROPPED U2/U13. The
operator challenged whether those drops were legitimate. Sol (max reasoning) + Fable independently reviewed the
decision with full context (mission, every standing ban, architecture reality, per-lever facts) and were told to be
adversarial. **Both concluded Opus overcorrected into prompt-only/drop; U3, U4, and U2 are cleanly buildable and
worth building.** Sol's bottom line: *"Opus correctly avoided banned machinery, but overcorrected into
prompt-only/drop decisions."*

## Per-lever verdict (both models)
| Lever | Verdict | Opus's drop was… |
|---|---|---|
| **U3** explain divergence (Insight #8 .0800; Comp #5) | **BUILD-THE-MECHANISM** (both) | NOT legit — a shortcut. A pre-gen evidence-pair analysis rendered as plain prompt text is NOT the ghost. |
| **U4** measure×context (Comp #3 .0725; Insight share) | **BUILD** via cross_trial_synthesis (Sol) / delivered by U3's ledger (Fable) | outcome right, reason wrong (relation-packs are empty-by-schema) |
| **U2 (+U8)** framework spine | **BUILD** narrow directive (both) | shortcut — the facet outline DOES control enrichment sections |
| **U13** anti-residual | one-line rider on U2 | defensible to skip alone; cheap to include |

## Key technical findings (verified by both, on live flags + corpus probe)
1. **U3 is mis-wired, not empty.** `contradiction_mining.find_contradictions` today is **conflict-only** — it
   discards `compatible` + `non_comparable` (`:157-183`; the committed test `test_batch3_pre_generation.py:79-91`
   *requires* them to return `[]`). The plan wanted **all 3 classes + boundary reason**. Fable's probe: 1,071
   candidate pairs (889/997 rows carry measures). So the fix is: harvest all 3 classes, on content-derived
   candidates (NOT the ~9,444-pair Cartesian pool), config-capped pair budget.
2. **U4's relation-pack mechanism is empty-by-schema.** 0/997 task-72 rows carry the declared attrs
   (`relation_evidence_packs.py:69-85`, no text fallback) → it would inject nothing. Do NOT enable
   `PG_RELATION_EVIDENCE_PACKS`. Extend the ALREADY-LIVE `cross_trial_synthesis` (contract-slot injection
   ~`multi_section_generator.py:12460-12471`) instead. U3+U4 share ONE pre-gen comparison substrate.
3. **U2 asset marooned.** `PG_COVERAGE_SPINE` (semantic, default-off, `config_defaults.py:915-922`) already threads
   question-named concepts through framing/mechanism/comparison/synthesis/implication roles
   (`outline/outline_agent.py:94-119`), but only inside the optional outline-agent self-review (Gate-B doesn't
   enable `PG_OUTLINE_AGENT`). Retarget it to the active facet outline (`_select_outline_system_prompt` ~:1650-1658).
   Do NOT blindly flip the 4-role `PG_FACET_OUTLINE_SKELETON` (Sol: broad structural change, confounds measurement,
   may duplicate the fixed V30 contract sections — the one place Opus's caution was right).

## Reconciled build plan (for the next Gate-B run)
1. **U3+U4 shared pre-gen comparison substrate** → plain-text divergence/comparison ledger → injected via the live
   `cross_trial_synthesis` seam. Harvest all 3 classes + boundary + same-measure×different-context pairs; run on
   content-derived candidates; config-capped pair budget; separate semantic flags (`PG_DIVERGENCE_LEDGER`,
   `PG_MEASURE_CONTEXT_SYNTHESIS`). **Ghost-guards (state in the diff):** the ledger has NO runtime reader after the
   writer call; never re-run post-gen; never compared to emitted text; frozen verifier untouched; plain text only.
2. **U2 framework spine** — retarget `PG_COVERAGE_SPINE` to the active facet outline (NOT the 4-role skeleton).
   **U13** — one anti-residual section-ownership sentence (`PG_OUTLINE_SECTION_OWNERSHIP`) riding the U2 diff.
3. Keep `PG_ANALYTICAL_SYNTHESIS` as the presentation writer-instruction (both: useful, not a substitute for the
   evidence-derived ledger).

**Priority:** U3+U4 substrate first (Insight #8 .0800 + Comp #3 .0725 — hits our weakest dim AND a top Insight
cell), then U2/U13. Each built → proven wired on the active Gate-B producer with an ON-state capture → gated
Sol+Fable → committed. The current directive-form run is the baseline data point.

**Lesson recorded:** "dead-on-Gate-B" and "banned" were over-applied as reasons to drop. A default-off/dark seam is
a reason to RETARGET + gate, not to erase a pre-registered high-value lever. NLI-*shape* in a pre-gen analysis is
not the faithfulness ghost — the ghost is runtime admission-gating of generated sentences.
