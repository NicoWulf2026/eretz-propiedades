import { describe, expect, it } from "vitest";
import { interpretNaturalQuery } from "@/lib/nl-search";
import { parsePropertyFilters } from "@/lib/property-query";

describe("interpretNaturalQuery — no inventa filtros (anti-Roomix)", () => {
  it("parsea tipo, ambientes, ubicación, moneda y precio máximo", () => {
    const r = interpretNaturalQuery("depto 2 ambientes en Palermo hasta 200000 usd");
    expect(r.params.tipo).toBe("departamento");
    expect(r.params.ambientes).toBe("2");
    expect(r.params.ubicaciones).toBe("Palermo");
    expect(r.params.moneda).toBe("USD");
    expect(r.params.precio_max).toBe("200000");
    // NO se inventó operación (no fue expresada)
    expect(r.params.operacion).toBeUndefined();
  });

  it("multi-ubicación OR: 'Palermo o Belgrano'", () => {
    const r = interpretNaturalQuery("departamento en Palermo o Belgrano para comprar");
    expect(r.params.ubicaciones).toBe("Palermo,Belgrano");
    expect(r.params.operacion).toBe("venta"); // "comprar" explícito
  });

  it("NO agrega un amenity como filtro: lo marca como no interpretado", () => {
    const r = interpretNaturalQuery("casa en Rosario con balcón y pileta");
    expect(r.params.tipo).toBe("casa");
    expect(r.params.ubicaciones).toBe("Rosario");
    // balcón/pileta NO se convierten en filtro (no hay dato) → notInterpreted
    expect(r.notInterpreted).toEqual(expect.arrayContaining(["balcon", "pileta"]));
    expect(Object.keys(r.params)).not.toContain("amenities");
  });

  it("no asume operación cuando no se expresa", () => {
    expect(interpretNaturalQuery("departamento en Palermo").params.operacion).toBeUndefined();
  });

  it("interpreta montos con 'mil'/'k'/'millones'", () => {
    expect(interpretNaturalQuery("hasta 200 mil usd").params.precio_max).toBe("200000");
    expect(interpretNaturalQuery("hasta 200k").params.precio_max).toBe("200000");
    expect(interpretNaturalQuery("desde 1,5 millones").params.precio_min).toBe("1500000");
  });

  it("rango 'entre N y M'", () => {
    const r = interpretNaturalQuery("entre 100000 y 200000 dolares");
    expect(r.params.precio_min).toBe("100000");
    expect(r.params.precio_max).toBe("200000");
    expect(r.params.moneda).toBe("USD");
  });

  it("tolera typo/coloquial y no rompe", () => {
    const r = interpretNaturalQuery("dpto 3 amb en nuñez alquiler");
    expect(r.params.tipo).toBe("departamento");
    expect(r.params.ambientes).toBe("3");
    expect(r.params.operacion).toBe("alquiler");
  });

  it("interpreta cochera ahora que el catálogo tiene respaldo real", () => {
    expect(interpretNaturalQuery("casa con cochera").params.cocheras).toBe("1");
    expect(interpretNaturalQuery("casa con 2 cocheras").params.cocheras).toBe("2");
  });

  it("input ambiguo/vacío no inventa nada", () => {
    const r = interpretNaturalQuery("algo lindo y barato");
    expect(r.params.operacion).toBeUndefined();
    expect(r.params.tipo).toBeUndefined();
    expect(r.params.ubicaciones).toBeUndefined();
  });

  it("los params interpretados son válidos para parsePropertyFilters (round-trip)", () => {
    const r = interpretNaturalQuery("depto 2 ambientes en Palermo o Belgrano hasta 200000 usd");
    const f = parsePropertyFilters(r.params);
    expect(f.propertyType).toBe("departamento");
    expect(f.minRooms).toBe(2);
    expect(f.locations).toEqual(["Palermo", "Belgrano"]);
    expect(f.currency).toBe("USD");
    expect(f.maxPrice).toBe(200000);
  });
});
