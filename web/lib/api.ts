/**
 * POLARIS v6 API client.
 *
 * Mirrors the FastAPI contract in src/polaris_v6/api/{runs,health,stream}.py.
 *
 * I-carney-005 (2026-05-13): all requests are browser-relative paths so the
 * browser only ever talks to the webui origin. Next.js server-side rewrites
 * (web/next.config.ts) forward `/api/v6/*` → `${INTERNAL_API_URL}/*`, which
 * in production compose is `http://api:8000` (a Docker service name the
 * browser cannot resolve directly). In local dev, INTERNAL_API_URL defaults
 * to http://localhost:8000 so `npm run dev` against a host-port-mapped
 * backend works without any client-side configuration.
 *
 * Codex diff iter-1 P1-B: NEXT_PUBLIC_BACKEND_URL is no longer consulted at
 * runtime — baking an absolute http://api:8000 into the client bundle would
 * make production browsers attempt direct Docker-network reach and fail.
 */

import { authHeader, redirectToSignIn } from "@/lib/auth";

const BACKEND_URL = "/api/v6";

/**
 * I-rdy-004 (#500) — fetch wrapper for every v6 API call. Injects the
 * `Authorization: Bearer <jwt>` header, preserves any caller-supplied
 * headers, and does NOT force a content-type (so `FormData` uploads keep
 * their auto-generated multipart boundary). On a 401 it clears the token
 * and routes to /sign-in.
 */
async function authFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers ?? {});
  for (const [key, value] of Object.entries(authHeader())) {
    headers.set(key, value);
  }
  const response = await globalThis.fetch(url, { ...init, headers });
  if (response.status === 401) {
    redirectToSignIn();
  }
  return response;
}

/**
 * I-rdy-004 — SSE URL for a run's event stream. Native `EventSource` cannot
 * set request headers, so the JWT rides as the `access_token` query param;
 * the backend `require_auth` accepts it for `/stream/*` paths only.
 */
export function streamUrl(runId: string): string {
  const token = authHeader().Authorization?.replace(/^Bearer /, "");
  const base = `${BACKEND_URL}/stream/${encodeURIComponent(runId)}`;
  return token ? `${base}?access_token=${encodeURIComponent(token)}` : base;
}

export type TemplateId =
  | "clinical"
  | "policy"
  | "tech"
  | "due_diligence"
  | "ai_sovereignty"
  | "canada_us"
  | "workforce"
  | "custom";

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

/**
 * Thrown by createRun when POST /runs is rejected by the 1-concurrent-session
 * constraint (I-rdy-013): a research run is already queued or in progress.
 */
export class ConcurrentRunError extends Error {
  readonly activeRunId: string;
  readonly activeStatus: string;
  constructor(message: string, activeRunId: string, activeStatus: string) {
    super(message);
    this.name = "ConcurrentRunError";
    this.activeRunId = activeRunId;
    this.activeStatus = activeStatus;
  }
}

