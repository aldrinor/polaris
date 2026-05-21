# Codex serious review — POLARIS Carney demo RE-PRIORITIZATION

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1 findings.
- If you detect "I'm holding back a P1 for the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

POLARIS is a sovereign-Canadian deep-research AI, a one-shot gift for PM Mark Carney (demo 2026-08-31..09-06). It is ALREADY DEPLOYED + live at https://polarisresearch.ca (OVH BHS5 Québec VM, OpenRouter backend with deepseek/deepseek-v4-pro generator + google/gemma-4-31b-it evaluator; sovereign GPU not yet provisioned). A live end-to-end run was verified working 2026-05-20 (real AI-sovereignty question → 3178-word report, two-family verified, Gemma flagged real flaws).

The operator flagged that the original strict global sequence (`state/polaris_carney_issue_breakdown_2026_05_19.md`, Codex-APPROVED at iter 2 on 2026-05-19) was being marched MECHANICALLY: GPU-procurement substrate was being shipped while the deployed UI is still ugly and the live-run journey was never validated through the browser. Priority was backwards.

## What you are reviewing

`state/polaris_carney_reprioritization_2026_05_20.md` (the re-prioritization, full text below). It re-orders the 46 still-open GitHub issues into 6 phases:
- PHASE 1: UI beauty + journey completeness (#704, new staged-progress run UI, #542, #543)
- PHASE 2: run output audit-grade (#702, #703, #675, #676, #680, #682, #537)
- PHASE 3: live-journey validation (#634/#696, #473, #403/#648, #629/#539)
- PHASE 4: infra hygiene (#567, #589, #658, #432)
- PHASE 5: sovereign GPU — DEAD LAST, no spend (#641, #642, #643, #644, #645, #646)
- PHASE 6: demo endgame (#647, #649, #650, #651, #652, #653)

Plus: close #636 + #699 (already done on the deployed VM).

## Review focus (be serious + adversarial)

1. **Dependency correctness** — is any PHASE-1/2/3 issue secretly blocked by a PHASE-5 GPU issue, or by a backend route that doesn't exist? Specifically #542 (follow-up answer UI) and #543 (run-compare view) — do they need new backend endpoints?
2. **Double-rehearsal risk** — PHASE 3 runs the rehearsal/audit (#473/#403) on OpenRouter NOW; PHASE 6 re-runs dress rehearsals on sovereign GPU pre-demo. Is rehearsing twice correct, or does it waste effort / create drift?
3. **Is closing #636/#699 safe?** The Let's Encrypt cert expires Aug 17 2026, BEFORE the demo window (Aug 31). Caddy ACME auto-renewal is live (confirmed via container logs). The re-prioritization adds a pre-demo renewal-verification step. Sufficient, or should #699 stay open as a renewal-watch?
4. **Sequencing within PHASE 2** — are the run-quality bugs ordered right? (e.g. should #680 EvidenceContract-for-real-runs precede #682 metadata-schema since inspector depends on both?)
5. **Missing work** — does pulling product-quality forward EXPOSE any gap the old sequence hid? e.g. is there a backend endpoint (GET /api/v6/runs list) needed for a "recent runs" home strip that no issue covers?
6. **Staged-progress run UI (P1-2)** — separate new issue, or fold into #704? Which gives a cleaner Codex-reviewable diff?
7. **Anything in PHASE 4 hygiene that is actually demo-blocking** and mis-filed as low priority? (#567 codex-artifact-gate inert = the CI gate may not be enforcing artifact triples — does that undermine the whole review process?)

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

## Full re-prioritization document under review

(see `state/polaris_carney_reprioritization_2026_05_20.md` in the repo — read it directly)
# POLARIS — Carney demo RE-PRIORITIZATION (2026-05-20, v1 — DRAFT, awaiting Codex serious review)

## Why this exists

Operator flag 2026-05-20: the original strict global sequence (Seq 1-48, `polaris_carney_issue_breakdown_2026_05_19.md`) was marched **mechanically**, treating "issue merged = feature done." Result: GPU-procurement substrate (Seq 37) was being shipped while (a) the deployed UI at https://polarisresearch.ca is still ugly/un-demo-grade and (b) the live-run journey was never validated through the browser. **The priority was fundamentally backwards.** GPU procurement is months away (demo 2026-08-31..09-06) AND OpenRouter is a working fallback, so sovereign GPU is the LAST thing, not a current spend.

This document re-orders the **46 still-open** issues by *true demo value*: the surface Carney sees and touches first, the sovereign GPU dead last. Same per-issue discipline (analyze → code → test → Codex brief+diff → fix → APPROVE/iter-5-cap), same standing gates (G1-G8 for UI, GL gate for GPU).

## Standing correction to the execution model

- **"Merged" ≠ "done."** Every issue with a user-facing surface closes ONLY after an authenticated browser walkthrough screenshot proves it on the deployed VM (per `feedback_plan_from_running_system_not_docs` + `bpei_phantom_completion_lessons`).
- **No GPU spend** until the product is demo-grade AND the operator re-raises it.
- **Codex serious review** on this re-prioritization first, then on each issue's brief + diff.

---

## Already DONE but left OPEN — close as part of cleanup (×2)

- **#636 (I-cd-036 Caddy/TLS)** — the deployed VM already runs `polaris-caddy-1` with a valid Let's Encrypt cert for `polarisresearch.ca` (verified 2026-05-20 via VM logs + `openssl s_client`). Acceptance met. CLOSE.
- **#699 (I-cd-036-followup domain+cert)** — `polarisresearch.ca` resolves to the VM with a valid cert (notBefore May 19, notAfter Aug 17 2026). Acceptance met. CLOSE. (Note: cert expires Aug 17, BEFORE the demo window Aug 31-Sep 6 — auto-renewal is live per ACME polling in Caddy logs, but P5-3 below adds a pre-demo renewal verification.)

---

## NEW priority order (P-phases)

### PHASE 1 — The demo surface is beautiful + the journey is complete (HIGHEST)

| P# | GH# | Title | Why first | Acceptance |
|---|---|---|---|---|
| P1-1 | #704 | UI visual identity overhaul | The thing Carney sees on sight. Currently ugly (operator-confirmed). | warm-editorial-institutional rebuild; authenticated walkthrough screenshots on the deployed VM; operator visual sign-off |
| P1-2 | (new) | `/runs/[runId]` staged-progress UI | The most-watched moment of the live demo (5-15 min run). | 4 staged sections (Scope/Retrieval/Generation/Verification) with sub-task streaming via SSE; screenshot |
| P1-3 | #542 | Follow-up answer UI (carved from #510) | Journey completeness — a reviewer asks a follow-up after the report. | G1-G8; screenshot |
| P1-4 | #543 | Run-compare view (carved from #510) | Journey completeness — compare two runs / pin dates. | G1-G8; screenshot |

### PHASE 2 — Run output is audit-grade (what Carney reads)

| P# | GH# | Title | Acceptance |
|---|---|---|---|
| P2-1 | #702 | Report sections repeat citations verbatim | cross-section dedup; regression check on bigram overlap |
| P2-2 | #703 | Bill C-27/AIDA + IP retention underspecified | ai_sovereignty template names AIDA-specific primary sources; fresh run covers the mechanism |
| P2-3 | #675 | Audit bridge model='unknown' fallback | bundle records true generator/evaluator model ids |
| P2-4 | #676 | GPG signer preflight shallow | preflight proves signing readiness, not just key presence |
| P2-5 | #680 | EvidenceContract for real runs | inspector renders real-run per-claim provenance JSON |
| P2-6 | #682 | metadata.json schema reconciliation | producer matches frozen v1.0 fixture |
| P2-7 | #537 | Document-grounding follow-up | uploaded document_ids consumed end-to-end with count cap + error path |

### PHASE 3 — Live journey validated end-to-end (prove it, don't assume it)

| P# | GH# | Title | Acceptance |
|---|---|---|---|
| P3-1 | #634 (+#696) | Run the 24-row test matrix against the LIVE VM | matrix executed via authenticated session on polarisresearch.ca; results recorded; #696 folds in (self-run now that we have access) |
| P3-2 | #473 | Live-submission rehearsal: 10 questions | 5 canonical Carney + 5 staff-style, signed bundles saved |
| P3-3 | #403 (+#648) | §-1.1 line-by-line per-claim audit of the 10 runs | Claude + Codex parallel; per-claim VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE |
| P3-4 | #629 (+#539) | Hard-kill / resume-from-checkpoint | mid-run kill + resume works (infra-gated; may degrade to documented-gap if checkpoint infra absent) |

### PHASE 4 — Infra hygiene (real, not demo-blocking)

| P# | GH# | Title |
|---|---|---|
| P4-1 | #567 | codex-artifact-gate CI workflow inert (not registered on default branch) |
| P4-2 | #589 | Stop hook to block fake-pause turn-ends |
| P4-3 | #658 | _verify_canonical_pin unwired in stop hook + CRLF false-positive |
| P4-4 | #432 | Surgical POLARIS root + .codex/ cleanup |

### PHASE 5 — Sovereign GPU (DEAD LAST — demo months away, OpenRouter is the working fallback; NO SPEND until operator re-raises)

| P# | GH# | Title | Gate |
|---|---|---|---|
| P5-1 | #641 (#88,#87) | FP4 readiness spike + serving-engine/topology confirm | GL gate |
| P5-2 | #642 | Final OVH capacity hold/confirm (runbook already shipped) | — |
| P5-3 | #643 (#90) | OVH GPU provisioning order (operator-authorized, $) | GL gate + operator $ |
| P5-4 | #644 | Sovereign window Session A: both boxes up + serving test | GL gate |
| P5-5 | #645 (#200,#201) | Sovereign regression Session B p1 | GL gate |
| P5-6 | #646 (#202,#203) | Two-family re-verify + migration fixes Session B p2 | GL gate |

### PHASE 6 — Demo endgame (final week before Aug 31)

| P# | GH# | Title | Gate |
|---|---|---|---|
| P6-1 | #647 (#473) | Session C dress rehearsal — 10 questions, signed bundles | GL gate |
| P6-2 | #649 | G1 full sovereign dress rehearsal | GL gate |
| P6-3 | #650 | Fallback drill — offline bundle + disclosed recording | — |
| P6-4 | #651 (#204) | Final walkthrough + Codex sweep | — |
| P6-5 | #652 (#205) | Handover package | — |
| P6-6 | #653 (#206) | The Carney demo | GL gate |

---

## What changed vs the 2026-05-19 sequence

1. **GPU cluster (old Seq 37-46) → PHASE 5/6 (last).** No GPU spend now.
2. **Run-quality bugs (#702/#703/#675/#676/#680/#682) → PHASE 2 (was scattered/post-hoc).** These are what Carney reads.
3. **UI quality (#704) + journey completeness (#542/#543) + staged-progress run UI → PHASE 1 (was treated as done at code-merge).**
4. **Live-journey validation (#634/#473/#403) → PHASE 3 (was end-of-line).** Pulled forward — proving the product works is higher value than provisioning hardware for a months-away demo.
5. **#636/#699 closed** — already done on the deployed VM.
6. **#542/#543 surfaced** — carved-from-#510 journey pieces that the 2026-05-19 breakdown folded into A-14 but never actually built.

## Open questions for Codex serious review

1. Is any PHASE-1/2/3 issue secretly blocked by a PHASE-5 GPU issue? (I believe NO — OpenRouter unblocks all product work — but verify.)
2. Is the staged-progress run UI (P1-2) better as part of #704 or a separate new issue?
3. Does pulling #403/#473 (rehearsal + audit) to PHASE 3 create a problem if they're later re-run on sovereign GPU in PHASE 6? (i.e. do we rehearse twice — once on OpenRouter now, once on sovereign GPU pre-demo?)
4. Any dependency in #542/#543 (follow-up UI, run-compare) on backend routes that don't exist yet?
5. Is closing #636/#699 safe given the cert expires Aug 17 (before demo)? P5-3/P6 add renewal verification — sufficient?
