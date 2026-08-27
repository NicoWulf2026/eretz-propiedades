import { NextResponse } from "next/server";
import { parsePropertyFilters } from "@/lib/property-query";
import { searchProperties } from "@/lib/property-service";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const url = new URL(request.url);
  const filters = parsePropertyFilters(Object.fromEntries(url.searchParams.entries()));
  try {
    const result = await searchProperties(filters);
    return NextResponse.json(result, {
      headers: { "Cache-Control": "private, max-age=20, stale-while-revalidate=40" },
    });
  } catch {
    return NextResponse.json({ error: "No pudimos consultar las propiedades." }, { status: 503 });
  }
}

export const GET = withObservability("/api/properties/search", handleGET);