export async function createRun(
  payload: RunRequest,
): Promise<RunStatusResponse> {
  const response = await authFetch(`${BACKEND_URL}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.status === 409) {
    // Read the body exactly once, then unwrap FastAPI's { detail: {...} }
    // envelope. The 1-concurrent-session reject carries a structured detail;
    // any other 409 falls through to a generic ApiError.
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const detail = (body?.detail ?? body) as {
      code?: string;
      message?: string;
      active_run_id?: string;
      active_status?: string;
    } | null;
    if (detail && detail.code === "concurrent_run_active") {
      throw new ConcurrentRunError(
        detail.message ?? "A research run is already in progress.",
        detail.active_run_id ?? "",
        detail.active_status ?? "in_progress",
      );
    }
    const error = new Error("POLARIS backend returned 409") as ApiError;
    error.status = 409;
    error.body = body;
    throw error;
  }
  return asJsonOrThrow<RunStatusResponse>(response);
}

export async function getRun(runId: string): Promise<RunStatusResponse> {
  const response = await authFetch(`${BACKEND_URL}/runs/${runId}`);
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
  content?: string;
  html?: string;
}

export async function getUpload(document_id: string): Promise<UploadResponse> {
  const response = await authFetch(
    `${BACKEND_URL}/upload/${encodeURIComponent(document_id)}`,
  );
  return asJsonOrThrow<UploadResponse>(response);
}

export async function uploadDocument(
  file: File,
  classification: DataClassification = "UNKNOWN",
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("classification", classification);
  const response = await authFetch(`${BACKEND_URL}/upload`, {
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
  const response = await authFetch(`${BACKEND_URL}/ambiguity`, {
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
  const response = await authFetch(`${BACKEND_URL}/scope/check`, {
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
  const response = await authFetch(`${BACKEND_URL}/templates`);
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
  const response = await authFetch(`${BACKEND_URL}/runs/${runId}/bundle`);
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
  const response = await authFetch(
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
  const source = new EventSource(streamUrl(runId));

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

// ---------------------------------------------------------------------------
// Slice 001 — Clinical Scope Discovery + Ambiguity Detection
// Mirrors src/polaris_graph/scope/scope_decision.py + api/intake_route.py.
// ---------------------------------------------------------------------------

export type IntakeStatus =
  | "in_scope"
  | "ambiguous_needs_clarification"
  | "out_of_scope"
  | "refused";

export type IntakeScopeClass =
  | "clinical_efficacy"
  | "clinical_safety"
  | "clinical_diagnosis"
  | "clinical_prognosis"
  | "out_of_scope";

export type PicoAxisName = "population" | "intervention" | "outcome";

export interface IntakeAmbiguityAxis {
  axis: PicoAxisName;
  plausible_interpretations: string[];
  needs_clarification: boolean;
}

export interface IntakeScopeDecision {
  status: IntakeStatus;
  scope_class: IntakeScopeClass | null;
  ambiguity_axes: IntakeAmbiguityAxis[];
  clarifications_needed: string[];
  provenance: Record<string, unknown>;
  decision_id: string;
  decided_at_utc: string;
  latency_ms: number;
  needs_disambiguation?: boolean;
  candidate_snippets?: { text: string; embedding: number[] }[];
}

export type DisambiguationCluster = {
  cluster_id: number;
  label: string;
  sample_snippets: string[];
};

export interface DisambiguationResponse {
  is_ambiguous: boolean;
  num_clusters: number;
  clusters: DisambiguationCluster[];
  server_time_utc: string;
}

export async function runDisambiguation(
  candidates: { text: string; embedding: number[] }[],
): Promise<DisambiguationResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/disambiguation`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ candidates }),
  });
  return asJsonOrThrow<DisambiguationResponse>(response);
}

export interface IntakeSuccessResponse {
  error: false;
  decision: IntakeScopeDecision;
  server_time_utc: string;
}

export interface IntakeErrorBody {
  error: true;
  code: "too_short" | "too_long" | "invalid_input";
  message: string;
  raw: string;
}

export class IntakeBadRequestError extends Error {
  code: IntakeErrorBody["code"];
  raw: string;
  constructor(body: IntakeErrorBody) {
    super(body.message);
    this.name = "IntakeBadRequestError";
    this.code = body.code;
    this.raw = body.raw;
  }
}

export async function runIntake(
  question: string,
): Promise<IntakeSuccessResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/intake`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (response.status === 400) {
    const detail = await response.json().catch(() => null);
    const body = (detail?.detail ?? detail) as IntakeErrorBody | null;
    if (body && body.error) {
      throw new IntakeBadRequestError(body);
    }
  }

  return asJsonOrThrow<IntakeSuccessResponse>(response);
}

export interface IntakeHealthResponse {
  status: "ok";
  slice: string;
  pipeline_stages: string[];
}

export async function getIntakeHealth(): Promise<IntakeHealthResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/intake/health`);
  return asJsonOrThrow<IntakeHealthResponse>(response);
}

// ---------------------------------------------------------------------------
// Slice 002 — Clinical Retrieval (verified clinical sources)
// Mirrors src/polaris_graph/retrieval2/evidence_pool.py +
// api/retrieval_route.py.
// ---------------------------------------------------------------------------

export type RetrievalSourceTier = "T1" | "T2" | "T3";

export interface RetrievalSource {
  source_id: string;
  url: string;
  domain: string;
  tier: RetrievalSourceTier;
  title: string;
  publication_date: string | null;
  authors: string[];
  snippet: string;
  full_text_available: boolean;
  full_text: string | null;
  fetched_at_utc: string;
  provenance: Record<string, unknown>;
  retracted?: boolean;
}

export interface RetrievalAdequacyVerdict {
  is_adequate: boolean;
  sources_per_tier: Record<RetrievalSourceTier, number>;
  min_required_per_tier: Record<RetrievalSourceTier, number>;
  failure_reason: string | null;
}

