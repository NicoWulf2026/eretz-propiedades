import { describe, expect, it } from "vitest";
import { assessLocationConfidence, classifyAddressQuality, type GeoPointStats } from "./geo-confidence";

const uniquePoint: GeoPointStats = {
  propertyCount: 1,
  addressCount: 1,
  cityCount: 1,
  provinceCount: 1,
  agencyCount: 1,
};

function assess(overrides: Partial<Parameters<typeof assessLocationConfidence>[0]> = {}) {
  return assessLocationConfidence({
    latitude: -34.6037,
    longitude: -58.3816,
    address: "Av. Corrientes 1234",
    neighborhood: "San Nicolás",
    city: "Ciudad Autónoma de Buenos Aires",
    province: "Capital Federal",
    pointStats: uniquePoint,
    ...overrides,
  });
}

describe("geo confidence", () => {
  it("clasifica coordenadas ausentes o fuera de Argentina como sin ubicación", () => {
    expect(assess({ latitude: null, longitude: null }).level).toBe("none");
    expect(assess({ latitude: 40.7, longitude: -74 }).level).toBe("none");
  });

  it("reconoce una dirección completa sin llamarla exacta", () => {
    expect(classifyAddressQuality("La Pampa 2700", "CABA", "Capital Federal")).toBe("street_number");
    expect(assess().level).toBe("high");
    expect(assess().score).toBe(98);
  });

  it("mantiene conservadora una coordenada sin estadísticas del punto", () => {
    expect(assess({ pointStats: null }).level).toBe("approximate");
  });

  it("distingue calle sin altura, desarrollo y texto insuficiente", () => {
    expect(classifyAddressQuality("Avenida Santa Fe", "CABA", "Capital Federal")).toBe("street");
    expect(classifyAddressQuality("Barrio San Matías", "Escobar", "Buenos Aires")).toBe("development");
    expect(classifyAddressQuality("Inicio Propiedades Tasaciones Contacto", null, null)).toBe("insufficient");
  });

  it("no penaliza injustamente un edificio legítimo", () => {
    expect(assess({ pointStats: { ...uniquePoint, propertyCount: 30 } }).level).toBe("high");
  });

  it("marca reutilización extrema y ciudades contradictorias como dudosas", () => {
    const result = assess({ pointStats: { propertyCount: 6993, addressCount: 130, cityCount: 14, provinceCount: 2, agencyCount: 79 } });
    expect(result.level).toBe("doubtful");
    expect(result.reasons).toContain("extreme_point_reuse");
    expect(result.reasons).toContain("conflicting_cities");
  });

  it("marca provincias contradictorias aunque el score no caiga por debajo de 30", () => {
    expect(assess({ pointStats: { ...uniquePoint, propertyCount: 2, addressCount: 2, provinceCount: 2 } }).level).toBe("doubtful");
  });

  it.each([
    ["104773", "La Pampa 2700", uniquePoint, "high"],
    ["104962", "Inicio Propiedades Tasaciones Contacto Inicio Propiedades Tasaciones Contacto ".repeat(4), { propertyCount: 30, addressCount: 30, cityCount: 4, provinceCount: 2, agencyCount: 1 }, "doubtful"],
    ["115673", "Inicio Propiedades Tasaciones Contacto", { propertyCount: 6993, addressCount: 130, cityCount: 14, provinceCount: 2, agencyCount: 79 }, "doubtful"],
    ["110542", "Barrio San Matías 100", { propertyCount: 57, addressCount: 6, cityCount: 2, provinceCount: 1, agencyCount: 5 }, "doubtful"],
    ["113105", "Inicio Propiedades Tasaciones Contacto", { propertyCount: 930, addressCount: 45, cityCount: 4, provinceCount: 2, agencyCount: 22 }, "doubtful"],
  ])("clasifica el caso conocido %s", (_id, address, pointStats, expected) => {
    expect(assess({ address, pointStats, neighborhood: _id === "110542" ? null : "San Nicolás" }).level).toBe(expected);
  });
});
