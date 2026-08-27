import { NextResponse } from "next/server";
import { searchSuggestions } from "@/lib/property-service";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.replace(/[<>]/g, "").trim().slice(0, 60) ?? "";
  if (query.length < 2) return NextResponse.json({ suggestions: [] });
  try {
    return NextResponse.json(
      { suggestions: await searchSuggestions(query) },
      { headers: { "Cache-Control": "private, max-age=60" } },
    );
  } catch {
    return NextResponse.json({ suggestions: [] }, { status: 503 });
  }
}

export const GET = withObservability("/api/properties/suggestions", handleGET);