export interface EvidencePool {
  pool_id: string;
  decision_id: string;
  sources: RetrievalSource[];
  adequacy: RetrievalAdequacyVerdict;
  queries_executed: string[];
  retrieval_started_at_utc: string;
  retrieval_finished_at_utc: string;
  latency_ms: number;
  cost_usd: number;
}

export interface RetrievalSuccessResponse {
  error: false;
  pool: EvidencePool;
  server_time_utc: string;
}

export interface RetrievalErrorBody {
  error: true;
  code: "wrong_status" | "wrong_scope_class" | "fetch_backend_unavailable";
  message: string;
  decision_id: string | null;
}

export class RetrievalBadRequestError extends Error {
  code: RetrievalErrorBody["code"];
  decision_id: string | null;
  constructor(body: RetrievalErrorBody) {
    super(body.message);
    this.name = "RetrievalBadRequestError";
    this.code = body.code;
    this.decision_id = body.decision_id;
  }
}

export async function runRetrieval(
  decision: IntakeScopeDecision,
): Promise<RetrievalSuccessResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/retrieval`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ decision }),
  });

  if (response.status === 400) {
    const detail = await response.json().catch(() => null);
    const body = (detail?.detail ?? detail) as RetrievalErrorBody | null;
    if (body && body.error) {
      throw new RetrievalBadRequestError(body);
    }
  }

  return asJsonOrThrow<RetrievalSuccessResponse>(response);
}

export interface RetrievalHealthResponse {
  status: "ok";
  slice: string;
  pipeline_stages: string[];
  fetch_backend: string;
}

export async function getRetrievalHealth(): Promise<RetrievalHealthResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/retrieval/health`);
  return asJsonOrThrow<RetrievalHealthResponse>(response);
}

/** Convenience: count sources matching a given tier. */
export function countSourcesByTier(
  pool: EvidencePool,
  tier: RetrievalSourceTier,
): number {
  return pool.sources.filter((s) => s.tier === tier).length;
}

/** Convenience: dedupe + sort sources by tier (T1 first), then by domain. */
export function sortSourcesByTier(
  sources: RetrievalSource[],
): RetrievalSource[] {
  const tier_rank: Record<RetrievalSourceTier, number> = {
    T1: 0,
    T2: 1,
    T3: 2,
  };
  return [...sources].sort((a, b) => {
    const t = tier_rank[a.tier] - tier_rank[b.tier];
    if (t !== 0) return t;
    return a.domain.localeCompare(b.domain);
  });
}

// ---------------------------------------------------------------------------
// Slice 003 — Generator with strict-verify
// Mirrors src/polaris_graph/generator2/verified_report.py +
// api/generation_route.py.
// ---------------------------------------------------------------------------

export type SectionStatus = "verified" | "regenerated" | "dropped";

export type PipelineVerdict = "success" | "abort_no_verified_sections";

export type DropReason =
  | "invalid_token"
  | "span_out_of_range"
  | "numeric_mismatch"
  | "overlap_too_low"
  | "no_provenance_token";

export interface ReportVerifiedSentence {
  section_id: string;
  sentence_text: string;
  provenance_tokens: string[];
  verifier_pass: boolean;
  drop_reason: DropReason | null;
  evaluator_agrees: boolean | null;
  is_synthesis_claim?: boolean;
  assertion_surface?: AssertionSurface;
  contradiction?: ContradictionSignal | null;
  evaluator_disagreement?: EvaluatorDisagreement | null;
}

export interface EvaluatorDisagreement {
  generator_reading: string;
  evaluator_reading: string;
  cited_sources: string[];
  evaluator_model: string;
}

export type ContradictionEvidenceType =
  | "trial"
  | "guideline"
  | "meta_analysis"
  | "observational"
  | "regulatory_label"
  | "expert_opinion"
  | "unspecified";

export type Jurisdiction =
  | "canada"
  | "us"
  | "eu"
  | "uk"
  | "who"
  | "other"
  | "unspecified";

export interface ContradictionSide {
  source_id: string;
  source_tier: "T1" | "T2" | "T3";
  sample_size?: number | null;
  hedge_language: string;
  pt08_flag?: string | null;
  claim_excerpt: string;
  evidence_type?: ContradictionEvidenceType;
  jurisdiction?: Jurisdiction;
}

