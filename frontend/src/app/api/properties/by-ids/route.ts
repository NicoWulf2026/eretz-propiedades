import { NextResponse } from "next/server";
import { getPropertiesByIds } from "@/lib/property-service";
import { getApiV2PropertiesBatch } from "@/lib/api-v2/client";
import { catalogPropertyToSummary } from "@/lib/api-v2/property-boundary";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

// Resúmenes frescos para las listas locales (favoritos, comparar, recientes).
// Sólo devuelve propiedades autorizadas por el Quality Gate; capado en el servicio.
async function handleGET(request: Request) {
  const url = new URL(request.url);
  const raw = Array.from(new Set((url.searchParams.get("ids") ?? "").split(",").map((x) => x.trim()).filter(Boolean))).slice(0, 100);
  const legacyIds = raw.filter((id) => /^\d+$/.test(id));
  const canonicalIds = raw.filter((id) => !/^\d+$/.test(id));
  const [legacy, catalog] = await Promise.all([
    getPropertiesByIds(legacyIds),
    canonicalIds.length ? getApiV2PropertiesBatch(canonicalIds) : Promise.resolve({ status: "SUCCESS_EMPTY" as const, data: { items: [], missingIds: [], requestedIds: [] } }),
  ]);
  const legacyUnavailable = legacy.failed && legacyIds.length > 0;
  const catalogUnavailable = catalog.status === "FAILURE" && canonicalIds.length > 0;
  if ((legacyUnavailable && canonicalIds.length === 0) || (catalogUnavailable && legacyIds.length === 0) || (legacyUnavailable && catalogUnavailable)) {
    return NextResponse.json(
      { error: "No pudimos cargar las propiedades." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
  const catalogProperties = catalog.status === "FAILURE" ? [] : catalog.data.items;
  const byId = new Map([
    ...legacy.properties.map((property) => [property.id, property] as const),
    ...catalogProperties.map((property) => [property.id, catalogPropertyToSummary(property)] as const),
  ]);
  const properties = raw.flatMap((id) => byId.get(id) ? [byId.get(id)!] : []);
  const missingIds = raw.filter((id) => !byId.has(id));
  return NextResponse.json(
    {
      properties,
      missingIds,
      status: missingIds.length ? "PARTIAL_DATA" : properties.length ? "SUCCESS" : "SUCCESS_EMPTY",
      issues: [
        ...(legacyUnavailable ? [{ source: "legacy", ids: legacyIds, kind: "UNAVAILABLE" }] : []),
        ...(catalogUnavailable ? [{ source: "api_v2", ids: canonicalIds, kind: "UNAVAILABLE" }] : []),
      ],
    },
    { headers: { "Cache-Control": "private, max-age=30, stale-while-revalidate=60" } },
  );
}

export const GET = withObservability("/api/properties/by-ids", handleGET);
