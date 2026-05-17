# Codex brief review — I-rdy-017 (#513): GPG key readiness + clean-machine bundle verification

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (return THIS, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

You are reviewing the **brief / acceptance criteria** for GitHub issue #513.

---

## Codex iter-1 findings — resolutions

**P1 (tarball member-set must be verified, not just manifest-listed files).**
Resolved: §2 gains an explicit **member-set check** — `tar -tzf` the archive,
and confirm the member set equals *exactly* `{manifest.yaml,
manifest.yaml.asc} ∪ {every path in manifest.yaml's files[]}`. Verified
against `manifest_builder.py`: `manifest.files[]` lists every content file
EXCEPT `manifest.yaml` and `manifest.yaml.asc` (the manifest is serialized
after `files_bytes` is built, the `.asc` after that). Any extra/unmanifested
member or any missing member → reject. The dry-run transcript (File 4)
captures this check.

**P2 (the fingerprint cross-check needs a real trusted publication point).**
Resolved: File 5 (NEW edit) — `docs/carney_handover/one_pager.md` publishes
the demo signing-key fingerprint and adds `bundle_verification.md` to the
handover-package document list. §2's "cross-check the fingerprint against the
handover one-pager" then references a value that actually exists. Made an
explicit acceptance criterion below.

---

## Issue #513 (I-rdy-017) — verbatim

> **Workstream L. GPG signing key readiness; documented criteria for
> verifying a signed audit bundle on a clean machine with no POLARIS
> access.**
> Acceptance: clean-machine verification criteria documented and dry-run;
> Codex APPROVE.
> Depends on: none (parallel).

## Context — verified against HEAD

**The signed audit bundle.** `src/polaris_graph/audit_bundle/bundle_builder.py`
packs `audit_<bundle_id>.tar.gz` containing: `manifest.yaml`,
`manifest.yaml.asc` (a **detached, ASCII-armored GPG signature** over
`manifest.yaml`), `scope_decision.json`, `evidence_pool.json`,
`verified_report.json`, per-source snapshot files, a reviewer README, and
`metadata.json`. The manifest carries a `files[]` array with a `sha256` for
every other file in the tarball. So the trust chain is: the GPG signature
authenticates `manifest.yaml`; `manifest.yaml`'s per-file hashes authenticate
every other file. The v6 demo serves this exact artifact at
`GET /runs/{run_id}/bundle.tar.gz` (`src/polaris_v6/api/bundle.py`).

**The signing key.** `scripts/bootstrap_gpg_demo_key.sh` generates an
ed25519, signing-only, 1-year-expiry key (`%no-protection` — no passphrase,
acceptable for a demo signing key), writes the fingerprint to
`state/polaris_gpg_keyid.txt`, and exports the public key to
`outputs/polaris_demo_pubkey.asc`. `GPGSigner` (`gpg_signer.py`) reads
`POLARIS_GPG_KEY_ID` and produces the `.asc`. On this machine the demo key
already exists (fingerprint `FB221FA8ED185F8E3F76F7E6F6F31CEDFF490C02`, its
secret present in `~/.gnupg-polaris`).

**Why this issue exists.** The verification commands currently live only in
a code comment in `bundle_builder.py` (lines 27-30). There is no
operator-facing key-readiness checklist and no reviewer-facing,
POLARIS-free verification document — and `outputs/polaris_demo_pubkey.asc`
is gitignored (`outputs/` is gitignored except `codex_findings/`), so a
reviewer has no committed public key to verify against. A reviewer with no
POLARIS access cannot today follow a written procedure to confirm a bundle
is authentic.

## Approach decision — documentation + a captured dry-run, NOT a pytest

The issue says "documented **and dry-run**." A reviewer with no POLARIS
access runs **shell commands** (`gpg`, `tar`, `sha256sum`) — not pytest.
The honest proof that those shell commands work is a **captured transcript
of executing them**, against a committed sample bundle a reviewer can
re-run them against. A pytest that shells out to `gpg` would be a Python
harness asserting bash — it tests a different surface than the doc shows,
and `tests/polaris_graph/audit_bundle/test_gpg_signer.py` already proves
the signer emits `gpg --verify`-compatible output. So this PR ships a
document + a real captured transcript + the sample artifacts the transcript
was produced against. No new test, no new script, no `src/` change.

## Proposed implementation — 4 new files, all handover docs/artifacts

### File 1 (NEW) — `docs/carney_handover/bundle_verification.md`

Two clearly separated sections:

**§1 — Signing-key readiness checklist (operator-facing).** A checklist the
operator confirms before the demo:
- demo key generated via `scripts/bootstrap_gpg_demo_key.sh` — ed25519,
  signing-only, no encryption/certification capability;
- fingerprint recorded in `state/polaris_gpg_keyid.txt`;
- public key exported (`outputs/polaris_demo_pubkey.asc`) AND its
  handover copy committed at `docs/carney_handover/polaris_demo_pubkey.asc`;
- `POLARIS_GPG_KEY_ID` set in `.env` to the fingerprint; the v6 API's
  `get_sign_fn` resolves a real `GPGSigner` (else `/runs/{id}/bundle.tar.gz`
  returns 503 — unsigned bundles are structurally forbidden, LAW II);
- key **expiry** noted (1 year from generation) with the renewal trigger —
  if the key expires before the demo, re-run the bootstrap script and
  re-export both pubkey copies;
- on the Vexxhost deploy, `provision.sh` imports operator-staged keys into
  `/var/lib/polaris/gpg` and shreds the secret-key file from `/root`.

**§2 — Clean-machine verification procedure (reviewer-facing, no POLARIS
access).** The literal shell commands, using only `gpg`, `tar`, and
`sha256sum`/`shasum` — no POLARIS code, no Python imports:
1. `gpg --import polaris_demo_pubkey.asc` then `gpg --list-keys` — confirm
   the fingerprint matches the one published with the handover package.
2. `tar -tzf audit_<id>.tar.gz` — list the archive members, then
   `tar -xzf audit_<id>.tar.gz` to extract.
3. **Member-set check:** confirm the archive's member set is *exactly*
   `manifest.yaml` + `manifest.yaml.asc` + every `path` in `manifest.yaml`'s
   `files[]` — no extra/unmanifested members, none missing. An attacker who
   repacks a bundle with added members must not pass.
4. `gpg --verify manifest.yaml.asc manifest.yaml` — expect
   `gpg: Good signature from "POLARIS Carney Demo ..."`.
5. For each entry in `manifest.yaml`'s `files[]`: re-hash the named file
   (`sha256sum <file>`) and confirm it equals the recorded `sha256`.
6. Pass criteria stated explicitly: the member set matches exactly AND the
   signature is good AND every file hash matches → the bundle is authentic
   and unmodified. Any mismatch → reject.
The section also states the **distribution mechanism**: the public key
travels with the handover package (committed copy
`docs/carney_handover/polaris_demo_pubkey.asc`) on a channel separate from
any individual bundle, and a reviewer cross-checks the fingerprint against
the value published in the handover one-pager — so an attacker cannot
substitute both key and bundle.

### File 2 (NEW) — `docs/carney_handover/polaris_demo_pubkey.asc`

The committed handover copy of the demo signing key's ASCII-armored public
key (the production `outputs/polaris_demo_pubkey.asc` is gitignored). This
is the key a reviewer imports in §2 step 1. A public key is non-sensitive
by definition. If the demo key is rotated before Sep 6, this file and the
sample bundle (File 3) are regenerated together.

### File 3 (NEW) — `docs/carney_handover/sample_signed_bundle.tar.gz`

A real GPG-signed `audit_*.tar.gz`, signed by the demo key, committed so any
reviewer can reproduce the §2 dry-run exactly. Produced by a throwaway
harness (`.codex/I-rdy-017/_make_sample_bundle.py`, deleted after use — not
part of the committed `src`/`scripts`/`tests` surface) that builds a minimal
valid `ScopeDecision`/`EvidencePool`/`VerifiedReport` FK chain (mirroring
the known-good shape in `tests/polaris_graph/api/test_audit_bundle_route.py`
`_payload()`) and calls `build_audit_bundle(..., sign_fn=GPGSigner(...))`
with the demo key. A few KB; `bundle_export_sample.json` set the precedent
for committing a sample handover artifact.

### File 4 (NEW) — `docs/carney_handover/bundle_verification_dryrun.txt`

The **captured transcript** of executing every §2 command on this machine,
exactly once, against File 3. Contains: a UTC timestamp; the bundle_id; the
signing-key fingerprint; `gpg --list-keys` output for a **fresh keyring**
(proving the verification needs only the imported public key); the
`tar -tzf` member listing and the member-set check verdict (the set equals
`{manifest.yaml, manifest.yaml.asc} ∪ files[]`); the actual `gpg: Good
signature from ...` line; the `sha256sum` line for every content file with
its match/mismatch verdict; and a final `RESULT: OK` line. The transcript is
a *worked example* — the proof is reproducibility: every value in it
(bundle_id, member list, file hashes, key fingerprint) is cross-checkable by
a reviewer re-running the same commands against File 3.

### File 5 (EDIT) — `docs/carney_handover/one_pager.md`

Publish the demo signing-key fingerprint at the handover package's trusted
reference point, so §2 step 1's cross-check has a real target: add a short
"Verifying a signed audit bundle" note carrying the fingerprint and pointing
to `bundle_verification.md`, and add `bundle_verification.md` to the
"documents in this package" list (it becomes a genuine 4th package
document). This is the only existing file this PR edits; it is documentation.

## Explicitly OUT of scope (carved; do not flag as P0/P1)

- **An automated test of the per-file hash-chain** (re-hashing every
  `manifest.files[i]` against an extracted tarball) → carved to follow-up
  **#549**. That is internal bundle-integrity testing; #513's scope is the
  reviewer-facing documented + dry-run procedure. `test_gpg_signer.py`
  already covers the signer→`gpg --verify` surface.
- Rotating / HSM-backing the demo key — the demo key is intentionally a
  no-passphrase demo key per `setup_gpg_for_demo.py`'s own documented
  rationale; production HSM custody is a separate post-handover concern.
- GPG-signing the *orchestrator backup* archive — that is #547 (from #512),
  a different artifact.

## Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_bundle/bundle_builder.py` — tarball layout +
  the existing verification comment (lines 16-30); `_default_sign_fn`
  forbids unsigned bundles.
- `src/polaris_graph/audit_bundle/manifest_builder.py` — `manifest.files[]`
  carries a `sha256` per content file.
- `src/polaris_graph/audit_bundle/gpg_signer.py` — `GPGSigner` /
  `load_config_from_env` / `build_gpg_signer`; `POLARIS_GPG_KEY_ID` driven.
- `scripts/bootstrap_gpg_demo_key.sh`, `scripts/setup_gpg_for_demo.py` —
  key generation; ed25519 signing-only, 1y expiry, fingerprint + pubkey
  export paths.
- `src/polaris_v6/api/bundle.py` — the v6 `GET /runs/{id}/bundle.tar.gz`
  endpoint serves this exact bundle; 503 when no signer.
- `tests/polaris_graph/audit_bundle/test_gpg_signer.py` — ephemeral-keyring
  signer test (already proves `gpg --verify` compatibility).
- `tests/polaris_graph/api/test_audit_bundle_route.py` — `_payload()` is
  the known-good FK-chain shape the throwaway harness mirrors.
- `docs/carney_handover/` — `bundle_export_sample.json` +
  `bundle_export_sample_README.md` (the JSON-contract sample; a different
  artifact from the signed tarball — this PR does not touch them) +
  `runbook.md`, `one_pager.md`.

## Acceptance criteria for the resulting PR

1. `docs/carney_handover/bundle_verification.md` — §1 operator key-readiness
   checklist + §2 reviewer clean-machine verification procedure (literal
   `gpg`/`tar`/`sha256sum` commands, no POLARIS code), including the
   **archive member-set check** and the public-key distribution mechanism.
2. `docs/carney_handover/polaris_demo_pubkey.asc` — committed handover copy
   of the demo signing public key.
3. `docs/carney_handover/sample_signed_bundle.tar.gz` — a real demo-key-signed
   bundle for reproducible verification.
4. `docs/carney_handover/bundle_verification_dryrun.txt` — the captured
   transcript of the §2 procedure (incl. the member-set check) run against
   File 3, ending `RESULT: OK`.
5. `docs/carney_handover/one_pager.md` — publishes the demo signing-key
   fingerprint and lists `bundle_verification.md` as a package document.
6. The §2 commands and the transcript agree; the fingerprint in §2 / File 4
   matches the one published in `one_pager.md`; the transcript's values are
   reproducible by re-running §2 against File 3.

No `src`/`scripts`/`tests` change; no LOC-cap concern (docs/artifacts only).

Return the YAML verdict block only.
