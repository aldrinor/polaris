"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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
    { id: "trade", title: "Trade & tariff", domain: "USMCA / WTO" },
    {
      id: "housing",
      title: "Housing & productivity",
      domain: "StatCan / CMHC",
    },
    { id: "defense", title: "Defense & Arctic", domain: "DND / NORAD" },
    {
      id: "climate",
      title: "Climate & critical minerals",
      domain: "ECCC / NRCan",
    },
    { id: "ai_sovereignty", title: "AI sovereignty", domain: "ISED / CIFAR" },
    { id: "canada_us", title: "Canada–US relations", domain: "GAC / DFAIT" },
    {
      id: "workforce",
      title: "Workforce & productivity",
      domain: "ESDC / IRCC",
    },
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
  const [templates, setTemplates] = useState(FALLBACK_TEMPLATES);

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
    setScopeChecking(true);
    setError(null);
    setAmbiguity(null);
    setAcknowledgedAmbiguity(false);
    try {
      const decision = await checkScope(template, question.trim());
      setScopeDecision(decision);
      if (decision.verdict === "accepted" && uploads.length > 0) {
        const candidates = uploads.flatMap((u, ui) =>
          u.chunk_preview.map((text, ci) => ({
            source_id: `${u.document_id}:${ui}-${ci}`,
            text,
          })),
        );
        if (candidates.length > 0) {
          const result = await checkAmbiguity(question.trim(), candidates);
          setAmbiguity(result);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scope check failed");
    } finally {
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
    if (ambiguity?.is_ambiguous && !acknowledgedAmbiguity) {
      setError(
        "Ambiguity detected. Acknowledge in the panel below or refine the question.",
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
                    onClick={() => setTemplate(t.id)}
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
              onChange={(e) => setQuestion(e.target.value)}
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
                      onClick={() =>
                        setUploads((prev) =>
                          prev.filter((p) => p.document_id !== u.document_id),
                        )
                      }
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

          {ambiguity?.is_ambiguous && (
            <Card
              role="status"
              aria-live="polite"
              className="border-yellow-500/50 bg-yellow-50/40"
            >
              <CardHeader>
                <CardDescription className="text-xs tracking-widest uppercase">
                  Disambiguation needed (ambiguity guard)
                </CardDescription>
                <CardTitle className="text-base">
                  {ambiguity.clusters.length} possible meanings detected
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">
                  Your question or uploads suggest more than one topic. Pick one
                  to refine the question, or acknowledge to proceed with all of
                  them in scope.
                </p>
                <ul className="mt-3 flex flex-col gap-2 text-sm">
                  {ambiguity.clusters.map((c) => (
                    <li
                      key={c.cluster_id}
                      className="border-border bg-background rounded-md border p-2"
                    >
                      <span className="text-foreground font-medium">
                        Cluster {c.cluster_id + 1}:
                      </span>{" "}
                      <span className="text-muted-foreground">
                        {c.representative_text}
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex gap-2">
                  <Button
                    type="button"
                    variant={acknowledgedAmbiguity ? "default" : "outline"}
                    onClick={() => setAcknowledgedAmbiguity((v) => !v)}
                  >
                    {acknowledgedAmbiguity
                      ? "Acknowledged — will run on all clusters"
                      : "Acknowledge ambiguity"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

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
