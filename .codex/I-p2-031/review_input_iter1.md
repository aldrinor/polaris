# Codex DESIGN+DIFF review — I-p2-031 (#770): Source Review / Source-Set Health

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `f0a48d8c7fe71637a034b083c5ff84dd3d45bc4006956fca2e1795c586211588`. web/ only, 2 files. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## 200-LOC cap exemption (please validate)
~304 patch lines; ~280 are the single new file `web/app/source_review/page.tsx` (one atomic new page), the rest a small intake-link rewire. Consistent with prior Phase-2 page builds (#759, #761). If you judge the size a real review risk, say so.

## Context
#770 = "Source Review / Source-Set Health", a NEW flow step BETWEEN intake and plan (intake → source_review → plan → run). Per the UX-standard Codex finding (P1-3): the winning flow is intake → review/approve sources → plan → run; add an explicit source-set-health state "so scope can't be buried." This page surfaces, BEFORE the run, the curated source set POLARIS will search for the chosen template + the per-tier adequacy bar the corpus must clear.

## Data source (LAW II — VERIFIED-live, not assumed)
`listTemplates()` → `GET /api/v6/templates`, served from the authoritative `config/v6_templates/*.json`. I VERIFIED this is real before building:
- `curl https://polarisresearch.ca/api/v6/templates` → `401 {"error":"missing_bearer_token"}` (a real auth-gated endpoint — a 404 would mean it doesn't exist). It runs authenticated in-browser (the page is behind auth).
- Read `config/v6_templates/clinical.json` directly: real `source_tiers` (T1: Health Canada, FDA, EMA, ClinicalTrials.gov, PubMed; T2: Cochrane, BMJ, JAMA, Lancet; T3: Medscape, StatNews) + real `min_sources_per_tier` {T1:3, T2:2, T3:0} + 5 frames. NO fabrication.

**Deliberately NOT used (would risk LAW II):** `runRetrieval` (a real pre-run corpus preview) is used by NO production page — only the dev `/retrieval` harness — and triggers actual retrieval (cost/heavy); `getAuditRun` (post-run gates) is frontend-unused + unverifiable offline (same call I deferred on #759). So the page shows the source-set DEFINITION + the adequacy bar, NOT a retrieved corpus.

## Honesty (LAW II)
The page does NOT fabricate a retrieved corpus, a "readiness %", or "estimated N sources". It states plainly (the "How sources are gathered" callout): the actual corpus is retrieved + adequacy-checked DURING the run, which aborts at the adequacy gate if any tier falls below its minimum — "scope is enforced, not assumed."

## Diff (2 files)
1. `web/app/source_review/page.tsx` (NEW): in-shell page (snake_case route folder, matches /pin_replay /audit_live). Suspense + useSearchParams (q + template; template defaults to "clinical" via the same allow-list as plan). On mount: `listTemplates()` → find the chosen template → render. Sections: question display, per-tier cards (T1 = Canada-red `bg-tier-1` dot, T2/T3 neutral; domains + min-required badge), frame-manifest chips, honest "how sources are gathered" callout, "Continue to plan review →" → `/plan?q=&template=`. #750 LoadingState/ErrorState for the fetch (offline harness → ErrorState; verified-content screenshot taken with a page.route intercept serving the REAL config json).
2. `web/app/intake/components/intake_form.tsx`: the in-scope continue link rewired from `/plan?q=` → `/source_review?q=` ("Review sources →"), inserting the new step. testid `intake-continue-to-plan` kept.

## Files I have ALSO checked and they're clean
- `grep` for `intake-continue-to-plan` / "Continue to plan" / `/source_review` / `source-review-page` across tests + scripts: NO staled consumer (no test asserts the old link text/href).
- `listTemplates` + `TemplateContent` (source_tiers, min_sources_per_tier, frame_manifest) field names exact (api.ts:395-411).
- Tier tokens `bg-tier-1`(#c8102e Canada-red)/`bg-tier-2`/`bg-tier-3` confirmed in globals.css.
- `/source_review` correctly NOT in PRIMARY_NAV (nav.ts) — it's a flow step like `/plan`, not top-nav. In-shell (not in app_shell_gate CHROMELESS).

## Claude visual audit (standalone @1366, REAL config data via page.route intercept)
In-shell (POLARIS·Canada nav + Canadian-hosted badge). Renders: "Review the source set" + the question + Template: clinical; three tier cards with the REAL domains (Health Canada/FDA/EMA/ClinicalTrials.gov/PubMed · Cochrane/BMJ/JAMA/Lancet · Medscape/StatNews) + MIN 3/MIN 2/NO MINIMUM badges; frame chips (Efficacy outcomes, Safety/adverse events, Regulatory labelling deltas, Post-market surveillance, Subgroup analyses); honest "how sources are gathered" callout; red "Continue to plan review →" CTA.

## Review focus (16-dim design rubric + diff)
1. Honesty: does the page avoid implying a corpus has been retrieved? Is the "definition + adequacy bar, retrieved during run" framing unambiguous?
2. LAW II: is building on `listTemplates` (verified-live endpoint + real config) defensible, given runRetrieval/getAuditRun were correctly deferred?
3. Flow: intake → source_review → plan wired cleanly (params preserved; no staled test)?
4. Design dims: hierarchy, the tier-card density, token use (tier-1 = national red OK here as a tier signal?), a11y (tier dots aria-hidden + text labels; in-shell single landmark), responsive (3-col → 1-col).
5. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```

===== FULL NEW FILE: web/app/source_review/page.tsx =====
```tsx
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
```

===== intake_form rewire (diff) =====
```diff
diff --git a/web/app/intake/components/intake_form.tsx b/web/app/intake/components/intake_form.tsx
index 4e7e0c37..d821baea 100644
--- a/web/app/intake/components/intake_form.tsx
+++ b/web/app/intake/components/intake_form.tsx
@@ -180,12 +180,16 @@ export function IntakeForm() {
               page, which is the run-start surface. */}
           {state.decision.status === "in_scope" ? (
             <div className="flex justify-end">
+              {/* I-p2-031 (#770): route through source-review (see the source
+                  set + adequacy bar) before the plan/run-start surface. */}
               <Button
                 nativeButton={false}
                 data-testid="intake-continue-to-plan"
                 render={
-                  <Link href={`/plan?q=${encodeURIComponent(question.trim())}`}>
-                    Continue to plan →
+                  <Link
+                    href={`/source_review?q=${encodeURIComponent(question.trim())}`}
+                  >
+                    Review sources →
                   </Link>
                 }
               />
```

===== REAL config the endpoint serves (clinical.json source_tiers/min) =====
```json
{
 "template_id": "clinical",
 "template_name": "Clinical drug audit",
 "source_tiers": {
  "T1": [
   "https://www.canada.ca/en/health-canada.html",
   "https://www.fda.gov/drugs",
   "https://www.ema.europa.eu",
   "https://clinicaltrials.gov",
   "https://pubmed.ncbi.nlm.nih.gov"
  ],
  "T2": [
   "https://www.cochranelibrary.com",
   "https://www.bmj.com",
   "https://jamanetwork.com",
   "https://www.thelancet.com"
  ],
  "T3": [
   "https://www.medscape.com",
   "https://www.statnews.com"
  ]
 },
 "min_sources_per_tier": {
  "T1": 3,
  "T2": 2,
  "T3": 0
 }
}
```
