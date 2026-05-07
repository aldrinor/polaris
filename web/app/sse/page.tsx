import { Suspense } from "react";

import { SSEHarness } from "./_harness";

export default function SSETestHarnessPage() {
  return (
    <Suspense fallback={<div>loading…</div>}>
      <SSEHarness />
    </Suspense>
  );
}
