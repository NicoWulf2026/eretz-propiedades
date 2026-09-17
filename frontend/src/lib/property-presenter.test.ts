import { describe, expect, it } from "vitest";
import { availabilityLabel, isAvailabilityConfirmed, propertyPrice, propertySpecs } from "@/lib/property-presenter";

describe("disponibilidad no confirmada", () => {
  it("sólo 'activa' es disponibilidad confirmada", () => {
    expect(isAvailabilityConfirmed("activa")).toBe(true);
    expect(isAvailabilityConfirmed("no_detectada_en_ultimo_scraping")).toBe(false);
    expect(isAvailabilityConfirmed("desconocida")).toBe(false);
  });

  it("muestra la etiqueta neutral sólo cuando corresponde", () => {
    expect(availabilityLabel("activa")).toBeNull();
    expect(availabilityLabel("no_detectada_en_ultimo_scraping")).toBe("Disponibilidad no confirmada");
    expect(availabilityLabel("desconocida")).toBe("Disponibilidad no confirmada");
  });
});

describe("presentación de valores conocidos", () => {
  it("distingue precio cero de precio desconocido", () => {
    expect(propertyPrice({ price: 0, currency: "USD" })).toBe("USD 0");
    expect(propertyPrice({ price: null, currency: "USD" })).toBe("Precio a consultar");
    expect(propertyPrice({ price: 0, currency: null })).toBe("Precio a consultar");
  });

  it("distingue cero de null en características y superficies", () => {
    expect(propertySpecs({ rooms: null, bedrooms: 0, bathrooms: 0, garages: 0, totalArea: 0, coveredArea: 80 }))
      .toEqual(["0 dorm.", "0 baños", "0 coch.", "0 m² tot."]);
    expect(propertySpecs({ rooms: null, bedrooms: null, bathrooms: null, garages: null, totalArea: null, coveredArea: 0 }))
      .toEqual(["0 m² cub."]);
  });
});
