import { describe, expect, it } from "vitest";
import { availabilityLabel, derivedTitle, isAvailabilityConfirmed, propertyPrice, propertySpecs, UNTITLED_PROPERTY } from "@/lib/property-presenter";

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

describe("título derivado (P9)", () => {
  it("compone tipo, operación y localidad sólo con datos reales", () => {
    expect(derivedTitle({ propertyType: "casa", operation: "venta", city: "Rosario", neighborhood: "Centro" })).toBe("Casa en venta · Rosario");
    expect(derivedTitle({ propertyType: "departamento", operation: "temporario", city: null, neighborhood: "Palermo" }))
      .toBe("Departamento en alquiler temporario · Palermo");
    expect(derivedTitle({ propertyType: "ph", operation: "venta_y_alquiler" })).toBe("PH en venta y alquiler");
  });

  it("usa la combinación parcial disponible", () => {
    expect(derivedTitle({ propertyType: "terreno", operation: "consultar" })).toBe("Terreno");
    expect(derivedTitle({ propertyType: "otro", operation: "alquiler" })).toBe("Propiedad en alquiler");
    expect(derivedTitle({ propertyType: "otro", operation: "consultar", city: "Mar del Plata" })).toBe("Propiedad · Mar del Plata");
  });

  it("no afirma «otro» ni «consultar», que también significan sin dato", () => {
    expect(derivedTitle({ propertyType: "otro", operation: "consultar", city: null, neighborhood: null })).toBe(UNTITLED_PROPERTY);
    expect(derivedTitle({ propertyType: "otro", operation: "consultar", city: "  ", neighborhood: "" })).toBe("Propiedad sin título");
  });
});
