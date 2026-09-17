import { describe, expect, it } from "vitest";
import { clusterMapMarkers, mergeDetailedPagePoints } from "./map-points";
import type { MapSearchResponse, MapViewport } from "@/types/property";

type MapPoint = MapSearchResponse["points"][number];

const viewport: MapViewport = { north: -34.55, east: -58.4, south: -34.6, west: -58.48, zoom: 14 };
const pageMarker: MapPoint = {
  kind: "property", id: "card-1", latitude: -34.57, longitude: -58.44,
  price: null, currency: null, propertyType: "departamento", title: "Propiedad", location: "CABA", locationConfidence: "high",
};

describe("mergeDetailedPagePoints", () => {
  it("agrega al zoom de detalle la card ubicada que el resultado limitado omitió", () => {
    const result = mergeDetailedPagePoints([], [pageMarker], viewport);
    expect(result).toEqual([pageMarker]);
  });

  it("no duplica marcadores ni agrega cards fuera del viewport", () => {
    const outside = { ...pageMarker, id: "outside", latitude: -35 };
    expect(mergeDetailedPagePoints([pageMarker], [pageMarker, outside], viewport)).toEqual([pageMarker]);
  });

  it("conserva exclusivamente clusters en zoom general", () => {
    const cluster: MapPoint = { kind: "cluster", id: "cluster-1", latitude: -34, longitude: -58, count: 20 };
    expect(mergeDetailedPagePoints([cluster], [pageMarker], { ...viewport, zoom: 10 })).toEqual([cluster]);
  });

  it("mantiene agrupados los duplicados exactos incluso en zoom alto", () => {
    const second = { ...pageMarker, id: "card-2" };
    const result = clusterMapMarkers([pageMarker, second], 15);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ kind: "cluster", count: 2, latitude: pageMarker.latitude, longitude: pageMarker.longitude });
  });

  it("separa puntos cercanos pero distintos en zoom alto", () => {
    const nearby = { ...pageMarker, id: "nearby", latitude: pageMarker.latitude + 0.0001 };
    expect(clusterMapMarkers([pageMarker, nearby], 15)).toHaveLength(2);
  });
});