export type ContradictionKind = "multi_source" | "self_contradiction";

export type ContradictionCategory =
  | "numeric"
  | "categorical"
  | "regulatory"
  | "temporal"
  | "jurisdictional"
  | "other";

export interface ContradictionSignal {
  disagreeing_source_count: number;
  summary: string;
  sides?: ContradictionSide[];
  kind?: ContradictionKind;
  category?: ContradictionCategory;
}

export type AssertionSurface =
  | "prose"
  | "table"
  | "summary_bullet"
  | "limitation"
  | "caption"
  | "heading";

export interface VerifiedReportSection {
  section_id: string;
  section_title: string;
  verified_sentences: ReportVerifiedSentence[];
  section_verify_pass_rate: number;
  section_status: SectionStatus;
}

export type GapReason =
  | "paywalled"
  | "no_oa"
  | "source_tier_ineligible"
  | "language_unavailable"
  | "retracted_only"
  | "jurisdiction_outside"
  | "not_indexed"
  | "embargoed"
  | "other";

export interface FrameGap {
  entity_name: string;
  reason: GapReason;
  reason_detail?: string | null;
}

export interface FrameCoverage {
  covered_entity_count: number;
  total_entity_count: number;
  gaps: FrameGap[];
}

export interface VerifiedReport {
  report_id: string;
  pool_id: string;
  decision_id: string;
  sections: VerifiedReportSection[];
  overall_verify_pass_rate: number;
  pipeline_verdict: PipelineVerdict;
  generator_model: string;
  evaluator_model: string;
  family_segregation_passed: boolean;
  verifier_pass_threshold: number;
  started_at_utc: string;
  finished_at_utc: string;
  latency_ms: number;
  cost_usd: number;
  frame_coverage?: FrameCoverage | null;
}

export interface GenerationSuccessResponse {
  error: false;
  report: VerifiedReport;
  server_time_utc: string;
}

export interface GenerationErrorBody {
  error: true;
  code:
    | "inadequate_pool"
    | "completion_backend_unavailable"
    | "malformed_output";
  message: string;
  pool_id: string | null;
  decision_id: string | null;
}

export class GenerationBadRequestError extends Error {
  code: GenerationErrorBody["code"];
  pool_id: string | null;
  decision_id: string | null;
  constructor(body: GenerationErrorBody) {
    super(body.message);
    this.name = "GenerationBadRequestError";
    this.code = body.code;
    this.pool_id = body.pool_id;
    this.decision_id = body.decision_id;
  }
}

export async function runGeneration(
  pool: EvidencePool,
  scope_class?: string | null,
): Promise<GenerationSuccessResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/generation`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ pool, scope_class: scope_class ?? null }),
  });

  if (response.status === 400) {
    const detail = await response.json().catch(() => null);
    const body = (detail?.detail ?? detail) as GenerationErrorBody | null;
    if (body && body.error) {
      throw new GenerationBadRequestError(body);
    }
  }

  return asJsonOrThrow<GenerationSuccessResponse>(response);
}

export interface GenerationHealthResponse {
  status: "ok";
  slice: string;
  pipeline_stages: string[];
  completion_backend: string;
}

export async function getGenerationHealth(): Promise<GenerationHealthResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/generation/health`);
  return asJsonOrThrow<GenerationHealthResponse>(response);
}

/** Filter to non-dropped sections (verified + regenerated). */
export function keptSections(report: VerifiedReport): VerifiedReportSection[] {
  return report.sections.filter((s) => s.section_status !== "dropped");
}

/** Filter sentences to those that passed strict_verify. */
export function keptSentences(
  section: VerifiedReportSection,
): ReportVerifiedSentence[] {
  return section.verified_sentences.filter((s) => s.verifier_pass);
}

// ---------------------------------------------------------------------------
// Slice 004 — Audit bundle (GPG-signed .tar.gz export)
// Mirrors src/polaris_graph/api/audit_bundle_route.py.
// ---------------------------------------------------------------------------

export interface AuditBundleErrorBody {
  error: true;
  code:
    | "fk_chain_mismatch"
    | "verdict_not_success"
    | "cited_span_unreachable_after_snapshot"
    | "copyrighted_span_in_bundle"
    | "gpg_unavailable"
    | "sign_failed";
  message: string;
  report_id: string | null;
}

