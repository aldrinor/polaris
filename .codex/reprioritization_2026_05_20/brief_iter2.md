# Codex serious review — POLARIS Carney RE-PRIORITIZATION (iter 2 of 5)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What changed since iter 1 (all 4 P1s + 5 P2s addressed)

v2 of `state/polaris_carney_reprioritization_2026_05_20.md`:
1. **NEW PHASE 1 real-run backend foundations** put FIRST: #682 metadata schema (precedes #680), #680 EvidenceContract-for-real-runs, + 2 NEW backend issues — I-cd-be-001 (GET /api/v6/runs?status=completed list endpoint) and I-cd-be-002 (SSE sub-task event instrumentation in the live producer).
2. **#542 + #543 moved to PHASE 2 and made DEPENDENT on #680 + the list endpoint**; acceptance now requires REAL completed run IDs, not golden fixtures; deployed-VM real-run screenshots.
3. **Staged-progress run UI (P2-2 I-cd-ui-002) now depends on P1-4 SSE instrumentation.**
4. **#699 KEPT OPEN as renewal-watch** (cert expires Aug 17 < demo Aug 31); explicit P7-3 renewal gate (notAfter past Sep 7 + post-Aug-17 Caddy renewal log). Only #636 closes.
5. **P4-2 freezes the 10-question pack + rubric + model IDs** for PHASE-7 sovereign re-run comparability.
6. **P4-4 (#629/#539 resume) stays OPEN as documented gap if checkpoint infra absent** — not marked working.
7. **#567 interim-risk note** on P5-1 + manual artifact-gate discipline reminder.

## Review focus (iter 2)

1. Are the 4 iter-1 P1s genuinely closed by v2's restructure? Any residual fixture-only / missing-backend dependency I mislabeled as resolved?
2. The 2 NEW backend issues (I-cd-be-001 list endpoint, I-cd-be-002 SSE instrumentation) — are they scoped correctly + in the right phase? Any OTHER missing backend foundation the UI silently needs (e.g. does the home recent-runs strip or the follow-up picker need anything beyond the list endpoint)?
3. Within PHASE 1, is #682 → #680 → list-endpoint → SSE the right internal order?
4. Does #704 (UI visual overhaul, already iter-1 deployed) belong in PHASE 2 AFTER the PHASE-1 backend foundations, or can the pure-visual part proceed in parallel since it doesn't strictly need real-run data? (It's partly done — branch bot/I-cd-ui-001 has the home redesign deployed.)
5. Any NEW P0/P1 introduced by the restructure itself.

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

## Full v2 document under review (read state/polaris_carney_reprioritization_2026_05_20.md directly)
# POLARIS — Carney demo RE-PRIORITIZATION (2026-05-20, v2 — Codex iter-1 P1s folded in)

## Why this exists

Operator flag 2026-05-20: the original strict global sequence (Seq 1-48, `polaris_carney_issue_breakdown_2026_05_19.md`) was marched **mechanically**, treating "issue merged = feature done." Result: GPU-procurement substrate (Seq 37) was being shipped while (a) the deployed UI at https://polarisresearch.ca is still ugly/un-demo-grade and (b) the live-run journey was never validated through the browser. **The priority was fundamentally backwards.** GPU procurement is months away (demo 2026-08-31..09-06) AND OpenRouter is a working fallback, so sovereign GPU is the LAST thing, not a current spend.

**Codex serious review (iter 1) confirmed the problem is deeper than ordering:** several "carved-from-#510" UI issues (#542 follow-up, #543 compare) have **fixture-only backends that 404 on real runs**, and the staged-progress SSE events don't exist in the live producer. So the re-prioritization must put **real-run backend foundations FIRST**, then the UI that depends on them. v2 reflects this.

## Standing correction to the execution model

- **"Merged" ≠ "done."** Every issue with a user-facing surface closes ONLY after an authenticated browser walkthrough screenshot proves it **against a REAL run (not a golden fixture)** on the deployed VM (per `feedback_plan_from_running_system_not_docs` + `bpei_phantom_completion_lessons`).
- **No GPU spend** until the product is demo-grade AND the operator re-raises it.
- **Codex serious review** on this re-prioritization first, then on each issue's brief + diff.

---

## Already DONE but left OPEN — disposition

- **#636 (I-cd-036 Caddy/TLS)** — the deployed VM already runs `polaris-caddy-1` with a valid Let's Encrypt cert for `polarisresearch.ca` (verified 2026-05-20 via VM logs + `openssl s_client`). Acceptance met. **CLOSE.**
- **#699 (I-cd-036-followup domain+cert)** — **KEEP OPEN as a renewal-watch** (Codex iter-1 P1). The cert expires 2026-08-17, BEFORE the demo window (Aug 31). Caddy ACME auto-renewal is live, but #699's acceptance is rewritten to: P7-renewal-gate verifies `notAfter` is past 2026-09-07 AND Caddy renewal logs show a successful post-Aug-17 renewal. Do NOT close until that gate passes.

---

## NEW priority order (P-phases) — v2 dependency-correct

### PHASE 1 — Real-run backend foundations (unblocks every UI surface; do FIRST)

| P# | GH# | Title | Acceptance |
|---|---|---|---|
| P1-1 | #682 | metadata.json schema reconciliation (producer ↔ frozen v1.0 fixture) | producer emits the v1.0 schema; conformance test green. **Precedes #680** (inspector/bundle path consumes metadata.json — Codex iter-1 P2). |
| P1-2 | #680 | EvidenceContract for real runs (pipeline-A capability extension) | a REAL completed run (not a golden fixture) yields per-claim provenance JSON the inspector + follow-up + compare can consume; deployed-VM real-run acceptance |
| P1-3 | (new) I-cd-be-001 | `GET /api/v6/runs?status=completed&limit=N` list endpoint | returns real completed runs; needed by compare (#543), follow-up picker, and the home recent-runs strip (Codex iter-1 P2) |
| P1-4 | (new) I-cd-be-002 | SSE sub-task event instrumentation in the live producer | producer emits retrieval/generation/verification sub-task events (not just scope + terminal) so the staged-progress UI has real data (Codex iter-1 P1) |

### PHASE 2 — The demo surface is beautiful + the journey is complete (depends on PHASE 1)

| P# | GH# | Title | Acceptance |
|---|---|---|---|
| P2-1 | #704 | UI visual identity overhaul | warm-editorial-institutional rebuild; authenticated walkthrough screenshots on the deployed VM against a REAL run; operator visual sign-off |
| P2-2 | (new) I-cd-ui-002 | `/runs/[runId]` staged-progress UI | consumes P1-4 SSE events; 4 staged sections (Scope/Retrieval/Generation/Verification) with sub-task streaming + word/elapsed counters; screenshot on deployed VM during a real run |
| P2-3 | #542 | Follow-up answer UI | works on REAL completed run IDs (depends on P1-2 #680); Ask-follow-up enabled on `/runs/[runId]`; G1-G8; deployed real-run screenshot |
| P2-4 | #543 | Run-compare view | works on REAL completed run IDs (depends on P1-2 #680 + P1-3 list endpoint); G1-G8; deployed real-run screenshot |

### PHASE 3 — Run output is audit-grade (what Carney reads)

| P# | GH# | Title | Acceptance |
|---|---|---|---|
| P3-1 | #702 | Report sections repeat citations verbatim | cross-section dedup; regression check on bigram overlap |
| P3-2 | #703 | Bill C-27/AIDA + IP retention underspecified | ai_sovereignty template names AIDA-specific primary sources; fresh real run covers the mechanism |
| P3-3 | #675 | Audit bridge model='unknown' fallback | bundle records true generator/evaluator model ids |
| P3-4 | #676 | GPG signer preflight shallow | preflight proves signing readiness, not just key presence |
| P3-5 | #537 | Document-grounding follow-up | uploaded document_ids consumed end-to-end with count cap + error path |

### PHASE 4 — Live journey validated end-to-end (prove it, don't assume it)

| P# | GH# | Title | Acceptance |
|---|---|---|---|
| P4-1 | #634 (+#696) | Run the 24-row test matrix against the LIVE VM | matrix executed via authenticated session on polarisresearch.ca; results recorded; #696 folds in |
| P4-2 | #473 | Live-submission rehearsal: 10 questions — **FROZEN PACK** | 5 canonical Carney + 5 staff-style; freeze the exact 10 questions + prompts + rubric + model IDs + audit schema so PHASE 6 sovereign re-run is comparable not drift-prone (Codex iter-1 P2); signed bundles saved |
| P4-3 | #403 (+#648) | §-1.1 line-by-line per-claim audit of the 10 runs | Claude + Codex parallel; per-claim VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE |
| P4-4 | #629 (+#539) | Hard-kill / resume-from-checkpoint | mid-run kill + resume works. **If checkpoint infra is absent, this issue STAYS OPEN as a documented gap — do NOT mark resume working** (Codex iter-1 P2). |

### PHASE 5 — Infra hygiene (real, not demo-blocking; but #567 carries interim risk)

| P# | GH# | Title | Note |
|---|---|---|---|
| P5-1 | #567 | codex-artifact-gate CI workflow inert (not on default branch) | **Interim risk (Codex iter-1 P2): until this lands, PRs touching `.codex/**` need manual artifact-gate + secret-scan discipline.** Consider pulling earlier if it actually gates nothing today. |
| P5-2 | #589 | Stop hook to block fake-pause turn-ends |  |
| P5-3 | #658 | _verify_canonical_pin unwired in stop hook + CRLF false-positive |  |
| P5-4 | #432 | Surgical POLARIS root + .codex/ cleanup |  |

### PHASE 6 — Sovereign GPU (DEAD LAST — demo months away, OpenRouter is the working fallback; NO SPEND until operator re-raises)

| P# | GH# | Title | Gate |
|---|---|---|---|
| P6-1 | #641 (#88,#87) | FP4 readiness spike + serving-engine/topology confirm | GL gate |
| P6-2 | #642 | Final OVH capacity hold/confirm (runbook shipped) | — |
| P6-3 | #643 (#90) | OVH GPU provisioning order (operator-authorized, $) | GL gate + operator $ |
| P6-4 | #644 | Sovereign window Session A: both boxes up + serving test | GL gate |
| P6-5 | #645 (#200,#201) | Sovereign regression Session B p1 | GL gate |
| P6-6 | #646 (#202,#203) | Two-family re-verify + migration fixes Session B p2 | GL gate |

### PHASE 7 — Demo endgame (final week before Aug 31)

| P# | GH# | Title | Gate |
|---|---|---|---|
| P7-1 | #647 (#473) | Session C dress rehearsal — the FROZEN 10-question pack on sovereign GPU | GL gate |
| P7-2 | #649 | G1 full sovereign dress rehearsal | GL gate |
| P7-3 | (in #699) | **TLS renewal gate** — verify cert notAfter past 2026-09-07 + Caddy post-Aug-17 renewal log | — |
| P7-4 | #650 | Fallback drill — offline bundle + disclosed recording | — |
| P7-5 | #651 (#204) | Final walkthrough + Codex sweep | — |
| P7-6 | #652 (#205) | Handover package | — |
| P7-7 | #653 (#206) | The Carney demo | GL gate |

---

## What changed vs the 2026-05-19 sequence

1. **GPU cluster (old Seq 37-46) → PHASE 6/7 (last).** No GPU spend now.
2. **NEW PHASE 1 real-run backend foundations** (#682, #680, + 2 new backend issues) — Codex iter-1 found the UI work is blocked by fixture-only backends; foundations come first.
3. **Run-quality bugs → PHASE 3** (what Carney reads).
4. **UI quality + journey + staged-progress → PHASE 2**, now correctly DEPENDENT on PHASE 1.
5. **Live-journey validation → PHASE 4** with a FROZEN 10-question pack for PHASE-7 comparability.
6. **#636 closed; #699 KEPT OPEN as renewal-watch** (cert expires before demo).
7. **2 new backend issues surfaced** (list endpoint, SSE instrumentation) that no prior issue covered.

## Codex iter-1 findings → how v2 closes them

- P1 #542 fixture-only → P1-2 #680 (real-run EvidenceContract) now PRECEDES #542; #542 acceptance requires real-run IDs.
- P1 #543 fixture-only → same; #543 depends on #680 + the new list endpoint (P1-3).
- P1 staged-progress SSE missing → new P1-4 backend SSE instrumentation precedes the staged-progress UI (P2-2).
- P1 #699 close unsafe → #699 KEPT OPEN; explicit P7-3 renewal gate.
- P2 #682 before #680 → reordered (P1-1 before P1-2).
- P2 double-rehearsal correct → kept; P4-2 freezes the question pack for P7 comparability.
- P2 #567 interim risk → noted on P5-1 + manual-discipline reminder.
- P2 resume-may-degrade → P4-4 now explicitly stays open as documented gap if infra absent.
- P2 list endpoint missing → new P1-3.
