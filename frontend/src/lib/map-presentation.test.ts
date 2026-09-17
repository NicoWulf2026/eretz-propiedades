import { describe, expect, it } from "vitest";
import {
  clusterSize,
  formatMapPriceAccessible,
  formatMapPriceCompact,
  viewportMovedMeaningfully,
} from "./map-presentation";
import type { MapViewport } from "@/types/property";

describe("map presentation", () => {
  it("formatea precios sin abreviaturas ambiguas", () => {
    expect(formatMapPriceCompact(185_000, "USD")).toBe("USD 185k");
    expect(formatMapPriceCompact(1_200_000, "USD")).toBe("USD 1,2M");
    expect(formatMapPriceCompact(850_000, "ARS")).toBe("ARS 850k");
    expect(formatMapPriceCompact(null, "USD")).toBe("Consultar");
    expect(formatMapPriceCompact(0, null)).toBe("Consultar");
    expect(formatMapPriceAccessible(185_000, "USD")).toBe("USD 185.000");
  });

  it("escala clusters por densidad sin perder el conteo real", () => {
    expect(clusterSize(24)).toBe("small");
    expect(clusterSize(128)).toBe("medium");
    expect(clusterSize(1_250)).toBe("large");
  });

  it("ignora movimientos mínimos y detecta pan o zoom significativos", () => {
    const viewport: MapViewport = { north: -34.4, east: -58.2, south: -34.8, west: -58.7, zoom: 10 };
    expect(viewportMovedMeaningfully(viewport, { ...viewport, north: -34.39, south: -34.79 })).toBe(false);
    expect(viewportMovedMeaningfully(viewport, { ...viewport, north: -34.35, south: -34.75 })).toBe(true);
    expect(viewportMovedMeaningfully(viewport, { ...viewport, zoom: 11 })).toBe(true);
  });
});