export class AuditBundleError extends Error {
  code: AuditBundleErrorBody["code"];
  report_id: string | null;
  constructor(body: AuditBundleErrorBody) {
    super(body.message);
    this.name = "AuditBundleError";
    this.code = body.code;
    this.report_id = body.report_id;
  }
}

/**
 * Build + download a GPG-signed audit bundle for the given research chain.
 *
 * Returns a Blob of the audit_<id>.tar.gz on success. On HTTP 4xx/5xx
 * with a structured error body, throws AuditBundleError with the .code
 * field set so callers can show specific UX (e.g. "GPG signer not
 * configured" vs "report verdict not success").
 */
export async function downloadAuditBundle(
  decision: IntakeScopeDecision,
  pool: EvidencePool,
  report: VerifiedReport,
): Promise<Blob> {
  const response = await authFetch(`${BACKEND_URL}/api/audit-bundle`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ decision, pool, report }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const body = (detail?.detail ?? detail) as AuditBundleErrorBody | null;
    if (body && body.error) {
      throw new AuditBundleError(body);
    }
    throw new Error(`Audit bundle request failed: HTTP ${response.status}`);
  }
  return await response.blob();
}

export interface BundlePreviewByContentType {
  count: number;
  bytes: number;
}

export interface BundlePreviewResponse {
  preview_bundle_id: string;
  generator_model: string;
  polaris_version: string;
  file_count: number;
  total_bytes: number;
  content_type_breakdown: Record<string, BundlePreviewByContentType>;
}

export async function previewAuditBundle(
  decision: IntakeScopeDecision,
  pool: EvidencePool,
  report: VerifiedReport,
): Promise<BundlePreviewResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/audit-bundle/preview`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ decision, pool, report }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const body = (detail?.detail ?? detail) as AuditBundleErrorBody | null;
    if (body && body.error) {
      throw new AuditBundleError(body);
    }
    throw new Error(`Bundle preview request failed: HTTP ${response.status}`);
  }
  return (await response.json()) as BundlePreviewResponse;
}

export interface AuditBundleHealthResponse {
  status: "ok";
  slice: string;
  pipeline_stages: string[];
  signing_backend: string;
}

export async function getAuditBundleHealth(): Promise<AuditBundleHealthResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/audit-bundle/health`);
  return asJsonOrThrow<AuditBundleHealthResponse>(response);
}

// ---------------------------------------------------------------------------
// Slice 005 — BEAT-BOTH benchmark
// Mirrors src/polaris_graph/api/benchmark_route.py +
// src/polaris_graph/benchmark/beat_both_scorer.py.
// ---------------------------------------------------------------------------

export type BenchmarkDimension =
  | "sourcing_tier_mix"
  | "numeric_grounding"
  | "provenance_density"
  | "refusal_correctness"
  | "coverage_completeness"
  | "latency"
  | "auditability";

export interface BenchmarkSystemScores {
  system: string;
  by_dimension: Record<BenchmarkDimension, number | null>;
  evidence: Record<BenchmarkDimension, string[]>;
}

export interface BenchmarkQuestionScores {
  question_id: string;
  question_text: string;
  is_refusal_bait: boolean;
  polaris: BenchmarkSystemScores;
  chatgpt: BenchmarkSystemScores;
  gemini: BenchmarkSystemScores;
}

export interface BenchmarkAggregateScoreboard {
  polaris_mean: Record<BenchmarkDimension, number | null>;
  chatgpt_mean: Record<BenchmarkDimension, number | null>;
  gemini_mean: Record<BenchmarkDimension, number | null>;
  n_questions: number;
}

export interface BenchmarkScoreboard {
  benchmark_id: string;
  ran_at_utc: string;
  per_question: BenchmarkQuestionScores[];
  aggregate: BenchmarkAggregateScoreboard;
  polaris_wins: number;
  external_wins: number;
  ties: number;
}

export interface BenchmarkHealthResponse {
  status: "ok";
  slice: string;
  results_root: string | null;
  available_benchmarks: string[];
}

export const BENCHMARK_DIMENSION_LABELS: Record<BenchmarkDimension, string> = {
  sourcing_tier_mix: "Sourcing tier mix",
  numeric_grounding: "Numeric grounding",
  provenance_density: "Provenance density",
  refusal_correctness: "Refusal correctness",
  coverage_completeness: "Coverage completeness",
  latency: "Latency",
  auditability: "Auditability",
};

