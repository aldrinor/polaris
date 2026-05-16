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
import { EvidenceTooltip } from "@/components/ui/evidence-tooltip";
import { VegaChart } from "@/components/ui/vega-chart";
import {
  downloadBundleAsJson,
  downloadBundleTarball,
  getBundle,
  getChart,
  type ChartType,
  type EvidenceContract,
  type SourceSpan,
  type VegaLiteSpec,
} from "@/lib/api";

interface InspectorPageProps {
  params: Promise<{ runId: string }>;
}

export default function InspectorPage({ params }: InspectorPageProps) {
  const { runId } = use(params);
  const [bundle, setBundle] = useState<EvidenceContract | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<SourceSpan | null>(
    null,
  );
  const [activeTab, setActiveTab] = useState<
    "summary" | "sentences" | "frames" | "contradictions" | "pool" | "charts"
  >("summary");

  useEffect(() => {
    let cancelled = false;
    getBundle(runId)
      .then((b) => {
        if (!cancelled) setBundle(b);
      })
      .catch((err) => {
        if (cancelled) return;
        // I-rdy-014 (#510): a freshly-created run has no published bundle
        // yet (404). That is a pending state, not an error — render an
        // honest "report not ready" panel, never a crash or a dead end.
        const status = (err as { status?: number })?.status;
        if (status === 404) {
          setNotReady(true);
        } else {
          setError(err instanceof Error ? err.message : "Bundle load failed");
        }
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
          id: "summary",
          label: "Executive summary",
          count: 3,
        },
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
        {
          id: "charts",
          label: "Charts",
          count: 3,
        },
      ]
    : [];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Inspector
            </span>
            <span className="text-foreground text-base font-semibold">
              Run {runId}
            </span>
          </div>
          {bundle && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    await downloadBundleTarball(runId);
                  } catch (err) {
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Signed bundle not available yet",
                    );
                  }
                }}
              >
                Download signed bundle
              </Button>
              <Button
                variant="outline"
                onClick={() => downloadBundleAsJson(bundle)}
              >
                Export bundle JSON
              </Button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
        {error && (
          <section role="alert" aria-labelledby="inspector-error-heading">
            <h1
              id="inspector-error-heading"
              className="text-foreground text-2xl font-semibold tracking-tight"
            >
              Bundle load failed
            </h1>
            <p className="border-destructive/60 text-foreground mt-2 rounded-md border p-3 text-sm font-medium">
              {error}
            </p>
          </section>
        )}

        {notReady && (
          <section role="status" aria-labelledby="inspector-pending-heading">
            <h1
              id="inspector-pending-heading"
              className="text-foreground text-2xl font-semibold tracking-tight"
            >
              Report not yet available
            </h1>
            <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
              Run <span className="font-mono">{runId}</span> has no published
              evidence bundle yet — the verifier pipeline is still running, or
              this run predates bundle capture. The integrated report and
              signed bundle appear here once the run completes.
            </p>
            <Link
              href={`/runs/${runId}`}
              className="text-foreground mt-3 inline-block text-sm font-semibold underline underline-offset-4"
            >
              ← Back to the live run
            </Link>
          </section>
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
                    : "border-destructive/60"
                }
              >
                <CardHeader>
                  <CardDescription className="text-foreground text-xs font-semibold tracking-widest uppercase">
                    Two-family invariant
                  </CardDescription>
                  <CardTitle className="text-sm">
                    {bundle.family_segregation_passed ? "PASS" : "FAIL"} ·{" "}
                    {bundle.generator_model} → {bundle.verifier_model}
                  </CardTitle>
                </CardHeader>
                {!bundle.family_segregation_passed && (
                  <CardContent className="text-foreground text-sm font-medium">
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
                  className={`min-h-[44px] border-b-2 px-3 py-2.5 text-sm transition ${
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
                {activeTab === "summary" && (
                  <ExecutiveSummaryTab
                    runId={runId}
                    bundle={bundle}
                    onSelect={(id) => setSelectedEvidence(evidenceById(id))}
                  />
                )}
                {activeTab === "sentences" && (
                  <SentencesTab
                    bundle={bundle}
                    evidenceById={evidenceById}
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
                {activeTab === "charts" && (
                  <ChartsTab
                    runId={runId}
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
  evidenceById,
  onSelect,
  onJumpToContradictions,
}: {
  bundle: EvidenceContract;
  evidenceById: (id: string) => SourceSpan | null;
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
                    className="ml-2 inline-flex min-h-[24px] items-center rounded bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-900 normal-case hover:bg-yellow-200"
                  >
                    contradiction in section →
                  </button>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm">
                {renderSentenceWithTokens(
                  s.sentence_text,
                  onSelect,
                  evidenceById,
                )}
              </p>
              {s.drop_reason && (
                <p className="text-foreground mt-2 text-xs font-medium">
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
  evidenceById?: (id: string) => SourceSpan | null,
): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const re = /\[#ev:([^:\]]+):\d+-\d+\]/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const evidenceId = match[1];
    const span = evidenceById?.(evidenceId);
    parts.push(
      <EvidenceTooltip
        key={`${match.index}-${evidenceId}`}
        evidenceId={evidenceId}
        sourceUrl={span?.source_url}
        spanText={span?.span_text}
        sourceTier={span?.source_tier}
        onClickToInspect={() => onSelect(evidenceId)}
      >
        {match[0]}
      </EvidenceTooltip>,
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

function ExecutiveSummaryTab({
  runId,
  bundle,
  onSelect,
}: {
  runId: string;
  bundle: EvidenceContract;
  onSelect: (id: string) => void;
}) {
  /**
   * F10c executive-summary infographic — composes all 3 chart types
   * (forest_plot + comparison_table + timeline) into a single page-
   * level briefing view, anchored by the run question + key counts.
   */
  const chartTypes: ChartType[] = [
    "forest_plot",
    "comparison_table",
    "timeline",
  ];
  const [specs, setSpecs] = useState<Record<ChartType, VegaLiteSpec | null>>({
    forest_plot: null,
    comparison_table: null,
    timeline: null,
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all(chartTypes.map((t) => getChart(runId, t).catch(() => null)))
      .then((results) => {
        if (cancelled) return;
        setSpecs({
          forest_plot: results[0],
          comparison_table: results[1],
          timeline: results[2],
        });
      })
      .catch(() => {
        if (!cancelled) {
          setSpecs({
            forest_plot: null,
            comparison_table: null,
            timeline: null,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const verifiedCount = bundle.verified_sentences.length;
  const droppedCount = bundle.verified_sentences.filter(
    (s) => s.drop_reason,
  ).length;
  const contradictionCount = bundle.contradictions.length;
  const tierCounts = bundle.evidence_pool.reduce<Record<string, number>>(
    (acc, span) => {
      acc[span.source_tier] = (acc[span.source_tier] ?? 0) + 1;
      return acc;
    },
    {},
  );

  return (
    <div className="flex flex-col gap-4">
      <Card className="border-foreground/30 bg-muted/20">
        <CardHeader>
          <CardDescription className="text-xs tracking-widest uppercase">
            Executive briefing — at a glance
          </CardDescription>
          <CardTitle className="text-base">{bundle.template} run</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-foreground text-sm">{bundle.question}</p>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <div>
              <p className="text-muted-foreground text-xs uppercase">
                Verified
              </p>
              <p className="text-foreground text-xl font-semibold">
                {verifiedCount}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase">Dropped</p>
              <p className="text-foreground text-xl font-semibold">
                {droppedCount}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase">
                Contradictions
              </p>
              <p className="text-foreground text-xl font-semibold">
                {contradictionCount}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase">Sources</p>
              <p className="text-foreground text-xl font-semibold">
                {bundle.evidence_pool.length}
                <span className="text-muted-foreground ml-2 text-xs font-normal">
                  T1:{tierCounts.T1 ?? 0} · T2:{tierCounts.T2 ?? 0} · T3:
                  {tierCounts.T3 ?? 0}
                </span>
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {chartTypes.map((t) => {
        const spec = specs[t];
        if (!spec) {
          return (
            <Card key={t}>
              <CardHeader>
                <CardDescription className="text-xs tracking-widest uppercase">
                  {t.replace("_", " ")}
                </CardDescription>
                <CardTitle className="text-sm">Loading…</CardTitle>
              </CardHeader>
            </Card>
          );
        }
        return (
          <Card key={t}>
            <CardHeader>
              <CardDescription className="text-xs tracking-widest uppercase">
                {t.replace("_", " ")} ·{" "}
                {spec.polaris_provenance.evidence_ids.length} evidence ids
              </CardDescription>
              <CardTitle className="text-sm">
                {(spec.title as string) ?? "Chart"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <VegaChart
                spec={spec}
                onPointClick={(datum) => {
                  const evidenceId = datum.evidence_id;
                  if (typeof evidenceId === "string") onSelect(evidenceId);
                }}
              />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function ChartsTab({
  runId,
  onSelect,
}: {
  runId: string;
  onSelect: (id: string) => void;
}) {
  const [chartType, setChartType] = useState<ChartType>("forest_plot");
  const [spec, setSpec] = useState<VegaLiteSpec | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getChart(runId, chartType)
      .then((s) => {
        if (!cancelled) {
          setSpec(s);
          setChartError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setSpec(null);
          setChartError(
            err instanceof Error ? err.message : "Chart load failed",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, chartType]);

  const types: ChartType[] = ["forest_plot", "comparison_table", "timeline"];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {types.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setChartType(t)}
            className={`min-h-[28px] rounded-md border px-3 py-2 text-xs transition ${
              chartType === t
                ? "border-foreground bg-foreground text-background"
                : "border-border hover:border-foreground"
            }`}
          >
            {t.replace("_", " ")}
          </button>
        ))}
      </div>
      {chartError && (
        <p
          role="alert"
          className="border-destructive/60 text-foreground rounded-md border p-3 text-sm font-medium"
        >
          {chartError}
        </p>
      )}
      {spec && (
        <Card>
          <CardHeader>
            <CardDescription className="text-xs tracking-widest uppercase">
              {spec.polaris_provenance.chart_type} ·{" "}
              {spec.polaris_provenance.evidence_ids.length} evidence ids
            </CardDescription>
            <CardTitle className="text-base">
              {(spec.title as string) ?? "Chart"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <VegaChart
              spec={spec}
              onPointClick={(datum) => {
                const evidenceId = datum.evidence_id;
                if (typeof evidenceId === "string") onSelect(evidenceId);
              }}
            />
            <details className="mt-4">
              <summary className="text-muted-foreground cursor-pointer text-xs">
                View raw Vega-Lite spec (
                {spec.polaris_provenance.evidence_ids.length} evidence ids)
              </summary>
              <div className="mt-2 mb-3 flex flex-wrap gap-1">
                {spec.polaris_provenance.evidence_ids
                  .slice(0, 12)
                  .map((eid) => (
                    <button
                      key={eid}
                      type="button"
                      onClick={() => onSelect(eid)}
                      className="bg-muted hover:bg-foreground hover:text-background rounded px-1.5 py-0.5 font-mono text-[11px]"
                    >
                      {eid}
                    </button>
                  ))}
              </div>
              <pre className="bg-muted text-muted-foreground max-h-96 overflow-auto rounded-md p-3 text-[11px]">
                {JSON.stringify(spec, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}
    </div>
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
