# Codex diff review — I-rdy-017 (#513): GPG key readiness + clean-machine bundle verification

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

You are reviewing the **diff** for issue #513 against the APPROVE'd brief
(`.codex/I-rdy-017/brief.md`, brief verdict APPROVE iter 2).

## Codex diff iter-1 findings — resolutions

**P1-1 (§2 not reproducible — cwd/archive-path flow).** Resolved: §2 was
rewritten so all of Steps 2–5 run from **one working directory** — the
directory holding the `.tar.gz`. Step 0 sets `BUNDLE=<file>` and
`DIR=$(tar -tzf "$BUNDLE" | head -1 | cut -d/ -f1)`; Steps 3–5 reference
extracted files via the `$DIR/` prefix. There is no `cd` into the extracted
folder, so every literal command runs end-to-end.

**P1-2 (dry-run not a verbatim transcript).** Resolved:
`bundle_verification_dryrun.txt` was regenerated to echo the **literal §2
commands** (the exact `tar`/`gpg`/`diff`/`paste|while` lines, with the same
`$BUNDLE`/`$DIR` variables the doc uses) and show their real output for
every step including 3 and 5 — no summarization. It is a faithful execution
of §2 against the committed sample bundle, ending `RESULT: OK`.

**P2 (extract untrusted archive before checks).** Acknowledged as advisory.
The reviewer is *verifying*, not executing, the bundle; `tar -xzf` of an
audit bundle is low-risk, and an extract-manifest-first restructure
materially complicates the copy-paste procedure. Left as-is, advisory.

## What to review

Canonical diff `.codex/I-rdy-017/codex_diff.patch`
(sha256 trailer `# canonical-diff-sha256: 29fd232ddf6357cd80f30b6dcb60d4910236a54e98261b9c2344271a6ddba956`).
5 files, +280/-1, **documentation + handover artifacts only — no `src` /
`scripts` / `tests` change**:

- `docs/carney_handover/bundle_verification.md` (NEW, 172 lines) — §1
  operator signing-key readiness checklist; §2 reviewer clean-machine
  verification procedure.
- `docs/carney_handover/polaris_demo_pubkey.asc` (NEW) — committed handover
  copy of the demo signing public key (the `outputs/` copy is gitignored).
- `docs/carney_handover/sample_signed_bundle.tar.gz` (NEW, binary, 3215 B) —
  a real demo-key-signed `audit_*.tar.gz` for a reproducible dry-run.
- `docs/carney_handover/bundle_verification_dryrun.txt` (NEW, 85 lines) —
  the captured transcript of §2 run against the sample bundle.
- `docs/carney_handover/one_pager.md` (+14/-1) — publishes the signing-key
  fingerprint; lists `bundle_verification.md` as the 4th package document.

## Brief acceptance criteria (verbatim)

1. `bundle_verification.md` — §1 operator key-readiness checklist + §2
   reviewer clean-machine verification procedure (literal `gpg`/`tar`/
   `sha256sum` commands, no POLARIS code), incl. the archive member-set
   check and the public-key distribution mechanism.
2. `polaris_demo_pubkey.asc` — committed handover copy of the demo public key.
3. `sample_signed_bundle.tar.gz` — a real demo-key-signed bundle.
4. `bundle_verification_dryrun.txt` — captured §2 transcript (incl. the
   member-set check), ending `RESULT: OK`.
5. `one_pager.md` — publishes the fingerprint; lists `bundle_verification.md`.
6. §2 commands and the transcript agree; the fingerprint in §2 / the
   transcript matches the one in `one_pager.md`; reproducible by re-running
   §2 against the sample bundle.

## Verification done

- The dry-run is real: §2's literal commands were executed on a **fresh
  empty GnuPG keyring** (clean-machine simulation — only the public key
  imported, no POLARIS code, no Python). Transcript captured verbatim →
  member-set PASS, `gpg` `Good signature` exit 0, all 6 manifest-listed
  files re-hash `OK`, `RESULT: OK`.
- The §2 procedure is **pure shell** (`gpg`/`tar`/`grep`/`awk`/`paste`/
  `sha256sum`/`sort`/`comm`) — a first attempt used `python3`+PyYAML and
  failed `ModuleNotFoundError` on the clean interpreter; the procedure was
  rewritten so it genuinely needs no Python.
- Fingerprint consistency: `FB22 1FA8 ED18 5F8E 3F76 F7E6 F6F3 1CED FF49
  0C02` appears identically in `bundle_verification.md` §1, the dry-run
  transcript (`gpg --list-keys` + `gpg --verify`), and `one_pager.md`.
- `sample_signed_bundle.tar.gz` is signed by that key — confirmed by the
  transcript's `gpg --verify` against the committed `polaris_demo_pubkey.asc`.

## How the brief's iter-1 P1/P2 were implemented

- **P1 (member-set check):** `bundle_verification.md` §2 Step 3 requires the
  archive member set to equal exactly `manifest.yaml` + `manifest.yaml.asc`
  + every `manifest.files[].path`; the dry-run captures this check (PASS).
- **P2 (fingerprint publication point):** `one_pager.md` prints the
  fingerprint; §2 Step 1 cross-checks against it.

## Out of scope (do not flag as P0/P1)

- An automated per-file hash-chain test → carved to follow-up **#549**
  (internal bundle-integrity testing; `test_gpg_signer.py` already covers
  the signer→`gpg --verify` surface).
- Rotating / HSM-backing the demo key — the demo key is intentionally a
  no-passphrase demo key per `setup_gpg_for_demo.py`'s own rationale.
- GPG-signing the orchestrator *backup* archive — that is #547 (from #512).

## Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_bundle/bundle_builder.py` /
  `manifest_builder.py` — confirm the tarball layout (`manifest.yaml` +
  `manifest.yaml.asc` + `manifest.files[]`) the §2 member-set check relies
  on; `manifest.files[]` lists every content file except the two manifest
  files. Unchanged by this PR.
- `src/polaris_graph/audit_bundle/gpg_signer.py`,
  `scripts/bootstrap_gpg_demo_key.sh` — the §1 checklist matches the actual
  key-generation flow (ed25519, 1y expiry, fingerprint + pubkey export).
- `docs/carney_handover/bundle_export_sample_README.md` — the in-bundle
  `REVIEWER_README.md` covers gpg-verify + per-file hash but not the
  member-set check and assumes the key is already held; `bundle_verification.md`
  is the outside-the-bundle, clean-machine bootstrap that complements it.
- No `src`/`scripts`/`tests` file is touched — zero regression surface.

## Acceptance criteria for the resulting PR

All 6 brief criteria above. The dry-run transcript ends `RESULT: OK` and is
reproducible by re-running §2 against the committed sample bundle.

Return the YAML verdict block only.
