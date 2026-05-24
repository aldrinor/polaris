/**
 * I-cd-021 (#631) — Browser-side bundle loader.
 *
 * Parses a v1.0 BundleManifest tar.gz uploaded by a disconnected
 * reviewer (no backend, no GPU). Same `LoadedBundle` shape as the
 * server-side `inspector_bundle_loader.ts` so all Inspector components
 * accept either source.
 *
 * Conformance (browser-safe subset of the 12-layer Python check):
 *   - tar.gz size ≤ 50MB
 *   - inflate via pako
 *   - extract files with tar-stream (browser build)
 *   - manifest.yaml parses cleanly (existing parseManifest)
 *   - bundle_version == "1.0"
 *   - all 6 required ContentTypes present in manifest.files
 *   - each declared file is present in the tar
 *   - SHA-256 of each file matches manifest hash (browser crypto.subtle)
 *   - byte size matches manifest size
 *   - signaturePresent: derived from manifest.yaml.asc existence + non-empty
 *
 * GPG cryptographic verify is out of scope (requires CLI / pgp.js + key
 * trust UX, both browser-impractical for Carney handover).
 */

import pako from "pako";
import { extract as tarExtract } from "tar-stream";

import {
  type BundleManifest,
  type BundleMetadata,
  type ReasoningTraceRecord,
  parseManifest,
  parseReasoningTraceJsonl,
} from "@/lib/signed_bundle";

import type {
  LoadedBundle,
  VerifiedReportShape,
} from "@/lib/inspector_bundle_loader";

const MAX_TAR_GZ_BYTES = 50 * 1024 * 1024;
// Codex iter-1 P1.1 fix: cap DECOMPRESSED tar bytes to prevent gzip-bomb OOM.
// A 50MB gzip can inflate to 50GB+ of zeros. 200MB is generous for legitimate
// bundles (the largest v1.0 fixture is ~80KB; real runs may approach a few MB).
const MAX_DECOMPRESSED_BYTES = 200 * 1024 * 1024;

export class BundleClientLoaderError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
    this.name = "BundleClientLoaderError";
  }
}

interface ExtractedFile {
  name: string;
  bytes: Uint8Array;
}

