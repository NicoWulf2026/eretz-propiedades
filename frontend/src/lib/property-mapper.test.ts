import { describe, expect, it } from "vitest";
import { completeRow } from "@/test/fixtures";
import {
  mapSupabasePropertyToProperty,
  normalizeCurrency,
  normalizeOperation,
} from "@/lib/property-mapper";

describe("property mapper", () => {
  it("maps complete public data without changing the published price", () => {
    const property = mapSupabasePropertyToProperty(completeRow);
    expect(property.price).toBe(180000);
    expect(property.currency).toBe("USD");
    expect(property.images).toEqual(["https://images.example/house.jpg"]);
    expect(property.quality).toEqual(expect.objectContaining({ hasPrice: true, hasImages: true, hasCoordinates: true }));
  });

  it("uses honest fallbacks and rejects unsafe content", () => {
    const property = mapSupabasePropertyToProperty({
      ...completeRow,
      titulo: "Propiedad sin título",
      descripcion: "",
      precio: null,
      moneda: null,
      imagenes: ["javascript:alert(1)", "https://host.example/logo.png"],
      latitud: 99,
      longitud: -64,
      url: "javascript:alert(1)",
    });
    expect(property.title).toBe("Propiedad sin título");
    expect(property.description).toBeNull();
    expect(property.price).toBeNull();
    expect(property.currency).toBeNull();
    expect(property.images).toEqual([]);
    expect(property.sourceUrl).toBeNull();
    expect(property.latitude).toBeNull();
  });

  it("supports all public currencies and operations", () => {
    expect(["USD", "ARS", "EUR", "UYU"].map(normalizeCurrency)).toEqual(["USD", "ARS", "EUR", "UYU"]);
    expect(normalizeCurrency("desconocida")).toBeNull();
    expect(normalizeOperation("alquiler_temporario")).toBe("temporario");
    expect(normalizeOperation("venta_y_alquiler")).toBe("venta_y_alquiler");
  });
});

