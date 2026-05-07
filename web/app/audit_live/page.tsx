import { Suspense } from "react";

import { LiveAuditPanels } from "./_panels";

export default function AuditLivePage() {
  return (
    <Suspense fallback={<div>loading…</div>}>
      <LiveAuditPanels />
    </Suspense>
  );
}
