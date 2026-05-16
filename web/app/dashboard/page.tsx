"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { DisambiguationModal } from "@/app/intake/components/disambiguation_modal";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  checkAmbiguity,
  checkScope,
  createRun,
  listTemplates,
  scanAmbiguity,
  uploadDocument,
  type AmbiguityResult,
  type ScopeDecision,
  type TemplateContent,
  type TemplateId,
  type UploadResponse,
} from "@/lib/api";

// Static fallback if /templates is unreachable. Keeps the dashboard usable
// even if the backend is down; live data preferred when available.
const FALLBACK_TEMPLATES: { id: TemplateId; title: string; domain: string }[] =
  [
    {
      id: "clinical",
      title: "Clinical drug audit",
      domain: "Health Canada / FDA",
    },
    { id: "policy", title: "Public policy", domain: "Health Canada / NICE" },
    {
      id: "tech",
      title: "Technology assessment",
      domain: "arXiv / IEEE / ACM",
    },
    {
      id: "due_diligence",
      title: "Due diligence",
      domain: "SEC EDGAR / USPTO",
    },
    { id: "ai_sovereignty", title: "AI sovereignty", domain: "ISED / CIFAR" },
    { id: "canada_us", title: "Canada–US relations", domain: "GAC / DFAIT" },
    {
      id: "workforce",
      title: "Workforce & productivity",
      domain: "ESDC / IRCC",
    },
    { id: "custom", title: "Custom research", domain: "Operator-defined" },
  ];

function templatesToCards(
  list: TemplateContent[],
): { id: TemplateId; title: string; domain: string }[] {
  return list.map((t) => ({
    id: t.template_id as TemplateId,
    title: t.template_name,
    domain: t.primary_domains.slice(0, 2).join(" / "),
  }));
}

// I-rdy-009 (#505): tri-state hard gate for the clinical question-only
// ambiguity scan. "Start run" is blocked for a clinical question-only run
// unless a candidate-fetch + detect_ambiguity scan has *successfully*
// completed — a failed or never-run scan must never fail open into
// createRun.
type ScanGate = "not_run" | "ok" | "failed";

