import type { MapSearchResponse, MapViewport } from "@/types/property";

type MapPoint = MapSearchResponse["points"][number];

/**
 * At detailed zoom the map endpoint may be capped independently from the
 * paginated rail. Keep every located card in the viewport addressable on the
 * map without duplicating markers or mixing individual pins into clusters.
 */
export function mergeDetailedPagePoints(
  mapPoints: MapPoint[],
  pagePoints: MapPoint[],
  viewport: MapViewport,
): MapPoint[] {
  if (viewport.zoom < 12) return mapPoints;

  const markerIds = new Set(
    mapPoints.filter((point) => point.kind === "property").map((point) => point.id),
  );
  const missing = pagePoints.filter((point) => (
    point.kind === "property"
    && !markerIds.has(point.id)
    && point.latitude <= viewport.north
    && point.latitude >= viewport.south
    && point.longitude <= viewport.east
    && point.longitude >= viewport.west
  ));
  return missing.length ? [...mapPoints, ...missing] : mapPoints;
}
