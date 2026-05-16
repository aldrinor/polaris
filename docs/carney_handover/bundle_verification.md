# Verifying a POLARIS signed audit bundle

Every POLARIS audit bundle (`audit_<id>.tar.gz`, served by
`GET /runs/{run_id}/bundle.tar.gz`) is GPG-signed. A reviewer with **no
POLARIS access** — no source code, no cluster login, no Python environment —
can confirm a bundle is authentic and unmodified using only standard
command-line tools.

This document has two parts:

- **§1** — the operator's signing-key readiness checklist (run before the
  demo).
- **§2** — the reviewer's clean-machine verification procedure.

A worked, captured run of §2 against the committed sample bundle
(`sample_signed_bundle.tar.gz`) is in `bundle_verification_dryrun.txt`.

---

## §1 — Signing-key readiness checklist (operator)

The audit-bundle signing key is the **POLARIS Carney Demo** GPG key. Confirm
all of the following before the demo:

- [ ] **Key generated.** `scripts/bootstrap_gpg_demo_key.sh` has been run.
      It creates an `ed25519` primary key (sign capability; GnuPG keeps the
      `certify` capability on any primary key; **no encryption subkey**).
- [ ] **Fingerprint recorded.** `state/polaris_gpg_keyid.txt` holds the
      40-hex-character fingerprint.
- [ ] **Public key exported** to `outputs/polaris_demo_pubkey.asc`, and its
      handover copy committed at `docs/carney_handover/polaris_demo_pubkey.asc`
      (the `outputs/` path is gitignored — the committed copy is what travels
      with the handover package).
- [ ] **Fingerprint published** in `docs/carney_handover/one_pager.md` so a
      reviewer has a trusted, out-of-band value to cross-check against.
- [ ] **`POLARIS_GPG_KEY_ID`** is set in `.env` to the fingerprint. The v6
      API's `get_sign_fn` then resolves a real `GPGSigner`; if it is unset,
      `GET /runs/{id}/bundle.tar.gz` returns **503** — POLARIS structurally
      refuses to ship an unsigned bundle (CLAUDE.md LAW II).
- [ ] **`gpg-agent` reachable.** GnuPG 2.x routes all secret-key operations
      through `gpg-agent`; confirm `gpg --batch --detach-sign` succeeds for
      the key under the deploy's `GNUPGHOME` (the v6 container sets
      `GNUPGHOME=/app/gpg`).
- [ ] **Expiry checked.** The demo key expires **one year after generation**.
      Confirm the expiry date is comfortably past the demo date; if it is
      not, re-run `bootstrap_gpg_demo_key.sh` and re-export **both** public
      key copies (and regenerate `sample_signed_bundle.tar.gz` +
      `bundle_verification_dryrun.txt`).
- [ ] **Sovereign deploy.** On the Vexxhost VM, `infra/vexxhost/provision.sh`
      imports the operator-staged key pair into `/var/lib/polaris/gpg` and
      `shred`s the secret-key file from `/root` afterward.

The current demo key (committed in `polaris_demo_pubkey.asc`):

```
fingerprint : FB22 1FA8 ED18 5F8E 3F76  F7E6 F6F3 1CED FF49 0C02
uid         : POLARIS Carney Demo (Carney demo bundle signing) <signing@polaris.local>
algorithm   : ed25519, [SC]
```

---

## §2 — Clean-machine verification procedure (reviewer)

You need only: **`gpg`**, **`tar`**, and the standard text tools (`grep`,
`awk`, `paste`, `sha256sum`, `sort`, `comm`). No POLARIS code, no Python.
On macOS, substitute `shasum -a 256` for `sha256sum`.

You should have received two files on a channel **separate** from the bundle
itself: `polaris_demo_pubkey.asc` (the public key) and the audit bundle
`audit_<id>.tar.gz`.

### Step 1 — import the public key and confirm the fingerprint

```
gpg --import polaris_demo_pubkey.asc
gpg --list-keys --fingerprint
```

