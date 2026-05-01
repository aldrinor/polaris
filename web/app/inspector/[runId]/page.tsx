"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  downloadBundleAsJson,
  getBundle,
  type EvidenceContract,
  type SourceSpan,
} from "@/lib/api";

interface InspectorPageProps {
  params: Promise<{ runId: string }>;
}

export default function InspectorPage({ params }: InspectorPageProps) {
  const { runId } = use(params);
  const [bundle, setBundle] = useState<EvidenceContract | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<SourceSpan | null>(
    null,
  );
  const [activeTab, setActiveTab] = useState<
    "sentences" | "frames" | "contradictions" | "pool"
  >("sentences");

  useEffect(() => {
    let cancelled = false;
    getBundle(runId)
      .then((b) => {
        if (!cancelled) setBundle(b);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Bundle load failed");
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const evidenceById = (id: string) =>
    bundle?.evidence_pool.find((s) => s.evidence_id === id) ?? null;

  const tabs: { id: typeof activeTab; label: string; count: number }[] = bundle
    ? [
        {
          id: "sentences",
          label: "Verified sentences",
          count: bundle.verified_sentences.length,
        },
        {
          id: "frames",
          label: "Frame coverage",
          count: bundle.frame_coverage.length,
        },
        {
          id: "contradictions",
          label: "Contradictions",
          count: bundle.contradictions.length,
        },
        {
          id: "pool",
          label: "Evidence pool",
          count: bundle.evidence_pool.length,
        },
      ]
    : [];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Inspector
            </span>
            <span className="text-foreground text-base font-semibold">
              Run {runId}
            </span>
          </Link>
          {bundle && (
            <Button
              variant="outline"
              onClick={() => downloadBundleAsJson(bundle)}
            >
              Export bundle JSON
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
        {error && (
          <p
            role="alert"
            className="text-destructive border-destructive/50 bg-destructive/10 rounded-md border p-3 text-sm"
          >
            {error}
          </p>
        )}

        {bundle && (
          <>
            <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardDescription className="text-xs tracking-widest uppercase">
                    Pipeline status
                  </CardDescription>
                  <CardTitle className="font-mono text-sm">
                    {bundle.pipeline_status}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card
                className={
                  bundle.family_segregation_passed
                    ? "border-emerald-500/40 bg-emerald-50/30"
                    : "border-destructive/60 bg-destructive/10"
                }
              >
                <CardHeader>
                  <CardDescription className="text-xs tracking-widest uppercase">
                    Two-family invariant
                  </CardDescription>
                  <CardTitle className="text-sm">
                    {bundle.family_segregation_passed ? "PASS" : "FAIL"} ·{" "}
                    {bundle.generator_model} → {bundle.verifier_model}
                  </CardTitle>
                </CardHeader>
                {!bundle.family_segregation_passed && (
                  <CardContent className="text-destructive text-xs">
                    CLAUDE.md §9.1 invariant violated. Run output is suspect:
                    generator and verifier share lineage. Re-run with
                    family-segregated models before trusting verdicts.
                  </CardContent>
                )}
              </Card>
              <Card>
                <CardHeader>
                  <CardDescription className="text-xs tracking-widest uppercase">
                    Cost
                  </CardDescription>
                  <CardTitle className="text-sm">
                    USD {bundle.cost_usd.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
            </section>

            <section className="flex flex-col gap-2">
              <h1 className="text-foreground text-2xl font-semibold tracking-tight">
                {bundle.question}
              </h1>
              <p className="text-muted-foreground text-sm">
                Template:{" "}
                <span className="text-foreground">{bundle.template}</span>
                {" · "}Queued <time>{bundle.queued_at}</time>
                {" · "}Finished <time>{bundle.finished_at}</time>
              </p>
            </section>

            <nav className="border-border flex gap-2 border-b">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className={`border-b-2 px-3 py-2 text-sm transition ${
                    activeTab === t.id
                      ? "border-foreground text-foreground"
                      : "text-muted-foreground hover:text-foreground border-transparent"
                  }`}
                >
                  {t.label}{" "}
                  <span className="font-mono text-xs">({t.count})</span>
                </button>
              ))}
            </nav>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="flex flex-col gap-3 lg:col-span-2">
                {activeTab === "sentences" && (
                  <SentencesTab
                    bundle={bundle}
                    onSelect={(id) => setSelectedEvidence(evidenceById(id))}
                    onJumpToContradictions={() =>
                      setActiveTab("contradictions")
                    }
                  />
                )}
                {activeTab === "frames" && <FramesTab bundle={bundle} />}
                {activeTab === "contradictions" && (
                  <ContradictionsTab
                    bundle={bundle}
                    onSelect={(id) => setSelectedEvidence(evidenceById(id))}
                  />
                )}
                {activeTab === "pool" && (
                  <PoolTab
                    bundle={bundle}
                    onSelect={(id) => setSelectedEvidence(evidenceById(id))}
                  />
                )}
              </div>
              <aside className="lg:col-span-1">
                <EvidencePane
                  span={selectedEvidence}
                  onClose={() => setSelectedEvidence(null)}
                />
              </aside>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function SentencesTab({
  bundle,
  onSelect,
  onJumpToContradictions,
}: {
  bundle: EvidenceContract;
  onSelect: (id: string) => void;
  onJumpToContradictions: () => void;
}) {
  if (bundle.verified_sentences.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No verified sentences. Pipeline status:{" "}
        <span className="font-mono">{bundle.pipeline_status}</span>.
      </p>
    );
  }
  const sectionsWithContradictions = new Set(
    bundle.contradictions.map((c) => c.section_id),
  );
  return (
    <ul className="flex flex-col gap-3">
      {bundle.verified_sentences.map((s, idx) => (
        <li key={idx}>
          <Card>
            <CardHeader>
              <CardDescription className="text-xs tracking-widest uppercase">
                {s.section_id} · {s.verifier_local_pass ? "local✓" : "local✗"} ·{" "}
                {s.verifier_global_pass ? "global✓" : "global✗"}
                {sectionsWithContradictions.has(s.section_id) && (
                  <button
                    type="button"
                    onClick={onJumpToContradictions}
                    className="ml-2 rounded bg-yellow-100 px-1.5 py-0.5 text-xs font-medium text-yellow-900 normal-case hover:bg-yellow-200"
                  >
                    contradiction in section →
                  </button>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm">
                {renderSentenceWithTokens(s.sentence_text, onSelect)}
              </p>
              {s.drop_reason && (
                <p className="text-destructive mt-2 text-xs">
                  Dropped: {s.drop_reason}
                </p>
              )}
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function renderSentenceWithTokens(
  text: string,
  onSelect: (id: string) => void,
): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const re = /\[#ev:([^:\]]+):\d+-\d+\]/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const evidenceId = match[1];
    parts.push(
      <button
        key={`${match.index}-${evidenceId}`}
        type="button"
        onClick={() => onSelect(evidenceId)}
        className="text-foreground bg-muted hover:bg-foreground hover:text-background mx-0.5 rounded px-1 font-mono text-xs transition"
      >
        {match[0]}
      </button>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

function FramesTab({ bundle }: { bundle: EvidenceContract }) {
  if (bundle.frame_coverage.length === 0) {
    return <p className="text-muted-foreground text-sm">No frame coverage.</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {bundle.frame_coverage.map((f) => (
        <li key={f.frame_id}>
          <Card>
            <CardHeader>
              <CardDescription className="text-xs tracking-widest uppercase">
                {f.frame_id}
              </CardDescription>
              <CardTitle className="text-base">{f.frame_name}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="bg-muted h-2 w-full overflow-hidden rounded">
                <div
                  className="bg-foreground h-full"
                  style={{ width: `${f.coverage_percent}%` }}
                />
              </div>
              <p className="text-muted-foreground mt-2 text-xs">
                {f.sources_assigned} sources · {f.coverage_percent.toFixed(1)}%
                coverage
              </p>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function ContradictionsTab({
  bundle,
  onSelect,
}: {
  bundle: EvidenceContract;
  onSelect: (id: string) => void;
}) {
  if (bundle.contradictions.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No contradictions detected.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {bundle.contradictions.map((c) => (
        <li key={c.contradiction_id}>
          <Card>
            <CardHeader>
              <CardDescription className="text-xs tracking-widest uppercase">
                {c.contradiction_id} · {c.section_id} · {c.resolution}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                <div className="border-border rounded-md border p-2">
                  <p className="text-foreground text-sm font-medium">A</p>
                  <p className="text-sm">{c.claim_a}</p>
                  <div className="mt-1 flex flex-wrap gap-1 text-xs">
                    {c.evidence_a.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => onSelect(id)}
                        className="bg-muted rounded px-1 font-mono"
                      >
                        {id}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="border-border rounded-md border p-2">
                  <p className="text-foreground text-sm font-medium">B</p>
                  <p className="text-sm">{c.claim_b}</p>
                  <div className="mt-1 flex flex-wrap gap-1 text-xs">
                    {c.evidence_b.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => onSelect(id)}
                        className="bg-muted rounded px-1 font-mono"
                      >
                        {id}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function PoolTab({
  bundle,
  onSelect,
}: {
  bundle: EvidenceContract;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {bundle.evidence_pool.map((s) => (
        <li key={s.evidence_id}>
          <button
            type="button"
            onClick={() => onSelect(s.evidence_id)}
            className="border-border hover:border-foreground w-full rounded-md border p-3 text-left text-sm transition"
          >
            <p className="text-muted-foreground font-mono text-xs">
              {s.evidence_id} · tier {s.source_tier}
            </p>
            <p className="text-foreground mt-1">
              {s.span_text.slice(0, 120)}
              {s.span_text.length > 120 ? "…" : ""}
            </p>
          </button>
        </li>
      ))}
    </ul>
  );
}

function EvidencePane({
  span,
  onClose,
}: {
  span: SourceSpan | null;
  onClose: () => void;
}) {
  if (!span) {
    return (
      <Card>
        <CardHeader>
          <CardDescription className="text-xs tracking-widest uppercase">
            Evidence
          </CardDescription>
          <CardTitle className="text-sm">Click a token to inspect</CardTitle>
        </CardHeader>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardDescription className="text-xs tracking-widest uppercase">
          {span.evidence_id} · tier {span.source_tier}
        </CardDescription>
        <CardTitle className="text-sm break-all">
          <a
            href={span.source_url}
            target="_blank"
            rel="noreferrer"
            className="underline-offset-4 hover:underline"
          >
            {span.source_url}
          </a>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground text-xs">
          chars {span.span_start}–{span.span_end}
        </p>
        <pre className="bg-muted text-foreground mt-2 overflow-x-auto rounded-md p-3 text-xs whitespace-pre-wrap">
          {span.span_text}
        </pre>
        <Button
          type="button"
          variant="ghost"
          onClick={onClose}
          className="mt-3"
        >
          Close
        </Button>
      </CardContent>
    </Card>
  );
}
