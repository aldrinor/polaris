// I-cd-013a (GH#609) — stub bundle API.
// Same loader the page uses; the no-op-replaceable seam I-B-09 will swap
// when implementing offline (no-backend) fallback.
import { NextResponse } from "next/server";

import { loadBundle } from "@/lib/inspector_bundle_loader";

interface RouteContext {
  params: Promise<{ runId: string }>;
}

export async function GET(_request: Request, ctx: RouteContext) {
  const { runId } = await ctx.params;
  const bundle = await loadBundle(runId);
  if (bundle === null) {
    return NextResponse.json(
      { error: "bundle_not_found", runId },
      { status: 404 },
    );
  }
  return NextResponse.json(bundle, { status: 200 });
}
