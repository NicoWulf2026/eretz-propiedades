import { NextResponse } from "next/server";
import { searchDiscoverySuggestions } from "@/lib/discovery-service";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.replace(/[<>]/g, "").trim().slice(0, 60) ?? "";
  const result = await searchDiscoverySuggestions(query, { signal: request.signal });
  if (result.status === "FAILURE") {
    const status = result.error.kind === "TIMEOUT" ? 504
      : result.error.kind === "BAD_REQUEST" ? 400
        : result.error.kind === "SERVER_ERROR" ? 502
          : 503;
    return NextResponse.json(result, { status, headers: { "Cache-Control": "no-store" } });
  }
  return NextResponse.json(result, { headers: { "Cache-Control": "private, max-age=60" } });
}

export const GET = withObservability("/api/properties/suggestions", handleGET);
