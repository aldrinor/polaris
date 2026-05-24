// I-ux-001a (GH#874) — server-side GPG verification of audit-bundle signatures.
//
// LAW-II "no fake working" gate. Previously the loader marked
// signaturePresent=true on any non-empty manifest.yaml.asc, so a placeholder
// `.asc` would render as "Signed bundle." This module replaces that with a
// real `gpg --verify` against the SHIPPED trust-root pubkey
// (docs/carney_handover/polaris_demo_pubkey.asc) in an ISOLATED temporary
// GNUPGHOME (so the host's default keyring cannot satisfy verification), and
// asserts the signing-key fingerprint matches the pinned canonical key
// (state/polaris_gpg_keyid.txt).
//
// Returns `gpg_verified` only on full pass; `present_unverified` if the file
// exists but verification fails for any reason; `missing` otherwise.

import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// repo-root-relative paths to the trust-root + pinned fingerprint, resolved
// from CWD at request time (Next.js server CWD is the repo root).
const TRUST_ROOT_PUBKEY = "docs/carney_handover/polaris_demo_pubkey.asc";
const PINNED_FP_FILE = "state/polaris_gpg_keyid.txt";

export interface SignatureVerifyResult {
  state: "missing" | "present_unverified" | "gpg_verified";
  /** Hex fingerprint of the signing key when state=gpg_verified. */
  fingerprint?: string;
}

async function _readPinnedFingerprint(): Promise<string | null> {
  try {
    const raw = await fs.readFile(PINNED_FP_FILE, "utf-8");
    const fp = raw.trim().toUpperCase().replace(/\s+/g, "");
    return /^[0-9A-F]{40}$/.test(fp) ? fp : null;
  } catch {
    return null;
  }
}

export async function verifyBundleSignature(
  bundleDir: string,
): Promise<SignatureVerifyResult> {
  const ascPath = path.join(bundleDir, "manifest.yaml.asc");
  const manifestPath = path.join(bundleDir, "manifest.yaml");

  // 1. presence + non-empty
  try {
    const stat = await fs.stat(ascPath);
    if (!stat.isFile() || stat.size === 0) return { state: "missing" };
  } catch {
    return { state: "missing" };
  }

  // 2. resolve the pinned canonical fingerprint + the shipped trust root.
  //    Without either we can never claim gpg_verified — degrade honestly.
  const pinnedFp = await _readPinnedFingerprint();
  if (!pinnedFp) return { state: "present_unverified" };

  let trustRoot: string;
  try {
    await fs.access(TRUST_ROOT_PUBKEY);
    trustRoot = TRUST_ROOT_PUBKEY;
  } catch {
    return { state: "present_unverified" };
  }

  // 3. Verify against the trust root in an ISOLATED KEYRING (Codex brief
  //    iter-2 P2). We use --no-default-keyring + --keyring (not --homedir):
  //    a fresh GNUPGHOME tries to spawn gpg-agent, which is brittle for a
  //    verify-only path. --keyring sidesteps the agent entirely.
  let tmpDir: string | null = null;
  try {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "polaris-gpg-"));
    const keyring = path.join(tmpDir, "trust.kbx");
    await execFileAsync("gpg", [
      "--no-default-keyring", "--keyring", keyring,
      "--batch", "--quiet", "--import", trustRoot,
    ]);
    // status-fd=1 routes machine-readable VALIDSIG to stdout; we check both.
    const { stdout, stderr } = await execFileAsync("gpg", [
      "--no-default-keyring", "--keyring", keyring,
      "--batch", "--status-fd", "1",
      "--verify", ascPath, manifestPath,
    ]);
    const m = (stdout + stderr).match(/VALIDSIG\s+([0-9A-F]{40})\b/i);
    const fp = m ? m[1].toUpperCase() : null;
    if (!fp) return { state: "present_unverified" };
    if (fp !== pinnedFp) return { state: "present_unverified" };
    return { state: "gpg_verified", fingerprint: fp };
  } catch {
    return { state: "present_unverified" };
  } finally {
    if (tmpDir) await fs.rm(tmpDir, { recursive: true, force: true }).catch(() => {});
  }
}
