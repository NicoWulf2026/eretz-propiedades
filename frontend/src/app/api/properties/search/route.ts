import { NextResponse } from "next/server";
import { parsePropertyFilters } from "@/lib/property-query";
import { searchProperties } from "@/lib/property-service";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
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
