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
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// I-ux-001a Codex iter-1 P1: Next.js server CWD is `web/`, NOT the repo root.
// Anchor the trust-root + pin paths to the discovered repo root so the verifier
// reliably finds them. Order of resolution:
//   1. $POLARIS_REPO_ROOT (explicit override; CI/Docker can set this)
//   2. walk up from this module's directory until a sentinel file appears
//   3. process.cwd() as last resort (works if launched from repo root)
function _findRepoRoot(): string {
  const fromEnv = process.env.POLARIS_REPO_ROOT;
  if (fromEnv && existsSync(path.join(fromEnv, "state/polaris_gpg_keyid.txt"))) {
    return fromEnv;
  }
  // __dirname is unavailable in ESM but Next.js compiles to CJS at runtime;
  // fall back to walking up from process.cwd() which under Next is `web/`.
  let cur = process.cwd();
  for (let i = 0; i < 6; i++) {
    if (existsSync(path.join(cur, "state/polaris_gpg_keyid.txt"))) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  return process.cwd();
}
const REPO_ROOT = _findRepoRoot();
const TRUST_ROOT_PUBKEY = path.join(REPO_ROOT, "docs/carney_handover/polaris_demo_pubkey.asc");
const PINNED_FP_FILE = path.join(REPO_ROOT, "state/polaris_gpg_keyid.txt");

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

  // 3. Verify with `gpgv` against a freshly-dearmored binary keyring built
  //    ONLY from the shipped trust root (Codex iter-1 P1 on the diff).
  //    gpgv is the dedicated verify-only tool: no gpg-agent spawn, no
  //    keyboxd, no host gpg.conf. The keyring is built fresh each request
  //    so the only key gpgv can trust is the one we pin.
  let tmpDir: string | null = null;
  try {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "polaris-gpgv-"));
    const keyringPath = path.join(tmpDir, "trust.gpg");
    // Dearmor the .asc pubkey into a binary keyring.
    const armored = await fs.readFile(trustRoot);
    const de = await new Promise<{ ok: boolean; bin?: Buffer; err: string }>((resolve) => {
      const cp = require("node:child_process").spawn("gpg", ["--no-options", "--batch", "--dearmor"]);
      const chunks: Buffer[] = [];
      const errChunks: Buffer[] = [];
      cp.stdout.on("data", (d: Buffer) => chunks.push(d));
      cp.stderr.on("data", (d: Buffer) => errChunks.push(d));
      cp.on("close", (code: number) => resolve({
        ok: code === 0,
        bin: code === 0 ? Buffer.concat(chunks) : undefined,
        err: Buffer.concat(errChunks).toString("utf-8"),
      }));
      cp.stdin.write(armored);
      cp.stdin.end();
    });
    if (!de.ok || !de.bin) return { state: "present_unverified" };
    await fs.writeFile(keyringPath, de.bin);

    // MSYS gpgv mangles absolute Windows paths in --keyring (prepends ~/.gnupg/
    // to anything with a colon). Workaround: cwd=tmpDir + relative keyring.
    const { stdout, stderr } = await execFileAsync("gpgv", [
      "--keyring", "./trust.gpg", "--status-fd", "1",
      path.resolve(ascPath), path.resolve(manifestPath),
    ], { cwd: tmpDir });
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