export default function DashboardPage() {
  const router = useRouter();
  const [template, setTemplate] = useState<TemplateId>("clinical");
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scopeDecision, setScopeDecision] = useState<ScopeDecision | null>(
    null,
  );
  const [scopeChecking, setScopeChecking] = useState(false);
  const [uploads, setUploads] = useState<UploadResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [ambiguity, setAmbiguity] = useState<AmbiguityResult | null>(null);
  const [acknowledgedAmbiguity, setAcknowledgedAmbiguity] = useState(false);
  const [disambigModalOpen, setDisambigModalOpen] = useState(false);
  const [clinicalScanGate, setClinicalScanGate] = useState<ScanGate>("not_run");
  const [templates, setTemplates] = useState(FALLBACK_TEMPLATES);

  // I-rdy-009 (#505): monotonic scan generation. Every scan claims a
  // generation at start; any input edit (invalidateAmbiguityScan) bumps it.
  // An in-flight scan whose generation is stale on resolution discards its
  // result — so a scan started for question A can never set the gate "ok"
  // for an edited-to question B (a ref, so the bump is synchronous and the
  // discard is order-independent of the resolving promise).
  const scanGenerationRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    listTemplates()
      .then((live) => {
        if (!cancelled && live.length > 0) {
          setTemplates(templatesToCards(live));
        }
      })
      .catch(() => {
        // Keep fallback on failure; dashboard still works.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // I-rdy-009 (#505): any change to the question, template, or upload set
  // invalidates a prior ambiguity scan. A stale "ok" gate must not let an
  // edited question reach createRun without its own detect_ambiguity scan.
  // Bumping the generation also cancels any in-flight scan. Called from the
  // question / template / upload event handlers (not an effect — per the
  // react-hooks/set-state-in-effect rule).
  const invalidateAmbiguityScan = () => {
    scanGenerationRef.current += 1;
    setClinicalScanGate("not_run");
    setAmbiguity(null);
    setAcknowledgedAmbiguity(false);
    setDisambigModalOpen(false);
  };

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const results: UploadResponse[] = [];
      for (const file of list) {
        const result = await uploadDocument(file, "UNKNOWN");
        results.push(result);
      }
      setUploads((prev) => [...prev, ...results]);
      invalidateAmbiguityScan();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer.files.length > 0) {
      handleFiles(event.dataTransfer.files);
    }
  };

  const runScopeCheck = async () => {
    if (question.trim().length < 1) return;
    // Claim a fresh generation; an edit mid-scan bumps past it and the
    // result-application guards below will discard this scan's output.
    const myGeneration = (scanGenerationRef.current += 1);
    setScopeChecking(true);
    setError(null);
    setAmbiguity(null);
    setAcknowledgedAmbiguity(false);
    setDisambigModalOpen(false);
    setClinicalScanGate("not_run");
    // Captured here so the async branches below use a stable value.
    const clinicalQuestionOnly = template === "clinical" && uploads.length === 0;
    try {
      const decision = await checkScope(template, question.trim());
      if (scanGenerationRef.current !== myGeneration) return; // stale — discard
      setScopeDecision(decision);
      if (decision.verdict === "accepted" && uploads.length > 0) {
        // Upload-backed ambiguity: candidates come from document chunks.
        const candidates = uploads.flatMap((u, ui) =>
          u.chunk_preview.map((text, ci) => ({
            source_id: `${u.document_id}:${ui}-${ci}`,
            text,
          })),
        );
        if (candidates.length > 0) {
          const result = await checkAmbiguity(question.trim(), candidates);
          if (scanGenerationRef.current !== myGeneration) return; // stale
          setAmbiguity(result);
          if (result.is_ambiguous) setDisambigModalOpen(true);
        }
      } else if (decision.verdict !== "rejected" && clinicalQuestionOnly) {
        // Question-only clinical run: the backend fetches candidates and
        // runs detect_ambiguity. A successful scan is mandatory before a
        // run may start (see the onSubmit gate below).
        const result = await scanAmbiguity(question.trim());
        if (scanGenerationRef.current !== myGeneration) return; // stale
        setAmbiguity(result);
        setClinicalScanGate("ok");
        if (result.is_ambiguous) setDisambigModalOpen(true);
      }
    } catch (err) {
      if (scanGenerationRef.current !== myGeneration) return; // stale — discard
      if (clinicalQuestionOnly) setClinicalScanGate("failed");
      setError(err instanceof Error ? err.message : "Scope check failed");
    } finally {
      // Always clear the in-progress flag — only one runScopeCheck is ever
      // in flight (the button is disabled while scopeChecking).
      setScopeChecking(false);
    }
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 4) {
      setError("Question must be at least 4 characters.");
      return;
    }
    if (scopeDecision?.verdict === "rejected") {
      setError("Scope gate rejected this question. Reframe before submitting.");
      return;
    }
    // I-rdy-009 (#505): a clinical question-only run must not start unless
    // the ambiguity scan succeeded. A 503, a never-run scan, a post-scan
    // edit, or a discarded stale in-flight scan all leave the gate != "ok".
    if (
      template === "clinical" &&
      uploads.length === 0 &&
      clinicalScanGate !== "ok"
    ) {
      setError(
        clinicalScanGate === "failed"
          ? "Ambiguity check is unavailable — retry Check scope before starting a run."
          : "Run Check scope first — the ambiguity guard must complete for clinical questions.",
      );
      return;
    }
    if (ambiguity?.is_ambiguous && !acknowledgedAmbiguity) {
      setError(
        "Ambiguity detected. Resolve it in the disambiguation modal before starting a run.",
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun({
        template,
        question: question.trim(),
        document_ids: uploads.map((u) => u.document_id),
      });
      router.push(`/runs/${run.run_id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada
            </span>
            <span className="text-foreground text-base font-semibold">
              Sovereign Deep Research
            </span>
          </Link>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-12">
        <section className="flex flex-col gap-2">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            Start a research run
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
            Pick a template and ask a focused question. Every claim returned
            will carry a provenance token tied to a primary source.
          </p>
        </section>

        <form onSubmit={onSubmit} className="flex flex-col gap-6">
          <fieldset className="flex flex-col gap-3">
            <legend className="text-foreground text-sm font-semibold">
              Template
            </legend>
            <div
              role="radiogroup"
              aria-label="Research template"
              className="grid grid-cols-1 gap-3 md:grid-cols-2"
            >
              {templates.map((t) => {
                const selected = template === t.id;
                return (
                  // F-26 (cycle-8 P1.2 root_cause): native button + role=radio
                  // makes template selection keyboard-operable. Survived 7
                  // prior cycles as <Card onClick=...> (React onClick on a
                  // <div> — keyboard-only users locked out of non-default
                  // templates, WCAG 2.1.1 Level A failure).
                  <button
                    key={t.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => {
                      setTemplate(t.id);
                      invalidateAmbiguityScan();
                    }}
                    className={`bg-card focus-visible:ring-ring/50 rounded-lg border p-4 text-left transition focus-visible:ring-2 focus-visible:outline-none ${
                      selected
                        ? "border-foreground"
                        : "border-border hover:border-muted-foreground"
                    }`}
                  >
                    <span className="text-card-foreground block text-xs font-medium tracking-widest uppercase">
                      {t.domain}
                    </span>
                    <span className="text-card-foreground mt-1 block text-base font-semibold">
                      {t.title}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="flex flex-col gap-2">
            <label
              htmlFor="question"
              className="text-foreground text-sm font-semibold"
            >
              Research question
            </label>
            <Input
              id="question"
              type="text"
              placeholder="What does the latest CMHC data say about Q3 2025 housing starts?"
              value={question}
              onChange={(e) => {
                setQuestion(e.target.value);
                invalidateAmbiguityScan();
              }}
              minLength={4}
              maxLength={2000}
              required
              disabled={submitting}
            />
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-foreground text-sm font-semibold">
              Optional: upload supporting documents
            </span>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-sm transition ${
                dragOver
                  ? "border-foreground bg-muted/40"
                  : "border-border bg-muted/10"
              }`}
            >
              <p className="text-muted-foreground">
                Drag PDFs, .docx, .md, or .txt here, or
              </p>
              <label className="text-foreground inline-flex min-h-[24px] cursor-pointer items-center px-2 underline-offset-4 hover:underline">
                <span>browse files</span>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.md,.txt"
                  className="hidden"
                  disabled={uploading || submitting}
                  onChange={(e) => {
                    if (e.target.files) handleFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
              </label>
              {uploading && (
                <p className="text-muted-foreground text-xs">Uploading…</p>
              )}
            </div>
            {uploads.length > 0 && (
              <ul className="text-muted-foreground flex flex-col gap-1 text-xs">
                {uploads.map((u) => (
                  <li
                    key={u.document_id}
                    className="border-border bg-background flex items-center justify-between rounded-md border px-3 py-2"
                  >
                    <span className="truncate">
                      <span className="text-foreground font-medium">
                        {u.filename}
                      </span>
                      <span className="ml-2 font-mono">
                        {(u.bytes / 1024).toFixed(1)} KB
                      </span>
                      <span className="ml-2 uppercase">{u.classification}</span>
                      <span className="ml-2">{u.parse_status}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setUploads((prev) =>
                          prev.filter((p) => p.document_id !== u.document_id),
                        );
                        invalidateAmbiguityScan();
                      }}
                      className="text-foreground inline-flex min-h-[24px] min-w-[24px] items-center justify-center rounded px-1 font-medium hover:underline"
                    >
                      remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {scopeDecision && (
            <Card
              role="status"
              aria-live="polite"
              className={
                scopeDecision.verdict === "rejected"
                  ? "border-destructive/60"
                  : scopeDecision.verdict === "needs_clarification"
                    ? "border-yellow-500/60"
                    : "border-emerald-500/60"
              }
            >
              <CardHeader>
                <CardDescription className="text-foreground text-xs font-semibold tracking-widest uppercase">
                  Scope discovery
                </CardDescription>
                <CardTitle className="text-base capitalize">
                  {scopeDecision.verdict.replace("_", " ")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{scopeDecision.rationale}</p>
                {scopeDecision.refusals.length > 0 && (
                  <p className="text-foreground mt-2 text-sm font-medium">
                    Refused: {scopeDecision.refusals.join(", ")}
                  </p>
                )}
                {scopeDecision.intended_source_tiers.length > 0 && (
                  <p className="text-foreground mt-2 text-xs font-medium">
                    Source tiers:{" "}
                    {scopeDecision.intended_source_tiers.join(", ")}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {/* I-rdy-009 (#505): inline notice — surfaces an unresolved
              ambiguity and re-opens the disambiguation modal. The modal
              itself (below) is the primary surface; this keeps the user
              able to act after dismissing it, and explains why "Start run"
              is blocked. */}
          {ambiguity?.is_ambiguous && !acknowledgedAmbiguity && (
            <div
              role="status"
              aria-live="polite"
              data-testid="dashboard-ambiguity-notice"
              className="border-yellow-500/50 bg-yellow-50/40 flex flex-wrap items-center justify-between gap-3 rounded-md border p-3 text-sm"
            >
              <span className="text-foreground">
                Disambiguation needed — {ambiguity.clusters.length} possible
                meanings detected. Resolve before starting a run.
              </span>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDisambigModalOpen(true)}
              >
                Review meanings
              </Button>
            </div>
          )}

          <DisambiguationModal
            open={disambigModalOpen}
            clusters={(ambiguity?.clusters ?? []).map((c) => ({
              cluster_id: c.cluster_id,
              label: c.representative_text.slice(0, 80),
              sample_snippets: [c.representative_text],
            }))}
            onSelectCluster={() => {
              setAcknowledgedAmbiguity(true);
              setDisambigModalOpen(false);
            }}
            onCancel={() => setDisambigModalOpen(false)}
          />

          {error && (
            <p
              role="alert"
              className="border-destructive/60 text-foreground rounded-md border p-3 text-sm font-medium"
            >
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-3">
            <Button
              variant="ghost"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={runScopeCheck}
              disabled={scopeChecking || question.trim().length < 1}
            >
              {scopeChecking ? "Checking…" : "Check scope"}
            </Button>
            <Button
              type="submit"
              disabled={submitting || scopeDecision?.verdict === "rejected"}
            >
              {submitting ? "Queuing…" : "Start run"}
            </Button>
          </div>
        </form>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Phase 0 scaffold</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
