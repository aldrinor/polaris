// I-p2-031 (#770) — Source Review / Source-Set Health.
//
// Sits between Intake and Plan in the flow (intake → source_review → plan →
// run). Its job: surface, BEFORE the run, the curated source set POLARIS will
// search for the chosen template + the per-tier adequacy bar the corpus must
// clear — so scope can't be buried (Codex iter-1 P1-3 on the UX standard).
//
// LAW II — data source: `listTemplates()` → GET /api/v6/templates, served from
// the authoritative config/v6_templates/*.json (real T1/T2/T3 source domains +
// min_sources_per_tier). The endpoint is live (auth-gated; runs authenticated
// in-browser). This page does NOT fabricate a retrieved corpus or a "readiness
// %": the ACTUAL sources are retrieved + adequacy-checked during the run, and
// the page says so plainly. No pre-run retrieval preview is invoked (runRetrieval
// is not wired into the user flow).
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import { listTemplates, type TemplateContent } from "@/lib/api";

const TEMPLATE_IDS = [
  "clinical",
  "policy",
  "tech",
  "ai_sovereignty",
  "canada_us",
  "due_diligence",
  "custom",
  "workforce",
] as const;

function asTemplateId(value: string | null): string {
  return value && (TEMPLATE_IDS as readonly string[]).includes(value)
    ? value
    : "clinical";
}

const TIERS = ["T1", "T2", "T3"] as const;
type Tier = (typeof TIERS)[number];

const TIER_DOT: Record<Tier, string> = {
  T1: "bg-tier-1",
  T2: "bg-tier-2",
  T3: "bg-tier-3",
};

const TIER_LABEL: Record<Tier, string> = {
  T1: "Tier 1 — primary / regulatory",
  T2: "Tier 2 — peer-reviewed / guidelines",
  T3: "Tier 3 — reputable secondary",
};

function prettyDomain(url: string): string {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

function TierCard({
  tier,
  domains,
  minRequired,
}: {
  tier: Tier;
  domains: string[];
  minRequired: number;
}) {
  return (
    <div className="border-border bg-card flex flex-col gap-3 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className={`${TIER_DOT[tier]} inline-block h-2.5 w-2.5 rounded-full`}
          />
          <span className="text-foreground text-sm font-semibold">
            {TIER_LABEL[tier]}
          </span>
        </div>
        <span
          className={
            minRequired > 0
              ? "border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase"
              : "text-muted-foreground text-[10px] font-medium tracking-wide uppercase"
          }
        >
          {minRequired > 0 ? `min ${minRequired} required` : "no minimum"}
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {domains.map((d) => (
          <li
            key={d}
            className="text-muted-foreground font-mono text-xs break-all"
          >
            {prettyDomain(d)}
          </li>
        ))}
        {domains.length === 0 && (
          <li className="text-muted-foreground text-xs">
            No curated domains for this tier.
          </li>
        )}
      </ul>
    </div>
  );
}

function SourceReviewContent() {
  const searchParams = useSearchParams();
  const question = (searchParams.get("q") ?? "").trim();
  const templateId = asTemplateId(searchParams.get("template"));

  const [template, setTemplate] = useState<TemplateContent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listTemplates()
      .then((templates) => {
        if (cancelled) return;
        const match = templates.find((t) => t.template_id === templateId);
        if (match) {
          setTemplate(match);
        } else {
          setError(
            `No source-set definition found for the "${templateId}" template.`,
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(
            "We couldn't load the source set right now. Please retry shortly.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  const planHref = `/plan?q=${encodeURIComponent(question)}&template=${encodeURIComponent(templateId)}`;

  return (
    <section
      data-testid="source-review-page"
      className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10"
    >
      <div className="flex flex-col gap-2">
        <Link
          href={`/intake?q=${encodeURIComponent(question)}`}
          className="text-muted-foreground hover:text-foreground text-xs"
        >
          ← Edit question
        </Link>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          Review the source set
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
          What POLARIS will search for this question — and the per-tier adequacy
          bar the corpus must clear before a single claim is written.
        </p>
      </div>

      {question && (
        <div className="border-border bg-card flex flex-col gap-2 rounded-lg border p-4">
          <span className="text-muted-foreground text-[10px] font-medium tracking-widest uppercase">
            Your question
          </span>
          <p className="text-foreground text-base">{question}</p>
          <span className="text-muted-foreground text-xs">
            Template:{" "}
            <span className="text-foreground font-medium">{templateId}</span>
          </span>
        </div>
      )}

      {error && (
        <ErrorState title="Couldn't load the source set" message={error} />
      )}

      {!template && !error && (
        <LoadingState label="Loading the source set…" rows={5} />
      )}

      {template && (
        <>
          <div className="flex flex-col gap-3">
            <h2 className="text-foreground text-sm font-semibold">
              Source tiers POLARIS will search
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {TIERS.map((tier) => (
                <TierCard
                  key={tier}
                  tier={tier}
                  domains={template.source_tiers[tier] ?? []}
                  minRequired={template.min_sources_per_tier[tier] ?? 0}
                />
              ))}
            </div>
          </div>

          {template.frame_manifest.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="text-foreground text-sm font-semibold">
                What the brief will cover
              </h2>
              <div className="flex flex-wrap gap-2">
                {template.frame_manifest.map((frame) => (
                  <span
                    key={frame.frame_id}
                    className="border-border text-muted-foreground rounded-full border px-2.5 py-1 text-xs"
                  >
                    {frame.frame_name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* HONEST framing — the page shows the curated source DEFINITION + the
              adequacy bar, NOT a retrieved corpus. Retrieval happens in the run. */}
          <div className="border-border bg-muted/40 flex flex-col gap-1 rounded-lg border p-4">
            <span className="text-foreground text-xs font-semibold">
              How sources are gathered
            </span>
            <p className="text-muted-foreground text-xs">
              These are the curated source domains and per-tier minimums for the{" "}
              <span className="text-foreground font-medium">
                {template.template_name}
              </span>{" "}
              template. POLARIS retrieves the actual corpus during the run and{" "}
              <span className="text-foreground">
                aborts at the adequacy gate
              </span>{" "}
              if any tier falls below its minimum — so scope is enforced, not
              assumed.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button
              nativeButton={false}
              render={<Link href={planHref} />}
              disabled={!question}
            >
              Continue to plan review →
            </Button>
            {!question && (
              <span className="text-muted-foreground text-xs">
                Start from a question on{" "}
                <Link className="text-primary underline" href="/intake">
                  Intake
                </Link>
                .
              </span>
            )}
          </div>
        </>
      )}
    </section>
  );
}

export default function SourceReviewPage() {
  return (
    <Suspense fallback={null}>
      <SourceReviewContent />
    </Suspense>
  );
}
