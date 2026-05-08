"use client";

import type { VerifiedReport } from "@/lib/api";

import { VerifiedReportView } from "./verified_report_view";

// I-f11-002: Append-to-existing-report rendering. Renders the original
// verified report, a labeled separator, then the appended (follow-up)
// verified report. Production wiring (graph_v4 generating the appended
// report from FollowUpAgent.compose) is follow-up I-f11-002b.

export function FollowUpAppendView({
  original,
  appended,
}: {
  original: VerifiedReport;
  appended: VerifiedReport;
}) {
  return (
    <div>
      <VerifiedReportView report={original} />
      <div data-testid="follow-up-separator" className="my-6">
        <hr className="border-border" />
        <p
          data-testid="follow-up-separator-caption"
          className="text-muted-foreground mt-2 text-center text-xs tracking-widest uppercase"
        >
          Follow-up appended below
        </p>
        <hr className="border-border mt-2" />
      </div>
      <VerifiedReportView report={appended} />
    </div>
  );
}
