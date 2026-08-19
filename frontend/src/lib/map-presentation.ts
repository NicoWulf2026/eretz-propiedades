import type { MapViewport, PropertyCurrency } from "@/types/property";

const compactNumber = new Intl.NumberFormat("es-AR", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

const fullNumber = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export function formatMapPriceCompact(price: number | null, currency: PropertyCurrency | null): string {
  if (!price || price <= 0 || !currency) return "Consultar";
  if (price >= 1_000_000) return `${currency} ${compactNumber.format(price / 1_000_000)}M`;
  if (price >= 1_000) return `${currency} ${compactNumber.format(price / 1_000)}k`;
  return `${currency} ${compactNumber.format(price)}`;
}

export function formatMapPriceAccessible(price: number | null, currency: PropertyCurrency | null): string {
  if (!price || price <= 0 || !currency) return "Precio a consultar";
  return `${currency} ${fullNumber.format(price)}`;
}

export function clusterSize(count: number): "small" | "medium" | "large" {
  if (count < 50) return "small";
  if (count < 200) return "medium";
  return "large";
}

export function viewportMovedMeaningfully(previous: MapViewport | null, next: MapViewport): boolean {
  if (!previous) return false;
  if (Math.abs(previous.zoom - next.zoom) >= 1) return true;

  const previousCenter = {
    latitude: (previous.north + previous.south) / 2,
    longitude: (previous.east + previous.west) / 2,
  };
  const nextCenter = {
    latitude: (next.north + next.south) / 2,
    longitude: (next.east + next.west) / 2,
  };
  const latitudeSpan = Math.max(Math.abs(previous.north - previous.south), 0.00001);
  const longitudeSpan = Math.max(Math.abs(previous.east - previous.west), 0.00001);
  return (
    Math.abs(previousCenter.latitude - nextCenter.latitude) / latitudeSpan >= 0.08
    || Math.abs(previousCenter.longitude - nextCenter.longitude) / longitudeSpan >= 0.08
  );
}
