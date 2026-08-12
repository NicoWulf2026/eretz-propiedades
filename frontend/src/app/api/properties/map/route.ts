import { NextResponse } from "next/server";
import { parsePropertyFilters } from "@/lib/property-query";
import { searchMap } from "@/lib/property-service";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const filters = parsePropertyFilters(Object.fromEntries(url.searchParams.entries()));
  if (!filters.viewport) {
    return NextResponse.json({ error: "La zona del mapa no es válida." }, { status: 400 });
  }
  try {
    const result = await searchMap(filters, filters.viewport);
    return NextResponse.json(result, {
      headers: { "Cache-Control": "private, max-age=20, stale-while-revalidate=40" },
    });
  } catch {
    return NextResponse.json({ error: "No pudimos consultar esta zona." }, { status: 503 });
  }
}

