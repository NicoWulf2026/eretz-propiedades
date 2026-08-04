import { NextResponse } from "next/server";
import { searchSuggestions } from "@/lib/property-service";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
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

