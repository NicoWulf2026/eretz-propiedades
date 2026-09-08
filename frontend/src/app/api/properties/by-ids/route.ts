import { NextResponse } from "next/server";
import { getPropertiesByIds } from "@/lib/property-service";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

// Resúmenes frescos para las listas locales (favoritos, comparar, recientes).
// Sólo devuelve propiedades autorizadas por el Quality Gate; capado en el servicio.
async function handleGET(request: Request) {
  const url = new URL(request.url);
  const raw = (url.searchParams.get("ids") ?? "").split(",").map((x) => x.trim()).filter(Boolean);
  const result = await getPropertiesByIds(raw);
  if (result.failed) {
    return NextResponse.json(
      { error: "No pudimos cargar las propiedades." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
  return NextResponse.json(
    { properties: result.properties },
    { headers: { "Cache-Control": "private, max-age=30, stale-while-revalidate=60" } },
  );
}

export const GET = withObservability("/api/properties/by-ids", handleGET);
