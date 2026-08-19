import type { MapMarker, MapSearchResponse, MapViewport } from "@/types/property";

type MapPoint = MapSearchResponse["points"][number];

/**
 * Server-side density progression. At detailed zoom only exact coordinate
 * duplicates remain clustered, preventing hundreds of indistinguishable pins
 * without inventing an area or changing the stored location.
 */
export function clusterMapMarkers(markers: MapMarker[], zoom: number): MapPoint[] {
  const cell = zoom >= 12 ? 0 : Math.max(0.008, (zoom <= 6 ? 128 : 48) / (2 ** zoom));
  const groups = new Map<string, { latitude: number; longitude: number; items: MapMarker[] }>();
  for (const marker of markers) {
    const key = cell === 0
      ? `${marker.latitude.toFixed(6)}:${marker.longitude.toFixed(6)}`
      : `${Math.floor(marker.latitude / cell)}:${Math.floor(marker.longitude / cell)}`;
    const group = groups.get(key);
    if (group) {
      group.latitude += marker.latitude;
      group.longitude += marker.longitude;
      group.items.push(marker);
    } else {
      groups.set(key, { latitude: marker.latitude, longitude: marker.longitude, items: [marker] });
    }
  }
  return [...groups.entries()].slice(0, 800).map(([key, group]) => group.items.length === 1 ? group.items[0] : ({
    kind: "cluster",
    id: `cluster-${key}`,
    latitude: group.latitude / group.items.length,
    longitude: group.longitude / group.items.length,
    count: group.items.length,
  }));
}

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
