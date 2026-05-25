# I-ux-001 S-tier experience plan — CODEX APPROVED (iter 4)

**Status:** `docs/stier_experience_plan.md` v4 — **verdict: APPROVE**, `convergence_call: accept_remaining` (Codex iter 4, 2026-05-24). Zero P0, zero P1.

**Iteration trajectory (uncapped per operator 2026-05-24):**
| iter | verdict | what moved |
|---|---|---|
| 1 | REQUEST_CHANGES | overclaimed uniqueness (competitors do exact-quote citation); route-centric not artifact-centric; hero = "nice citation UI"; missing clinical-quality layer |
| 2 | REQUEST_CHANGES | clinical-safety method (GRADE per-sentence was wrong); regulatory/intended-use posture; verifier over-trust |
| 3 | REQUEST_CHANGES | one honest P0 — the "signed bundle" is not actually signed (no real `manifest.yaml.asc`; fixture `.asc` is placeholder) |
| 4 | **APPROVE** | Prereq-0 signed-bundle honesty gate; operational abstention/SoF launch gate; verifier release gate; non-use exclusions |

**Locking note:** `.codex/REVIEW_BRIEF_FORMAT.md` suggests two consecutive independent APPROVEs; Codex's explicit `accept_remaining` convergence call + zero P0/P1 at iter 4, under the operator's uncapped "iterate until Codex approves" directive, is the lock. Per §8.3.6 (respect Codex's convergence call) we do NOT iterate past a converged APPROVE.

## Non-blocking residuals → carry into EXECUTION tickets (Codex iter-4)

- **P2 — tri-valued signature state.** Model signature as `missing | present_unverified | gpg_verified`, NOT boolean `signaturePresent`. Today `web/components/inspector/bundle_header.tsx:76` can show "Signed bundle" from mere `.asc` presence, while `web/lib/inspector_bundle_client_loader.ts:19` says GPG verify is out of scope. This is the exact spot the Prereq-0 honesty gate could regress in implementation → fix when building the Receipt/Inspector (§11/§13.5).
- **P3 — name the config paths.** Verifier gold-set threshold + SoF threshold config file paths must be named in their implementation tickets (config-backed per LAW VI), to reduce drift.

## Next: EXECUTION per approved §14
0. **Prerequisite 0 (§13.5):** a REAL signed demo bundle + signed-language guard (investigate signing-key material; if none, `state/stier_halt_signing_key.md`). Gates all "signed" UI claims.
1. **Design + motion foundation + Figma/motion prototype of the hero** (6-beat) — Codex reviews prototype via `-i` BEFORE code.
2. Component system to spec.
3. Hero (Report/Inspector + Home teaser), "signed" affordances gated on Prereq 0.
4. Clinical evidence-strength layer + intended-use + verifier-honesty.
5. Journey views (failure states designed).
6. Supporting surfaces.
7. #871 in PARALLEL (live-demo reliability blocker).
8. PM 90-second demo script.

Per page: issue → brief → Codex brief review → build → Codex 16-dim visual audit (`codex exec -i`) → Codex diff review → merge → redeploy → screenshot-verify LIVE → close.
