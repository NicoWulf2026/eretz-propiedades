import { NextResponse } from "next/server";
import { parsePropertyFilters, urlSearchParamsToSearchParams } from "@/lib/property-query";
import { searchApiV2ForExplorer } from "@/lib/api-v2/property-boundary";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const url = new URL(request.url);
  const filters = parsePropertyFilters(urlSearchParamsToSearchParams(url.searchParams));
  try {
    // Use a single page search to get the count data (counts are cached separately)
    // The search service returns count, totalCount, mapCount without loading all results
    const outcome = await searchApiV2ForExplorer({ ...filters, cursor: "", page: 1 });
    if (outcome.failure || !outcome.result) {
      return NextResponse.json(
        { error: "No pudimos obtener los conteos." },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      {
        totalCount: outcome.result.totalCount,
        count: outcome.result.count,
        mapCount: null,
        withoutMapCount: null,
      },
      { headers: { "Cache-Control": "private, max-age=60, stale-while-revalidate=120" } },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos obtener los conteos." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export const GET = withObservability("/api/properties/counts", handleGET);
