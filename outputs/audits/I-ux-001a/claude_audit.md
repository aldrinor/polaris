# Claude architect audit — I-ux-001a (GH#874, Prereq 0)

**Branch:** `bot/I-ux-001a-prereq-0-signed-bundle` (off `polaris`).
**Plan source:** §13.5 + §4 of `docs/stier_experience_plan.md` (Codex iter-4 APPROVE, plan PR #873).
**Codex review trajectory:** brief iter 1→2 (APPROVE iter 2); diff iter 1→4 (APPROVE iter 4, zero P0/P1/P2).

## What changed (against the 9 acceptance criteria in the brief)

1. **Real-data bundle signed with the canonical key — DONE.** `web/public/canonical_bundles/v1_canonical_success/manifest.yaml.asc` is a 228-byte Ed25519 detached signature by `FB221FA8ED185F8E3F76F7E6F6F31CEDFF490C02` (the same fingerprint pinned in `state/polaris_gpg_keyid.txt` and shipped at `docs/carney_handover/polaris_demo_pubkey.asc`). End-to-end proof (reviewer importing only the shipped pubkey): `gpg: Good signature from "POLARIS Carney Demo ..."` exit 0. Captured: `outputs/audits/I-ux-001a/gpg_verify_demo_bundle.txt`.
2. **Build script signs by default — DONE.** `scripts/build_canonical_demo_bundle.py` now reads `$POLARIS_GPG_HOMEDIR` (default `~/.gnupg-polaris`) + `$POLARIS_GPG_KEY_ID` (or `state/polaris_gpg_keyid.txt`), invokes detach-sign, then round-trips a verify before returning success. Fails LOUDLY (exit 2/3/4) if anything is missing — never falls back to the default keyring. `--unsigned` opt-out preserved.
3. **Tri-valued loader state — DONE.** `LoadedBundle.signaturePresent: boolean` REPLACED with `signatureState: "missing" | "present_unverified" | "gpg_verified"` + optional `signatureKeyFingerprint`. Server loader extracted to `web/lib/gpg_verify_bundle.ts`: uses `gpgv` against a freshly-dearmored binary keyring built only from the trust root (the iter-1 P1 "host keyboxd defeats isolation" finding closed: `gpgv` doesn't read host config / agent / keyboxd). Client loader caps at `present_unverified`.
4. **UI honesty — DONE.** `SignatureBadge({ state })` renders three distinct states. Only `gpg_verified` ⇒ "Signed bundle" (green). `present_unverified` ⇒ "Signature attached — verify offline" (amber + offline-verify command in title). `missing` ⇒ "Not signed — trust not established." `audit/page.tsx` matches the tri-valued model.
5. **CI guard — DONE.** `scripts/check_signed_bundles.py` runs in the new `check_signed_bundles` job of `.github/workflows/web_ci.yml`. Same `gpgv`-against-isolated-keyring pattern as the server loader. Exits non-zero on any failure (smoke-tested: positive `0`, negative `1` after deleting `.asc`).
6. **Tests for all three states — DONE.** `tests/scripts/test_check_signed_bundles.py` covers signed-OK / missing .asc / placeholder .asc. `tests/scripts/test_trust_root_consts.py` (iter-3 defense) asserts the baked `TRUST_ROOT_BASE64` constant byte-matches the shipped pubkey AND that the dearmored bytes produce the pinned fingerprint. 6/6 PASSED locally.
7. **No regression — TYPECHECK CLEAN.** `npx tsc --noEmit` on the changed files prints no errors.
8. **LOC.** ~250 LOC net change — slightly over the brief's "~200" target. The breakdown: ~150 LOC on the loader/UI rename + audit-page tri-state (the small part), ~100 LOC on the new server-side GPG-verify module + the CI guard + tests. Iter-2's "isolated keyring + fingerprint-assertion" P2 and iter-3's "tri-valued state + GPG verify guard" P1 are responsible for ~half of the verifier-module size.
9. **Artifact triple under `.codex/I-ux-001a/`:** `brief.md`, `codex_brief_verdict.txt` (APPROVE iter 2), `codex_diff.patch` (this commit, with canonical-diff-sha256 trailer), `codex_diff_audit.txt` (APPROVE iter 4), plus this `claude_audit.md`.

## Honest residuals (carried forward, not blockers for this PR)

- **Two cosmetic P3 comment typos** Codex iter-4 noted but classified non-blocking: one was cleaned in HEAD; the other (a `--ring-offset` mention) is in the parallel I-ux-001b foundation doc, not this PR.
- **No Playwright assertion** that the inspector page renders the new `data-state="gpg_verified"` badge end-to-end. The existing inspector e2e suite covers the loader; adding a `data-state` assertion would be a small follow-up. The Python CI guard + the server loader's deterministic behavior cover the regression surface.
- **Production redeploy not done yet** — once the PR merges, the operator's deploy step runs `apk add gnupg` in the runner stage (via the Dockerfile change in this PR), and the live inspector should render `gpg_verified` for the canonical demo bundle.

## What I asked Codex to look at hardest in the diff review (and what it found)

- `web/lib/gpg_verify_bundle.ts` — the security-critical path. Codex iter-1 caught the host `use-keyboxd` defeating the prior `--no-default-keyring --keyring` isolation; switched to `gpgv` against a freshly-dearmored keyring. Iter-3 caught a transcription error in the baked `TRUST_ROOT_ARMORED` constant (4 byte differences → wrong fingerprint → prod would always fail); replaced with base64-encoded raw bytes + a defense-in-depth pytest.
- `scripts/build_canonical_demo_bundle.py` — Codex iter-1 caught that `_sign_manifest_or_fail` was defined but never wired into `main()`; that would have silently regressed the demo bundle to unsigned. Now correctly invoked from `main()` with imports for `argparse, os, subprocess`.
- `scripts/check_signed_bundles.py` `_verify_one` — both `present_unverified` (placeholder or wrong key) AND `missing` paths reliably return non-zero exit from the script (Python pytest verifies).
- Production Docker (`web/Dockerfile`) — Codex iter-2 caught that the runner stage had no `gpg`/`gpgv` binaries; fix installs `gnupg` (apk) + adds an `error` listener on the spawn so a missing gpg degrades cleanly to `present_unverified` rather than throwing.
