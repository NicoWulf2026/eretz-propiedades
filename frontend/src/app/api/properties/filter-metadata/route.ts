import { NextResponse } from "next/server";
import { loadDiscoveryFilterMetadata } from "@/lib/discovery-service";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const result = await loadDiscoveryFilterMetadata({ signal: request.signal });
  if (result.status === "FAILURE") {
    const status = result.error.kind === "TIMEOUT" ? 504
      : result.error.kind === "SERVER_ERROR" ? 502
        : 503;
    return NextResponse.json(result, { status, headers: { "Cache-Control": "no-store" } });
  }
  return NextResponse.json(result, { headers: { "Cache-Control": "private, max-age=300" } });
}

export const GET = withObservability("/api/properties/filter-metadata", handleGET);
