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

const REPO_ROOT = path.resolve(process.cwd(), "..");

export interface LoadedBundle {
  runId: string;
  manifest: BundleManifest;
  scopeDecision: unknown;
  evidencePool: unknown;
  verifiedReport: VerifiedReportShape;
  metadata: BundleMetadata;
  reasoningTrace: ReasoningTraceRecord[];
  sources: Record<string, string>;
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
  "v1-canonical": "tests/fixtures/signed_bundle/v1_canonical",
  "v1-canonical-success": "tests/fixtures/signed_bundle/v1_canonical_success",
};

export async function loadBundle(runId: string): Promise<LoadedBundle | null> {
  const relPath = KNOWN_FIXTURES[runId];
  if (!relPath) return null;
  const dir = path.join(REPO_ROOT, relPath);

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

  return {
    runId,
    manifest,
    scopeDecision,
    evidencePool,
    verifiedReport,
    metadata,
    reasoningTrace,
    sources,
  };
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
