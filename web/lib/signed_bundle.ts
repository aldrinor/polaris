// I-cd-012 (GH#608) — frontend mirror of
// src/polaris_graph/audit_bundle/bundle_schema.py:BundleManifest (FROZEN v1.0).
//
// FROZEN v1.0: Field additions, removals, type changes, or new ContentType
// enum members require the full bump cascade documented in the Python module.
//
// Active consumers:
//   - Future Inspector route (I-A-03, #609)
//   - Offline fallback Inspector that renders a signed bundle in-browser
//     with no GPU/no backend (I-B-09, #631)
//
// Active producers (mirror this contract):
//   - src/polaris_graph/audit_bundle/manifest_builder.py
//   - src/polaris_graph/audit_bundle/bundle_builder.py
//   - src/polaris_graph/api/audit_bundle_route.py
//   - src/polaris_v6/api/bundle.py

import yaml from "js-yaml";

// ---------------------------------------------------------------------------
// Type literals — must match
// src/polaris_graph/audit_bundle/bundle_schema.py:ContentType
// ---------------------------------------------------------------------------

export type ContentType =
  | "scope_decision"
  | "evidence_pool"
  | "verified_report"
  | "source_snapshot"
  | "metadata"
  | "reasoning_trace";

export const CONTENT_TYPES: ContentType[] = [
  "scope_decision",
  "evidence_pool",
  "verified_report",
  "source_snapshot",
  "metadata",
  "reasoning_trace",
];

export const BUNDLE_VERSION = "1.0" as const;

// ---------------------------------------------------------------------------
// FileEntry — mirrors bundle_schema.py:FileEntry
// ---------------------------------------------------------------------------

export interface FileEntry {
  path: string; // relative POSIX path inside the extracted bundle
  sha256: string; // lowercase hex SHA256
  size_bytes: number;
  content_type: ContentType;
}

// ---------------------------------------------------------------------------
// BundleManifest — mirrors bundle_schema.py:BundleManifest
// ---------------------------------------------------------------------------

export interface BundleManifest {
  bundle_id: string;
  bundle_version: typeof BUNDLE_VERSION;
  decision_id: string;
  pool_id: string;
  report_id: string;
  generator_model: string;
  polaris_version: string;
  files: FileEntry[];
  bundle_created_at_utc: string; // ISO-8601 UTC
}

// ---------------------------------------------------------------------------
// Reasoning trace — JSONL (one record per generator LLM call)
// ---------------------------------------------------------------------------

// Mirrors src/polaris_graph/generator/reasoning_trace.py:67
// ReasoningTraceRecord (the active producer dataclass). 15 fields.
// Codex diff iter-1 P1: previous 5-field shape diverged from real producer.
export interface ReasoningTraceRecord {
  call_id: string;
  section: string;
  call_type: string;
  model: string;
  status: string; // see reasoning_trace.py STATUSES
  content_source: string; // see reasoning_trace.py CONTENT_SOURCES
  parent_call_id: string | null;
  regen_reason: string | null;
  attempt_n: number;
  reasoning_text: string;
  content_text: string;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  timestamp: string; // ISO-8601 UTC
}

// ---------------------------------------------------------------------------
// Bundle metadata — content of metadata.json
// ---------------------------------------------------------------------------

export interface BundleMetadata {
  polaris_version: string;
  generator_model: string;
  evaluator_model: string;
  bundle_created_at_utc: string;
  schema_version: typeof BUNDLE_VERSION;
}

// ---------------------------------------------------------------------------
// Parsers
// ---------------------------------------------------------------------------

/** Parse a `manifest.yaml` text into a typed `BundleManifest`.
 *
 * Validation is structural (presence of required fields + bundle_version
 * literal); deeper conformance (path traversal, SHA256 matching, content
 * schema validity) lives in the Python `check_bundle_conformance`. */
export function parseManifest(yamlText: string): BundleManifest {
  const parsed = yaml.load(yamlText);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("manifest.yaml does not parse to a YAML mapping");
  }
  const m = parsed as Partial<BundleManifest>;
  if (m.bundle_version !== BUNDLE_VERSION) {
    throw new Error(
      `bundle_version ${m.bundle_version} != frozen ${BUNDLE_VERSION}`,
    );
  }
  for (const required of [
    "bundle_id",
    "decision_id",
    "pool_id",
    "report_id",
    "generator_model",
    "polaris_version",
    "files",
    "bundle_created_at_utc",
  ] as const) {
    if (m[required] === undefined || m[required] === null) {
      throw new Error(`manifest.yaml missing required field: ${required}`);
    }
  }
  if (!Array.isArray(m.files)) {
    throw new Error("manifest.yaml `files` must be an array");
  }
  return m as BundleManifest;
}

/** Parse a `reasoning_trace.jsonl` text body into a list of records.
 *
 * One JSON object per non-empty line; blank lines are skipped. Malformed
 * lines throw to surface bundle corruption at the source. */
export function parseReasoningTraceJsonl(text: string): ReasoningTraceRecord[] {
  const out: ReasoningTraceRecord[] = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.trim() === "") continue;
    let record: unknown;
    try {
      record = JSON.parse(line);
    } catch (err) {
      throw new Error(
        `reasoning_trace.jsonl line ${i + 1} is not valid JSON: ${(err as Error).message}`,
      );
    }
    if (
      typeof record !== "object" ||
      record === null ||
      Array.isArray(record)
    ) {
      throw new Error(
        `reasoning_trace.jsonl line ${i + 1} is not a JSON object`,
      );
    }
    out.push(record as ReasoningTraceRecord);
  }
  return out;
}

/** Helper: filter `BundleManifest.files` by ContentType. */
export function filesByContentType(
  manifest: BundleManifest,
  contentType: ContentType,
): FileEntry[] {
  return manifest.files.filter((f) => f.content_type === contentType);
}
