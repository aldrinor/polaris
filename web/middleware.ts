// I-cd-015 (GH#611) — exclude test-harness routes from the production build.
//
// Listed routes (/charts_test/*, /sentence_hover_test/*,
// /disambiguation_modal_preview/*, /generation/*, /retrieval/*, /sse/*)
// are dev-only harness surfaces. In production deployments they must
// return 404 so reviewers + Carney's office don't reach internal test
// pages.
//
// Override: `POLARIS_TEST_HARNESS_ENABLED=1` keeps harness routes
// reachable (CI workflow `.github/workflows/web_ci.yml` runs
// `evidence_tooltip_perf.spec.ts` against `next start` in prod mode
// and needs `/sentence_hover_test/perf` to work). Real production
// deployment leaves this UNSET.
import { NextResponse } from "next/server";

export function middleware() {
  const isProd = process.env.NODE_ENV === "production";
  const harnessAllowed = process.env.POLARIS_TEST_HARNESS_ENABLED === "1";
  if (isProd && !harnessAllowed) {
    return new NextResponse(null, {
      status: 404,
      headers: { "x-harness-blocked": "1" },
    });
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/charts_test",
    "/charts_test/:path*",
    "/sentence_hover_test",
    "/sentence_hover_test/:path*",
    "/disambiguation_modal_preview",
    "/disambiguation_modal_preview/:path*",
    "/generation",
    "/generation/:path*",
    "/retrieval",
    "/retrieval/:path*",
    "/sse",
    "/sse/:path*",
  ],
};
