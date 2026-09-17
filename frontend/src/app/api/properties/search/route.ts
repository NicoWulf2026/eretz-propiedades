import { NextResponse } from "next/server";
import { parsePropertyFilters, urlSearchParamsToSearchParams } from "@/lib/property-query";
import { searchApiV2ForExplorer, validateApiV2ExplorerParams } from "@/lib/api-v2/property-boundary";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const url = new URL(request.url);
  const filters = parsePropertyFilters(urlSearchParamsToSearchParams(url.searchParams));
  const invalid = validateApiV2ExplorerParams(url.searchParams);
  if (invalid) {
    return NextResponse.json({ error: invalid, errorKind: "BAD_REQUEST" }, { status: 400, headers: { "Cache-Control": "no-store" } });
  }
  try {
    const outcome = await searchApiV2ForExplorer(filters);
    if (outcome.failure || !outcome.result) {
      const status = outcome.failure?.kind === "BAD_REQUEST" ? 400 : outcome.failure?.kind === "NOT_FOUND" ? 404 : 503;
      return NextResponse.json({ error: outcome.failure?.message ?? "No pudimos consultar las propiedades.", errorKind: outcome.failure?.kind ?? "SERVER_ERROR" }, { status, headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.json({ ...outcome.result, searchWindowExhausted: outcome.windowExhausted }, {
      headers: { "Cache-Control": "private, max-age=20, stale-while-revalidate=40" },
    });
  } catch {
    return NextResponse.json({ error: "No pudimos consultar las propiedades." }, { status: 503 });
  }
}

export const GET = withObservability("/api/properties/search", handleGET);
