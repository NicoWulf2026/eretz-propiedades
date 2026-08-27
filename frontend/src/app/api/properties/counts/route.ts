import { NextResponse } from "next/server";
import { parsePropertyFilters } from "@/lib/property-query";
import { searchProperties } from "@/lib/property-service";
import { getPreviewQualityGate } from "@/lib/preview-quality-gate";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const url = new URL(request.url);
  const filters = parsePropertyFilters(Object.fromEntries(url.searchParams.entries()));
  try {
    // Use a single page search to get the count data (counts are cached separately)
    // The search service returns count, totalCount, mapCount without loading all results
    const [result, gate] = await Promise.all([
      searchProperties({ ...filters, cursor: "", page: 1 }),
      getPreviewQualityGate(),
    ]);
    return NextResponse.json(
      {
        totalCount: gate.visibleCount,
        count: result.count,
        mapCount: result.mapCount,
        withoutMapCount: result.count !== null && result.mapCount !== null
          ? Math.max(0, result.count - result.mapCount)
          : null,
      },
      { headers: { "Cache-Control": "private, max-age=60, stale-while-revalidate=120" } },
    );
  } catch {
    return NextResponse.json({ error: "No pudimos obtener los conteos." }, { status: 503 });
  }
}

export const GET = withObservability("/api/properties/counts", handleGET);