export const ALL_BENCHMARK_DIMENSIONS: BenchmarkDimension[] = [
  "sourcing_tier_mix",
  "numeric_grounding",
  "provenance_density",
  "refusal_correctness",
  "coverage_completeness",
  "latency",
  "auditability",
];

export async function getBenchmarkHealth(): Promise<BenchmarkHealthResponse> {
  const response = await authFetch(`${BACKEND_URL}/api/benchmark/health`);
  return asJsonOrThrow<BenchmarkHealthResponse>(response);
}

export async function getBenchmarkScoreboard(
  benchmark_id: string,
): Promise<BenchmarkScoreboard> {
  const response = await authFetch(
    `${BACKEND_URL}/api/benchmark/${encodeURIComponent(benchmark_id)}/scoreboard`,
  );
  return asJsonOrThrow<BenchmarkScoreboard>(response);
}

export async function getBenchmarkSummary(
  benchmark_id: string,
): Promise<string> {
  const response = await authFetch(
    `${BACKEND_URL}/api/benchmark/${encodeURIComponent(benchmark_id)}/summary`,
  );
  if (!response.ok) {
    throw new Error(`benchmark summary fetch failed: HTTP ${response.status}`);
  }
  return await response.text();
}

// I-f14-002 — workspace memory client. Mirrors src/polaris_v6/api/memory.py.
export type MemoryKind =
  | "user_preference"
  | "domain_assumption"
  | "prior_run_summary"
  | "rejected_source"
  | "preferred_source";

export interface MemoryEntry {
  entry_id: string;
  workspace_id: string;
  kind: MemoryKind;
  content: string;
  created_at: string;
  last_used_at?: string | null;
  use_count: number;
  derived_from_run_ids: string[];
}

const _ws = (ws: string) =>
  `${BACKEND_URL}/workspaces/${encodeURIComponent(ws)}/memory`;

export async function listMemory(ws: string): Promise<MemoryEntry[]> {
  return asJsonOrThrow<MemoryEntry[]>(await authFetch(_ws(ws)));
}

export async function rememberMemory(
  ws: string,
  payload: {
    kind: MemoryKind;
    content: string;
    derived_from_run_ids?: string[];
  },
): Promise<MemoryEntry> {
  return asJsonOrThrow<MemoryEntry>(
    await authFetch(_ws(ws), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function forgetMemory(
  ws: string,
  entry_id: string,
): Promise<void> {
  const r = await authFetch(`${_ws(ws)}/${encodeURIComponent(entry_id)}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 404)
    throw new Error(`forget memory failed: HTTP ${r.status}`);
}

// ---------------------------------------------------------------------------
// F-snowball graph (I-snowball-002 backend + I-snowball-003a frontend).
// Cytoscape-format graph payload mirroring src/polaris_graph/api/graph_route.py.
// ---------------------------------------------------------------------------

export type GraphNodeType = "sentence" | "source" | "section" | "frame";
export type GraphEdgeType = "cites" | "contradicts" | "section_member";
export type GraphTier = "T1" | "T2" | "T3" | "T4" | "T5" | "T6" | "T7";
export type GraphFrameStatus = "pass" | "partial" | "fail";

export interface GraphNodeData {
  id: string;
  type: GraphNodeType;
  label: string;
  tier?: GraphTier;
  sentence_text?: string;
  source_url?: string;
  section_title?: string;
  frame_status?: GraphFrameStatus;
  classes?: string;
}

export interface GraphPosition {
  x: number;
  y: number;
}

export interface GraphNode {
  data: GraphNodeData;
  position?: GraphPosition | null;
}

export interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  edge_type: GraphEdgeType;
}

export interface GraphEdge {
  data: GraphEdgeData;
}

export interface GraphDiagnostics {
  bibliography_count: number;
  fallback_source_count: number;
  missing_reference_occurrence_count: number;
  referenced_unknown_evidence_ids: string[];
}

export interface GraphPayload {
  elements: { nodes: GraphNode[]; edges: GraphEdge[] };
  run_id: string;
  elements_hash: string;
  diagnostics: GraphDiagnostics;
  schema_version: "1.0";
}

export async function getRunGraph(runId: string): Promise<GraphPayload> {
  const res = await authFetch(`${BACKEND_URL}/api/runs/${runId}/graph`);
  if (!res.ok) {
    const body = await res.text();
    const err = new Error(
      `getRunGraph(${runId}) HTTP ${res.status}: ${body}`,
    ) as ApiError;
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<GraphPayload>;
}
