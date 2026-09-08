import { NextResponse } from "next/server";
import { parsePropertyFilters, urlSearchParamsToSearchParams } from "@/lib/property-query";
import { searchApiV2MapForExplorer, validateApiV2ExplorerParams } from "@/lib/api-v2/property-boundary";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const url = new URL(request.url);
  const invalid = validateApiV2ExplorerParams(url.searchParams);
  if (invalid) return NextResponse.json({ error: invalid, errorKind: "BAD_REQUEST" }, { status: 400, headers: { "Cache-Control": "no-store" } });
  const filters = parsePropertyFilters(urlSearchParamsToSearchParams(url.searchParams));
  if (!filters.viewport) {
    return NextResponse.json({ error: "La zona del mapa no es válida." }, { status: 400 });
  }
  try {
    const outcome = await searchApiV2MapForExplorer(filters, filters.viewport);
    if (outcome.failure || !outcome.result) {
      const status = outcome.failure?.kind === "BAD_REQUEST" ? 400 : 503;
      return NextResponse.json({ error: outcome.failure?.message ?? "No pudimos consultar esta zona.", errorKind: outcome.failure?.kind ?? "SERVER_ERROR" }, { status, headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.json(outcome.result, {
      headers: { "Cache-Control": "private, max-age=20, stale-while-revalidate=40" },
    });
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar esta zona." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export const GET = withObservability("/api/properties/map", handleGET);
