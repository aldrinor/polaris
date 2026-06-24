// I-cd-013a (GH#609) — server-only bundle loader.
//
// Imported by web/app/inspector/[runId]/page.tsx and
// web/app/api/inspector_bundle/[runId]/route.ts. Returns the parsed
// canonical fixture data for runId === "v1-canonical" or
// "v1-canonical-success"; returns null for any other runId (the page
// renders a BundlePendingCTA in that case).
//
// Real-bundle backend wiring lands at I-B-08 (Seq 20); offline
// fallback (in-browser bundle render) at I-B-09 (Seq 21). This module
// is the swappable seam — same function signature, different data
// path in each follow-up issue.

import { promises as fs } from "node:fs";
import path from "node:path";

import {
  type BundleManifest,
  type BundleMetadata,
  type ReasoningTraceRecord,
  parseManifest,
  parseReasoningTraceJsonl,
} from "@/lib/signed_bundle";

// I-p2-p0 (#789): the canonical fixture ships in web/public/canonical_bundles/
// (Dockerfile COPYs public → /app/public; cwd=/app at runtime), so it resolves
// in dev, the standalone harness, AND the prod container — unlike the old
// process.cwd()/../tests/fixtures path, which only existed in dev → live 500.
const FIXTURE_ROOT = path.join(process.cwd(), "public", "canonical_bundles");

export interface LoadedBundle {
  runId: string;
  manifest: BundleManifest;
  scopeDecision: unknown;
  evidencePool: unknown;
  verifiedReport: VerifiedReportShape;
  metadata: BundleMetadata;
  reasoningTrace: ReasoningTraceRecord[];
  sources: Record<string, string>;
  /** Honest tri-valued signature state per I-ux-001a (Codex iter-4 P2 on the
   * I-ux-001 plan: boolean `signaturePresent` could render "Signed bundle"
   * from any non-empty `.asc`, including the historical placeholder fixture).
   *   - "missing"             — no manifest.yaml.asc on disk
   *   - "present_unverified"  — file present, but it does NOT GPG-verify
   *                              against the shipped trust-root pubkey
   *                              (docs/carney_handover/polaris_demo_pubkey.asc),
   *                              or fingerprint doesn't match the pinned key.
   *                              Client loader always returns at most this
   *                              state (no GPG in the browser).
   *   - "gpg_verified"        — file present AND `gpg --verify` PASS against
   *                              the trust root in an isolated keyring AND
   *                              the signing-key fingerprint matches the
   *                              pinned canonical key. The ONLY state the UI
   *                              may label "Signed bundle." */
  signatureState: "missing" | "present_unverified" | "gpg_verified";
  /** Hex fingerprint of the signing key when signatureState=gpg_verified;
   * undefined otherwise. Surfaced for the receipt view. */
  signatureKeyFingerprint?: string;
}

export interface VerifiedReportShape {
  report_id: string;
  pool_id: string;
  decision_id: string;
  sections: VerifiedReportSectionShape[];
  overall_verify_pass_rate: number;
  verifier_pass_threshold: number;
  pipeline_verdict: string;
  generator_model: string;
  evaluator_model: string;
  family_segregation_passed: boolean;
  started_at_utc: string;
  finished_at_utc: string;
  latency_ms: number;
  cost_usd: number;
  /** The research question this brief answered (real-run bundles). */
  research_question?: string;
}

export interface VerifiedReportSectionShape {
  section_id: string;
  section_verify_pass_rate: number;
  verified_sentences: VerifiedSentenceShape[];
  [extra: string]: unknown;
}

export interface VerifiedSentenceShape {
  section_id: string;
  sentence_text: string;
  provenance_tokens: string[];
  verifier_pass: boolean;
  [extra: string]: unknown;
}

const KNOWN_FIXTURES: Record<string, string> = {
  "v1-canonical": "v1_canonical",
  "v1-canonical-success": "v1_canonical_success",
};

export async function loadBundle(runId: string): Promise<LoadedBundle | null> {
  // typeof guard (not `!relPath`): runId could be an Object.prototype name
  // (toString / __proto__ / constructor) → KNOWN_FIXTURES[runId] returns a
  // function/object → path.join would throw before the try → user-triggerable
  // 500. A non-string lookup → null → BundlePendingCta. (Codex iter-2 P1.)
  const relPath = KNOWN_FIXTURES[runId];
  if (typeof relPath !== "string") return null;
  const dir = path.join(FIXTURE_ROOT, relPath);

  try {
    const manifestRaw = await fs.readFile(
      path.join(dir, "manifest.yaml"),
      "utf-8",
    );
    const manifest = parseManifest(manifestRaw);

    const scopeDecision = await readJson(dir, manifest, "scope_decision");
    const evidencePool = await readJson(dir, manifest, "evidence_pool");
    const verifiedReport = (await readJson(
      dir,
      manifest,
      "verified_report",
    )) as VerifiedReportShape;

    // metadata.json is selected by EXPLICIT PATH per the v1.0 freeze;
    // multiple files may carry content_type=metadata (e.g. REVIEWER_README.md
    // also flagged metadata in the active producer).
    const metadataEntry = manifest.files.find(
      (f) => f.content_type === "metadata" && f.path === "metadata.json",
    );
    if (!metadataEntry) {
      throw new Error(
        `bundle ${runId}: manifest has no entry with path=metadata.json and content_type=metadata`,
      );
    }
    const metadata = JSON.parse(
      await fs.readFile(path.join(dir, "metadata.json"), "utf-8"),
    ) as BundleMetadata;

    const reasoningTraceEntry = manifest.files.find(
      (f) => f.content_type === "reasoning_trace",
    );
    const reasoningTrace = reasoningTraceEntry
      ? parseReasoningTraceJsonl(
          await fs.readFile(path.join(dir, reasoningTraceEntry.path), "utf-8"),
        )
      : [];

    const sources: Record<string, string> = {};
    for (const entry of manifest.files) {
      if (entry.content_type !== "source_snapshot") continue;
      sources[entry.path] = await fs.readFile(
        path.join(dir, entry.path),
        "utf-8",
      );
    }

    // Signature state (tri-valued per I-ux-001a). The boolean check this
    // replaces could call a non-empty placeholder `.asc` "signed". This now
    // requires an actual `gpg --verify` PASS against the shipped trust root
    // in an isolated keyring (so the host's default keyring cannot satisfy
    // the check) AND a fingerprint match to the pinned canonical key
    // (state/polaris_gpg_keyid.txt).
    const { verifyBundleSignature } = await import("./gpg_verify_bundle");
    const sig = await verifyBundleSignature(dir);

    return {
      runId,
      manifest,
      scopeDecision,
      evidencePool,
      verifiedReport,
      metadata,
      reasoningTrace,
      sources,
      signatureState: sig.state,
      signatureKeyFingerprint: sig.fingerprint,
    };
  } catch (err) {
    // Graceful: a missing/unreadable/malformed bundle renders the pending
    // state (BundlePendingCta), NEVER a 500. (#789 P0 — the centerpiece must
    // not crash the page.)
    console.error(`[inspector] bundle load failed for ${runId}:`, err);
    return null;
  }
}

async function readJson(
  dir: string,
  manifest: BundleManifest,
  contentType: "scope_decision" | "evidence_pool" | "verified_report",
): Promise<unknown> {
  const entry = manifest.files.find((f) => f.content_type === contentType);
  if (!entry) {
    throw new Error(
      `bundle: manifest has no entry of content_type=${contentType}`,
    );
  }
  const body = await fs.readFile(path.join(dir, entry.path), "utf-8");
  return JSON.parse(body);
}
