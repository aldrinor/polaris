# Claude architect audit — I-rdy-017 (#513)

**Issue:** Workstream L — GPG signing-key readiness; documented + dry-run
clean-machine verification of a signed audit bundle.
**Branch:** `bot/I-rdy-017-bundle-verification` off `polaris`.
**Canonical diff sha256:** `d152b03641a7fb2e0883d26dbf6171f30af0692a300f6ccd49eb4345256eb408`

## What shipped

| File | Change |
|---|---|
| `docs/carney_handover/bundle_verification.md` | NEW — §1 key-readiness checklist + §2 reviewer procedure |
| `docs/carney_handover/polaris_demo_pubkey.asc` | NEW — committed handover copy of the demo signing public key |
| `docs/carney_handover/sample_signed_bundle.tar.gz` | NEW — a real demo-key-signed bundle for reproducible verification |
| `docs/carney_handover/bundle_verification_dryrun.txt` | NEW — captured §2 dry-run, `RESULT: OK` |
| `docs/carney_handover/one_pager.md` | publishes the signing-key fingerprint; lists the new doc |

No `src` / `scripts` / `tests` change — documentation + handover artifacts only.

## Approach

The issue asks for the verification criteria to be **documented and
dry-run**. A reviewer with no POLARIS access runs **shell commands**, not
pytest — so the proof is a *captured transcript* of those commands, run
against a *committed sample bundle* the reviewer can re-run them against.
`tests/polaris_graph/audit_bundle/test_gpg_signer.py` already covers the
signer→`gpg --verify` surface; an automated per-file hash-chain test is the
distinct internal-integrity concern carved to follow-up #549.

## How it was produced (durably, not fabricated)

- The sample bundle was built by `build_audit_bundle(...)` over the
  known-good FK-chain shape from `test_audit_bundle_route.py` `_payload()`,
  signed with the real demo key (fingerprint `FB22…0C02`, secret present in
  `~/.gnupg-polaris`). bundle_id `audit_2b7cb9e3-44fa-4a9b-a3c9-5be72eb6a033`.
- The dry-run executed §2's literal commands on a **fresh empty GnuPG
  keyring** (a clean-machine simulation: only the public key imported, no
  POLARIS code, no Python). Result captured verbatim: member-set PASS, `gpg`
  `Good signature` exit 0, all 6 manifest-listed files re-hash `OK`,
  `RESULT: OK`.
- The throwaway harnesses that built the bundle and ran the dry-run were
  deleted after use (per the APPROVE'd brief) — not committed.

## Codex iter-1 brief findings — both addressed

- **P1 (member-set check):** §2 Step 3 now requires the archive's member
  set to equal *exactly* `manifest.yaml` + `manifest.yaml.asc` + every
  `manifest.files[].path` — a repacked bundle with an added unmanifested
  member is rejected. Captured in the dry-run.
- **P2 (trusted fingerprint publication point):** `one_pager.md` now prints
  the signing-key fingerprint, so §2 Step 1's out-of-band cross-check has a
  real target.

## Honesty / correctness checks

- The §2 procedure is **pure shell** (`gpg`, `tar`, `grep`, `awk`, `paste`,
  `sha256sum`, `sort`, `comm`) — the first dry-run attempt used `python3` +
  PyYAML and failed `ModuleNotFoundError: No module named 'yaml'` on the
  clean interpreter; that finding drove the rewrite so the documented
  procedure genuinely needs no Python.
- The doc explains GnuPG's `WARNING: This key is not certified` message as
  normal — trust comes from the fingerprint cross-check, not GnuPG's
  trustdb — so a reviewer is not misled into rejecting a valid signature.
- The committed pubkey and sample bundle are a matched pair; §1 documents
  that a key rotation requires regenerating both plus the transcript.
- `outputs/polaris_demo_pubkey.asc` is gitignored — hence the committed
  handover copy at `docs/carney_handover/polaris_demo_pubkey.asc`.

## Verification

The dry-run transcript IS the verification: §2 run end-to-end on a fresh
keyring → `RESULT: OK`. Reproducible by re-running §2 against the committed
`sample_signed_bundle.tar.gz`.

## Verdict

Ready for Codex diff review. The clean-machine criteria are documented and
proven by a captured, reproducible dry-run.
