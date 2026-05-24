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

// I-ux-001a: bake the trust root + pinned fingerprint as constants instead of
// reading from disk. Two wins: (1) the prior CWD walk-up from Next.js cwd=web/
// is gone (Codex iter-1 P1 root cause), (2) the production Docker (build
// context=./web) no longer needs to ship docs/ or state/ files outside its
// context. Both values are PUBLIC by design per docs/carney_secret_inventory.md
// #1 ("Public key may stay published"). Rotation = update both constants and
// the corresponding source files + redeploy.
//
// IMPORTANT (Codex iter-3 P1): TRUST_ROOT_ARMORED is BASE64-encoded so we never
// transcribe multi-line ASCII-armored text by hand again. The earlier hand-
// copied version had a 4-byte transcription error → wrong fingerprint → prod
// would always degrade to present_unverified. The bytes below are
// `base64(file_contents(docs/carney_handover/polaris_demo_pubkey.asc))`.
// `tests/scripts/test_trust_root_consts.py` asserts both constants exactly
// match the shipped source files + that the dearmored bytes produce the
// pinned fingerprint, so this regression cannot recur silently.
const PINNED_FP = "FB221FA8ED185F8E3F76F7E6F6F31CEDFF490C02";
const TRUST_ROOT_BASE64 =
  "LS0tLS1CRUdJTiBQR1AgUFVCTElDIEtFWSBCTE9DSy0tLS0tDQoNCm1ETUVhZ1Zrd2hZSkt3WUJCQUhhUnc4QkFRZEFPMlFBNEpyT1YreThnc21NRjN2SFgzY0svQVhYVTRLbTZpSW8NClpRT2dWM2EwU0ZCUFRFRlNTVk1nUTJGeWJtVjVJRVJsYlc4Z0tFTmhjbTVsZVNCa1pXMXZJR0oxYm1Sc1pTQnoNCmFXZHVhVzVuS1NBOGMybG5ibWx1WjBCd2IyeGhjbWx6TG14dlkyRnNQb2laQkJNV0NnQkJGaUVFK3lJZnFPMFkNClg0NC9kdmZtOXZNYzdmOUpEQUlGQW1vRlpNSUNHd01GQ1FIaE00QUZDd2tJQndJQ0lnSUdGUW9KQ0FzQ0JCWUMNCkF3RUNIZ2NDRjRBQUNna1E5dk1jN2Y5SkRBS0dyd0VBbnF3Rm5HeFdkTW4rUzJycHptbkdRTU10KzFrZGFMM0cNCmhSRVVXM1M3ZUtnQkFPZHpqL2s4bVBvV1VxRXFCa0MvSzhvbHZBcWxLR0RJeGNSSW5SNlhHVkFEDQo9bUFneA0KLS0tLS1FTkQgUEdQIFBVQkxJQyBLRVkgQkxPQ0stLS0tLQ0K";

export interface SignatureVerifyResult {
  state: "missing" | "present_unverified" | "gpg_verified";
  /** Hex fingerprint of the signing key when state=gpg_verified. */
  fingerprint?: string;
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

  // 2. Verify with `gpgv` against a freshly-dearmored binary keyring built
  //    ONLY from the baked-in trust root. gpgv is the dedicated verify-only
  //    tool: no gpg-agent spawn, no keyboxd, no host gpg.conf. The keyring
  //    is built fresh each request so the only key gpgv can trust is the
  //    one we pin. Production Docker installs gnupg (apk) so gpg+gpgv are
  //    available; if not, the spawn promise rejects → present_unverified
  //    (Codex iter-2 P1: controlled downgrade, no thrown process error).
  let tmpDir: string | null = null;
  try {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "polaris-gpgv-"));
    const keyringPath = path.join(tmpDir, "trust.gpg");
    const armored = Buffer.from(TRUST_ROOT_BASE64, "base64");
    // Dearmor: write the armored pubkey to stdin, capture binary stdout.
    // Promise wrapped manually to catch spawn errors (ENOENT etc) as a
    // controlled downgrade rather than an unhandled process throw.
    const de = await new Promise<{ ok: boolean; bin?: Buffer }>((resolve) => {
      const { spawn } = require("node:child_process") as typeof import("node:child_process");
      let cp;
      try {
        cp = spawn("gpg", ["--no-options", "--batch", "--dearmor"]);
      } catch {
        return resolve({ ok: false });
      }
      const chunks: Buffer[] = [];
      cp.stdout.on("data", (d: Buffer) => chunks.push(d));
      cp.on("error", () => resolve({ ok: false })); // gpg missing → downgrade
      cp.on("close", (code: number | null) =>
        resolve({ ok: code === 0, bin: code === 0 ? Buffer.concat(chunks) : undefined }),
      );
      cp.stdin.on("error", () => resolve({ ok: false }));
      cp.stdin.write(armored);
      cp.stdin.end();
    });
    if (!de.ok || !de.bin) return { state: "present_unverified" };
    await fs.writeFile(keyringPath, de.bin);

    // MSYS gpgv mangles absolute Windows paths in --keyring (prepends ~/.gnupg/
    // to anything with a colon). Workaround: cwd=tmpDir + relative keyring.
    // execFile's promisified form rejects on spawn error → caught below.
    const { stdout, stderr } = await execFileAsync("gpgv", [
      "--keyring", "./trust.gpg", "--status-fd", "1",
      path.resolve(ascPath), path.resolve(manifestPath),
    ], { cwd: tmpDir });
    const m = (stdout + stderr).match(/VALIDSIG\s+([0-9A-F]{40})\b/i);
    const fp = m ? m[1].toUpperCase() : null;
    if (!fp) return { state: "present_unverified" };
    if (fp !== PINNED_FP) return { state: "present_unverified" };
    return { state: "gpg_verified", fingerprint: fp };
  } catch {
    return { state: "present_unverified" };
  } finally {
    if (tmpDir) await fs.rm(tmpDir, { recursive: true, force: true }).catch(() => {});
  }
}