async function _extractTarBytes(
  tarBytes: Uint8Array,
): Promise<ExtractedFile[]> {
  return new Promise((resolve, reject) => {
    const files: ExtractedFile[] = [];
    const extractor = tarExtract();
    extractor.on(
      "entry",
      (
        header: { name: string; type?: string },
        stream: NodeJS.ReadableStream,
        next: () => void,
      ) => {
        const chunks: Uint8Array[] = [];
        stream.on("data", (c: Uint8Array) => chunks.push(c));
        stream.on("end", () => {
          if (header.type === "file") {
            // Concat chunks into one Uint8Array.
            const total = chunks.reduce((s, c) => s + c.length, 0);
            const merged = new Uint8Array(total);
            let off = 0;
            for (const c of chunks) {
              merged.set(c, off);
              off += c.length;
            }
            files.push({
              name: header.name.replace(/^\.\//, ""),
              bytes: merged,
            });
          }
          next();
        });
        stream.resume();
      },
    );
    extractor.on("finish", () => resolve(files));
    extractor.on("error", reject);
    extractor.end(tarBytes);
  });
}

class _GzipBombAbort extends Error {
  readonly cap: number;
  constructor(cap: number) {
    super(`Decompressed bytes exceeded ${cap} cap (gzip-bomb guard).`);
    this.cap = cap;
  }
}

function _streamingUngzip(
  compressed: Uint8Array,
): Uint8Array | BundleClientLoaderError {
  // pako.Inflate emits chunks via an onData callback; we accumulate up to
  // MAX_DECOMPRESSED_BYTES then ABORT (Codex iter-3 P1 fix: previously
  // onData just stopped collecting but inflator.push continued processing
  // the rest of the stream — bomb could still hang the thread).
  // Throwing from onData propagates out of inflator.push so we stop pako
  // from continuing to decompress. The throw is caught locally.
  const inflator = new pako.Inflate({ raw: false });
  let total = 0;
  const chunks: Uint8Array[] = [];

  inflator.onData = (chunk: Uint8Array): void => {
    total += chunk.length;
    if (total > MAX_DECOMPRESSED_BYTES) {
      throw new _GzipBombAbort(MAX_DECOMPRESSED_BYTES);
    }
    chunks.push(chunk);
  };
  inflator.onEnd = (_status: number): void => {
    /* status handled via err/msg fields below */
  };

  try {
    inflator.push(compressed, true);
  } catch (exc) {
    if (exc instanceof _GzipBombAbort) {
      return new BundleClientLoaderError("decompressed_too_large", exc.message);
    }
    return new BundleClientLoaderError(
      "ungzip_failed",
      `Failed to gunzip bundle: ${(exc as Error).message}`,
    );
  }

  if (inflator.err) {
    return new BundleClientLoaderError(
      "ungzip_failed",
      `Failed to gunzip bundle: ${inflator.msg || "pako error " + inflator.err}`,
    );
  }

  // Concatenate chunks into one Uint8Array.
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

async function _sha256Hex(bytes: Uint8Array): Promise<string> {
  // Slice into a fresh ArrayBuffer (not SharedArrayBuffer) for browser-safe
  // BufferSource typing on crypto.subtle.digest.
  const buf = await crypto.subtle.digest(
    "SHA-256",
    bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ) as ArrayBuffer,
  );
  const arr = Array.from(new Uint8Array(buf));
  return arr.map((b) => b.toString(16).padStart(2, "0")).join("");
}

function _findFile(
  files: ExtractedFile[],
  pathInManifest: string,
): ExtractedFile | undefined {
  // tar entries may be prefixed with bundle-dir name (e.g. "v1_canonical/").
  // Match suffix to keep loader robust against `tar -czf bundle.tar.gz <dir>`
  // vs `tar -czf bundle.tar.gz -C <dir> .`.
  return files.find(
    (f) => f.name === pathInManifest || f.name.endsWith("/" + pathInManifest),
  );
}

function _decode(bytes: Uint8Array): string {
  return new TextDecoder("utf-8").decode(bytes);
}

// Codex iter-1 P1.2 fix: v1.0 conformance per
// src/polaris_graph/audit_bundle/conformance.py:_REQUIRED_CONTENT_TYPES
// requires ALL SIX content types (including source_snapshot).
const REQUIRED_CONTENT_TYPES = [
  "scope_decision",
  "evidence_pool",
  "verified_report",
  "metadata",
  "source_snapshot",
  "reasoning_trace",
] as const;

export async function loadBundleFromTarGz(file: File): Promise<LoadedBundle> {
  if (file.size > MAX_TAR_GZ_BYTES) {
    throw new BundleClientLoaderError(
      "tar_gz_too_large",
      `Bundle file is ${file.size} bytes, exceeds ${MAX_TAR_GZ_BYTES} byte limit.`,
    );
  }
  const arrayBuffer = await file.arrayBuffer();
  // Codex iter-2 P1.1 fix: streaming inflate via pako.Inflate, aborting as
  // soon as cumulative decompressed bytes exceed MAX_DECOMPRESSED_BYTES.
  // The previous one-shot pako.ungzip() materialized the full bomb before
  // the size guard ran.
  const tarBytes = _streamingUngzip(new Uint8Array(arrayBuffer));
  if (tarBytes instanceof BundleClientLoaderError) {
    throw tarBytes;
  }
  const files = await _extractTarBytes(tarBytes);
  const manifestFile = _findFile(files, "manifest.yaml");
  if (!manifestFile) {
    throw new BundleClientLoaderError(
      "manifest_missing",
      "Bundle is missing manifest.yaml.",
    );
  }
  let manifest: BundleManifest;
  try {
    manifest = parseManifest(_decode(manifestFile.bytes));
  } catch (exc) {
    throw new BundleClientLoaderError(
      "manifest_parse_failed",
      `manifest.yaml parse failed: ${(exc as Error).message}`,
    );
  }
  if (manifest.bundle_version !== "1.0") {
    throw new BundleClientLoaderError(
      "version_mismatch",
      `Bundle version ${JSON.stringify(manifest.bundle_version)} != frozen v1.0.`,
    );
  }
  for (const required of REQUIRED_CONTENT_TYPES) {
    if (!manifest.files.some((f) => f.content_type === required)) {
      throw new BundleClientLoaderError(
        "required_content_type_missing",
        `Manifest missing required content_type ${JSON.stringify(required)}.`,
      );
    }
  }

  // SHA-256 + size verify every manifest entry.
  for (const entry of manifest.files) {
    const candidate = _findFile(files, entry.path);
    if (!candidate) {
      throw new BundleClientLoaderError(
        "manifest_file_missing",
        `Manifest declares ${JSON.stringify(entry.path)} but bundle does not contain it.`,
      );
    }
    if (candidate.bytes.length !== entry.size_bytes) {
      throw new BundleClientLoaderError(
        "size_mismatch",
        `${JSON.stringify(entry.path)}: manifest size=${entry.size_bytes}, actual=${candidate.bytes.length}.`,
      );
    }
    const actualSha = await _sha256Hex(candidate.bytes);
    if (actualSha !== entry.sha256) {
      throw new BundleClientLoaderError(
        "sha256_mismatch",
        `${JSON.stringify(entry.path)}: manifest sha256=${JSON.stringify(entry.sha256)}, actual=${JSON.stringify(actualSha)}.`,
      );
    }
  }

  // metadata.json by explicit path (v1.0 spec).
  const metadataEntry = manifest.files.find(
    (f) => f.content_type === "metadata" && f.path === "metadata.json",
  );
  if (!metadataEntry) {
    throw new BundleClientLoaderError(
      "metadata_entry_missing",
      "Manifest must have a metadata entry with path=metadata.json.",
    );
  }
  const metadataFile = _findFile(files, "metadata.json")!;
  const metadata = JSON.parse(_decode(metadataFile.bytes)) as BundleMetadata;

  const scopeDecisionFile = _findFile(files, "scope_decision.json")!;
  const scopeDecision = JSON.parse(_decode(scopeDecisionFile.bytes));

  const evidencePoolFile = _findFile(files, "evidence_pool.json")!;
  const evidencePool = JSON.parse(_decode(evidencePoolFile.bytes));

  const verifiedReportFile = _findFile(files, "verified_report.json")!;
  const verifiedReport = JSON.parse(
    _decode(verifiedReportFile.bytes),
  ) as VerifiedReportShape;

  const reasoningEntry = manifest.files.find(
    (f) => f.content_type === "reasoning_trace",
  );
  const reasoningTrace: ReasoningTraceRecord[] = reasoningEntry
    ? parseReasoningTraceJsonl(
        _decode(_findFile(files, reasoningEntry.path)!.bytes),
      )
    : [];

  const sources: Record<string, string> = {};
  for (const entry of manifest.files) {
    if (entry.content_type !== "source_snapshot") continue;
    const sourceFile = _findFile(files, entry.path);
    if (sourceFile) {
      sources[entry.path] = _decode(sourceFile.bytes);
    }
  }

  // Tri-valued signature state per I-ux-001a. CLIENT loader can NEVER return
  // gpg_verified — the browser has no gpg(1) + no trust root. At best the
  // `.asc` is present in the uploaded tarball; full crypto verification is
  // the offline CLI path (signed bundle → `gpg --verify` against the
  // shipped pubkey at docs/carney_handover/polaris_demo_pubkey.asc).
  const signatureFile = _findFile(files, "manifest.yaml.asc");
  const signatureState: "missing" | "present_unverified" | "gpg_verified" =
    signatureFile && signatureFile.bytes.length > 0
      ? "present_unverified"
      : "missing";

  // runId for offline mode: derive from filename (BundleMetadata doesn't
  // carry run_id; it's a session-level field outside the v1.0 freeze).
  const runId =
    file.name.replace(/\.tar\.gz$/, "").replace(/\.tgz$/, "") ||
    "offline-bundle";

  return {
    runId,
    manifest,
    scopeDecision,
    evidencePool,
    verifiedReport,
    metadata,
    reasoningTrace,
    sources,
    signatureState,
  };
}