Confirm the printed fingerprint **exactly matches** the one published in the
handover one-pager (`one_pager.md`). This out-of-band cross-check — not
GnuPG's trust database — is what establishes that the key is POLARIS's. If
the fingerprint does not match, **stop**: do not trust the bundle.

All remaining steps run from **one working directory** — the directory that
holds the `.tar.gz` you received. Do **not** `cd` into the extracted folder;
every command below references the extracted files explicitly via `$DIR`.
Set two shell variables once, then steps 2–5 are copy-paste reproducible:

```
BUNDLE=audit_<id>.tar.gz                       # the file you received
DIR=$(tar -tzf "$BUNDLE" | head -1 | cut -d/ -f1)   # the archive's top folder
```

### Step 2 — list and extract the archive

```
tar -tzf "$BUNDLE"
tar -xzf "$BUNDLE"
```

### Step 3 — archive member-set check

A valid bundle contains **exactly** `manifest.yaml`, `manifest.yaml.asc`,
and every file listed in `manifest.yaml`'s `files[]` array — nothing more,
nothing less. An attacker who adds an unmanifested file must not pass.

```
tar -tzf "$BUNDLE" | sed 's#^[^/]*/##' | sort > got.txt
{ echo manifest.yaml; echo manifest.yaml.asc; \
  grep '^  path:' "$DIR/manifest.yaml" | awk '{print $2}'; } | sort > expected.txt
diff got.txt expected.txt && echo "member-set OK"
```

Any line of `diff` output means an extra or missing member — **reject the
bundle**.

### Step 4 — verify the GPG signature over `manifest.yaml`

```
gpg --verify "$DIR/manifest.yaml.asc" "$DIR/manifest.yaml"
```

Expect `gpg: Good signature from "POLARIS Carney Demo ..."`. GnuPG will also
print `WARNING: This key is not certified with a trusted signature` — that
is **normal and expected**: it only means you have not locally *certified*
the key in your web of trust. The cryptographic verification has still
succeeded; trust in the key comes from the fingerprint cross-check in
Step 1, not from GnuPG's trust database. A non-zero exit code, or anything
other than `Good signature`, means **reject the bundle**.

### Step 5 — re-hash every manifest-listed file

The signature authenticates `manifest.yaml`; `manifest.yaml` records a
SHA-256 for every other file. Re-hash each and compare:

```
paste <(grep '^  path:'   "$DIR/manifest.yaml" | awk '{print $2}') \
      <(grep '^  sha256:' "$DIR/manifest.yaml" | awk '{print $2}') \
| while read -r path recorded; do
      actual=$(sha256sum "$DIR/$path" | awk '{print $1}')
      [ "$actual" = "$recorded" ] && echo "OK  $path" || echo "BAD $path"
  done
```

Every line must read `OK`. Any `BAD` means a file was altered after signing
— **reject the bundle**.

### Pass criteria

The bundle is **authentic and unmodified** if and only if **all** of:

1. the Step 1 fingerprint matches the one published in `one_pager.md`;
2. the Step 3 member set matches exactly;
3. Step 4 prints `Good signature` and `gpg` exits 0;
4. every Step 5 file reads `OK`.

Any failure → reject the bundle and do not trust the report it contains.

### Inspecting the content

Once verified, the bundle's own `REVIEWER_README.md` walks through reading
`verified_report.json` and tracing any claim's `[#ev:<source_id>:<start>-<end>]`
provenance token back to the exact character span of its snapshotted source
in `sources/<source_id>.txt`.

---

## Distribution

The public key (`polaris_demo_pubkey.asc`) ships **with the handover
package**, and its fingerprint is **also** printed in `one_pager.md`. A
reviewer therefore has the key on a channel independent of any single
bundle, and an independent value to cross-check the fingerprint against — so
an attacker cannot substitute both the key and a forged bundle. Audit
bundles themselves are produced per-run and delivered separately (downloaded
from the running system, or attached to a report).
