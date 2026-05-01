/**
 * POLARIS v6 API client.
 *
 * Mirrors the FastAPI contract in src/polaris_v6/api/{runs,health,stream}.py.
 * NEXT_PUBLIC_BACKEND_URL points to the FastAPI dev server (default
 * http://127.0.0.1:8000 for local development).
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

export type TemplateId =
  | "clinical"
  | "trade"
  | "housing"
  | "defense"
  | "climate"
  | "ai_sovereignty"
  | "canada_us"
  | "workforce";

export type RunStatus =
  | "queued"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "failed"
  | "abort_scope_rejected"
  | "abort_corpus_inadequate"
  | "abort_corpus_approval_denied"
  | "abort_no_verified_sections";

export interface RunRequest {
  template: TemplateId;
  question: string;
  document_ids?: string[];
}

export interface RunStatusResponse {
  run_id: string;
  status: RunStatus;
  template: string;
  question: string;
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ApiError extends Error {
  status: number;
  body: unknown;
}

async function asJsonOrThrow<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(
      `POLARIS backend returned ${response.status}`,
    ) as ApiError;
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body as T;
}

export async function createRun(
  payload: RunRequest,
): Promise<RunStatusResponse> {
  const response = await fetch(`${BACKEND_URL}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  return asJsonOrThrow<RunStatusResponse>(response);
}

export async function getRun(runId: string): Promise<RunStatusResponse> {
  const response = await fetch(`${BACKEND_URL}/runs/${runId}`);
  return asJsonOrThrow<RunStatusResponse>(response);
}

export type DataClassification =
  | "PUBLIC_SYNTHETIC"
  | "CAN_REAL"
  | "PRIVATE"
  | "CLIENT"
  | "UNKNOWN";

export interface UploadResponse {
  document_id: string;
  filename: string;
  bytes: number;
  sha256: string;
  classification: DataClassification;
  parse_status: "queued" | "completed" | "failed";
  chunk_preview: string[];
}

export async function uploadDocument(
  file: File,
  classification: DataClassification = "UNKNOWN",
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("classification", classification);
  const response = await fetch(`${BACKEND_URL}/upload`, {
    method: "POST",
    body: form,
  });
  return asJsonOrThrow<UploadResponse>(response);
}

export type ScopeVerdict = "accepted" | "needs_clarification" | "rejected";
export type RefusalReason =
  | "clinical_treatment_recommendation"
  | "individual_legal_advice"
  | "individual_financial_advice"
  | "personal_political_endorsement"
  | "out_of_template_scope";

export interface ScopeDecision {
  verdict: ScopeVerdict;
  template: string;
  question: string;
  rationale: string;
  refusals: RefusalReason[];
  intended_source_tiers: ("T1" | "T2" | "T3")[];
}

export interface AmbiguityCluster {
  cluster_id: number;
  representative_text: string;
  member_source_ids: string[];
}

export interface AmbiguityResult {
  is_ambiguous: boolean;
  clusters: AmbiguityCluster[];
  fallback_used: boolean;
}

export interface AmbiguityCandidate {
  source_id: string;
  text: string;
}

export async function checkAmbiguity(
  question: string,
  candidates: AmbiguityCandidate[],
): Promise<AmbiguityResult> {
  const response = await fetch(`${BACKEND_URL}/ambiguity`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      question,
      candidates,
      min_cluster_size: 2,
      similarity_threshold: 0.5,
    }),
  });
  return asJsonOrThrow<AmbiguityResult>(response);
}

export async function checkScope(
  template: TemplateId,
  question: string,
): Promise<ScopeDecision> {
  const response = await fetch(`${BACKEND_URL}/scope/check`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ template, question }),
  });
  return asJsonOrThrow<ScopeDecision>(response);
}

export interface TemplateContent {
  template_id: string;
  template_name: string;
  summary: string;
  primary_domains: string[];
  source_tiers: Record<"T1" | "T2" | "T3", string[]>;
  min_sources_per_tier: Record<"T1" | "T2" | "T3", number>;
  frame_manifest: { frame_id: string; frame_name: string }[];
  refusal_patterns: string[];
  sample_questions: string[];
  out_of_scope_examples: string[];
}

export async function listTemplates(): Promise<TemplateContent[]> {
  const response = await fetch(`${BACKEND_URL}/templates`);
  return asJsonOrThrow<TemplateContent[]>(response);
}

export interface SourceSpan {
  evidence_id: string;
  source_url: string;
  source_tier: "T1" | "T2" | "T3";
  span_start: number;
  span_end: number;
  span_text: string;
}

export interface VerifiedSentence {
  section_id: string;
  sentence_text: string;
  provenance_tokens: string[];
  verifier_local_pass: boolean;
  verifier_global_pass: boolean;
  drop_reason: string | null;
}

export interface EvidenceContract {
  contract_version: "1.0";
  run_id: string;
  template: string;
  question: string;
  queued_at: string;
  finished_at: string;
  pipeline_status: string;
  evidence_pool: SourceSpan[];
  verified_sentences: VerifiedSentence[];
  frame_coverage: {
    frame_id: string;
    frame_name: string;
    sources_assigned: number;
    coverage_percent: number;
  }[];
  contradictions: {
    contradiction_id: string;
    section_id: string;
    claim_a: string;
    claim_b: string;
    evidence_a: string[];
    evidence_b: string[];
    resolution: string;
  }[];
  cost_usd: number;
  generator_model: string;
  verifier_model: string;
  family_segregation_passed: boolean;
}

export async function getBundle(runId: string): Promise<EvidenceContract> {
  const response = await fetch(`${BACKEND_URL}/runs/${runId}/bundle`);
  return asJsonOrThrow<EvidenceContract>(response);
}

export type ChartType = "forest_plot" | "comparison_table" | "timeline";

export interface VegaLiteSpec {
  $schema: string;
  title?: string;
  data: { values: Record<string, unknown>[] };
  mark?: unknown;
  encoding?: unknown;
  layer?: unknown;
  polaris_provenance: {
    chart_type: ChartType;
    evidence_ids: string[];
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

export async function getChart(
  runId: string,
  chartType: ChartType,
): Promise<VegaLiteSpec> {
  const response = await fetch(
    `${BACKEND_URL}/runs/${runId}/charts/${chartType}`,
  );
  return asJsonOrThrow<VegaLiteSpec>(response);
}

export function downloadBundleAsJson(bundle: EvidenceContract): void {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `polaris_bundle_${bundle.run_id}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

/**
 * Subscribe to /stream/{runId}. Returns the EventSource so the caller can
 * close it. Per Phase 0 stub, the backend yields 5 deterministic events.
 */
export function subscribeToRun(
  runId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const source = new EventSource(`${BACKEND_URL}/stream/${runId}`);

  const handler = (event: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(event.data);
      onEvent({ event: event.type, data: parsed });
    } catch {
      onEvent({ event: event.type, data: { raw: event.data } });
    }
  };

  for (const eventName of [
    "scope_decision",
    "retrieval_progress",
    "verifier_verdict",
    "section_complete",
    "run_complete",
  ]) {
    source.addEventListener(eventName, handler);
  }

  if (onError) {
    source.onerror = onError;
  }
  return source;
}
