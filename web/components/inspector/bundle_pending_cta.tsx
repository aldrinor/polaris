// I-cd-013a (GH#609) — CTA for unknown runIds.
// User-facing copy is G2-clean (no dev language); issue IDs live in
// source comments and test-IDs only.
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface BundlePendingCtaProps {
  runId: string;
}

export function BundlePendingCta({ runId }: BundlePendingCtaProps) {
  return (
    <main
      className="mx-auto flex min-h-[60vh] max-w-2xl items-center justify-center p-6"
      data-testid="bundle-pending-cta"
    >
      <Card className="w-full">
        <CardHeader>
          <CardTitle>This run isn&rsquo;t ready for inspection yet</CardTitle>
          <CardDescription>
            Signed audit bundles appear here once a run completes. Live runs and
            in-progress state are on the Runs page.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="border-border bg-muted/40 rounded-md border p-3">
            <p className="text-muted-foreground text-sm font-medium">
              Run identifier
            </p>
            <p className="font-mono text-sm" data-testid="cta-run-id">
              {runId}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/runs/${runId}`} className={buttonVariants()}>
              Open in Runs
            </Link>
            <Link
              href="/dashboard"
              className={buttonVariants({ variant: "outline" })}
            >
              Back to dashboard
            </Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
