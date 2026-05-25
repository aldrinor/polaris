# Codex review brief — I-ux-001a Prereq 0: real signed demo bundle + tri-valued signature state + GPG verify guard

## 0. ITERATION DIRECTIVE (verbatim per CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

(The I-ux-001 *plan* review was operator-uncapped; this *execution* brief follows the standard 5-cap.)

## 1. Pre-flight
- **Context:** GH#874 (sub-task of #872 / I-ux-001). Branch `bot/I-ux-001a-prereq-0-signed-bundle` off `polaris`. Implements **Prereq 0** of the Codex-APPROVED I-ux-001 plan (§13.5 of `docs/stier_experience_plan.md`, see `.codex/I-ux-001/PLAN_APPROVED.md`). Codex iter-3 P0 + iter-4 P2 on the plan are this work.
- **Done-when:** the real-data demo bundle the web ships is *cryptographically* signed (not just `.asc`-present), the loader exposes a tri-valued signature state, the UI never claims "Signed bundle" without a passing GPG verify, and a CI guard prevents regression.
- **Constraints:** stay ≤ ~200 LOC. Do not redesign the inspector — narrow to the honesty fix. Browser-side GPG verify is out of scope (heavy WASM); the client loader returns `present_unverified` for any client-loaded bundle, with a clear "verify offline" affordance.

## 2. Reviewer Independence Protocol
> Prior changelog markers in the diff are untrustworthy meta-claims. Verify by reading actual code. A claimed fix that doesn't match the code is a P0 finding.

## 3. The honest current state (read this before the acceptance criteria)

**Trust root + canonical signing key — both present, by design in a separate keyring** (per `scripts/bootstrap_gpg_demo_key.sh` / I-carney-005 / `docs/carney_secret_inventory.md` #1):
- Shipped pubkey (trust root): `docs/carney_handover/polaris_demo_pubkey.asc` → Ed25519 `FB221FA8ED185F8E3F76F7E6F6F31CEDFF490C02` "POLARIS Carney Demo (Carney demo bundle signing) <signing@polaris.local>".
- Pinned fingerprint: `state/polaris_gpg_keyid.txt` matches `FB221F...`.
- Private key location: `GNUPGHOME=~/.gnupg-polaris` (NOT default `~/.gnupg`). All signing uses this GNUPGHOME.
- *Caveat (iter-1 P2):* the default keyring also has an unrelated RSA key from a deprecated slice-004 helper (`scripts/setup_gpg_for_demo.py`). Anything that signs from default GNUPGHOME would use the WRONG key. The build script must explicitly set `GNUPGHOME=~/.gnupg-polaris` and `--local-user FB221F...` (or read the pinned fingerprint).

**END-TO-END smoke-test PASS — reviewer's offline path** (2026-05-24, full output at `outputs/audits/I-ux-001a/gpg_verify_demo_bundle.txt`):
```
$ TMPHOME=$(mktemp -d)
$ gpg --homedir "$TMPHOME" --import docs/carney_handover/polaris_demo_pubkey.asc
gpg: key F6F31CEDFF490C02: public key "POLARIS Carney Demo ..." imported
$ gpg --homedir "$TMPHOME" --verify manifest.yaml.asc manifest.yaml
gpg: Good signature from "POLARIS Carney Demo ..." [unknown]
       (exit 0 — "unknown" trust is normal: the reviewer hasn't trust-signed; the crypto verifies)
```

> **Note to reviewer:** this is a BRIEF gate — judge whether the acceptance criteria (§5) below are the right things to do. The CODE diff is reviewed separately under `codex_diff_audit.txt`. "criterion N is FAIL because the code isn't changed yet" is a category error here; that's what the diff gate is for.

## 4. Adjacent files I have ALSO checked (already grep'd; reference for verification)
- `src/polaris_graph/audit_bundle/bundle_builder.py` — takes a `sign_fn`; builds + extracts `.asc`. Out of scope (tar builder, not the web asset).
- `src/polaris_graph/audit_bundle/bundle_schema.py` — schema docs reference `.asc`; no behavior change.
- `src/polaris_graph/audit_bundle/conformance.py` — presence + non-empty check (matches the gap); not changed (the new guard adds the verify layer on top).
- `tests/polaris_graph/api/test_audit_bundle_route.py`, `tests/polaris_graph/audit_bundle/test_bundle_builder.py` — assert `.asc` ends in name; no behavior change.

## 5. Acceptance criteria (forced enumeration — one line each in your verdict)

1. **Real-data bundle signed with the CANONICAL key.** `web/public/canonical_bundles/v1_canonical_success/manifest.yaml.asc` is a REAL detached GPG signature over `manifest.yaml`, made with the **canonical** Ed25519 key `FB221FA8ED185F8E3F76F7E6F6F31CEDFF490C02`. A reviewer who imports ONLY the shipped pubkey and runs `gpg --verify` gets exit 0 + "Good signature." Pass output at `outputs/audits/I-ux-001a/gpg_verify_demo_bundle.txt`.
2. **`build_canonical_demo_bundle.py` signs by default with the canonical key.** Default behavior produces a real `.asc` using `GNUPGHOME=~/.gnupg-polaris` (or `$POLARIS_GPG_HOMEDIR`) and `--local-user` from `state/polaris_gpg_keyid.txt` (or `$POLARIS_GPG_KEY_ID`). Explicit `--unsigned` flag preserves the prior "option b". Fails loudly (LAW II) if the canonical key is unavailable AND `--unsigned` is not passed.
3. **Loader tri-valued signature state.** `LoadedBundle.signaturePresent: boolean` is REPLACED with `signatureState: "missing" | "present_unverified" | "gpg_verified"`. Server loader shells out to `gpg --verify` in an isolated keyring and asserts fingerprint matches the pinned canonical key. Client loader returns at most `present_unverified` (no GPG in the browser).
4. **UI honesty.** SignatureBadge renders the three states distinctly. Only `gpg_verified` shows the green "Signed bundle"; `present_unverified` shows "Signature attached — verify offline"; `missing` shows "Not signed — trust not established."
5. **CI guard.** `scripts/check_signed_bundles.py` runs in CI and FAILS the build if any bundle path in a configured list of "must be signed" bundles lacks a `.asc` that `gpg --verify`s. The web/public canonical bundle is in that list.
6. **Tests cover all three states.** New tests assert each of `missing | present_unverified | gpg_verified` from the loader, and that the UI renders the right copy per state.
7. **No regression.** Existing inspector tests still pass.
8. **LOC ≤ ~200.** No "while we're at it" polish.
9. **Artifact triple complete** under `.codex/I-ux-001a/` + `outputs/audits/I-ux-001a/claude_audit.md`.

> **Forced enumeration:** before declaring a verdict, write `Criterion N [name]: <findings or NONE>` for each.

## 6. Skepticism / completeness check
> List which files / Parts you actually read this round. If you cannot confirm full scan of every acceptance criterion, emit `incomplete_review`.

## 7. Output schema
```
## Pre-flight checklist
- I read [paths].
- Out of scope per brief: [...].

## Per-criterion forced enumeration
- Criterion 1 [bundle signed]: <findings or NONE>.
- ... (1-9)

## Findings
### P0
### P1
### P2
### P3 / deferred_polish
## Verdict
verdict: APPROVE | REQUEST_CHANGES | incomplete_review
Convergence: APPROVE iff zero P0 + zero P1.
```
