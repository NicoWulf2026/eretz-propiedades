import { describe, expect, it } from "vitest";
import { blockingKey, classify, groupDuplicates, scoreMatch, type DupCandidate } from "@/lib/duplicates";

const base: DupCandidate = {
  id: "1", operation: "venta", propertyType: "departamento",
  city: "Córdoba", neighborhood: "Nueva Córdoba", address: "Independencia 700",
  price: 100000, currency: "USD", totalArea: 60, latitude: -31.42, longitude: -64.19,
  title: "Departamento 2 ambientes Nueva Córdoba",
};
const make = (id: string, patch: Partial<DupCandidate>): DupCandidate => ({ ...base, id, ...patch });

describe("bloqueo (evita O(n²))", () => {
  it("misma propiedad en distinta ciudad NO comparte bloque", () => {
    expect(blockingKey(base)).not.toBe(blockingKey(make("2", { city: "Rosario", latitude: -32.95, longitude: -60.64 })));
  });
  it("misma zona/operación/tipo comparte bloque", () => {
    expect(blockingKey(base)).toBe(blockingKey(make("2", { address: "Otra 100" })));
  });
});

describe("scoring y confianza", () => {
  it("dos avisos casi idénticos son HIGH_CONFIDENCE", () => {
    const b = make("2", { price: 101000, address: "Independencia 700 2A", title: "Depto 2 amb Nueva Córdoba" });
    expect(classify(scoreMatch(base, b))).toBe("HIGH_CONFIDENCE");
  });
  it("propiedades distintas son NO_MATCH", () => {
    const other = make("2", { price: 300000, totalArea: 200, address: "Colón 4500", latitude: -31.40, longitude: -64.25, title: "Casa 4 dormitorios con pileta" });
    expect(classify(scoreMatch(base, other))).toBe("NO_MATCH");
  });
  it("no compara precios en monedas distintas (anula esa señal)", () => {
    const ars = make("2", { currency: "ARS", price: 50_000_000 });
    // sin la señal de precio, el resto (misma dirección/área/coords) sigue siendo alto
    expect(scoreMatch(base, ars)).toBeGreaterThan(0.8);
  });
});

describe("agrupación (sólo alta confianza, conserva publicaciones)", () => {
  it("agrupa duplicados y conserva todos los ids", () => {
    const items = [
      base,
      make("2", { price: 100500, address: "Independencia 700 piso 2" }),
      make("3", { price: 305000, totalArea: 200, address: "Colón 4500", latitude: -31.40, longitude: -64.30, title: "Casa con jardín" }),
    ];
    const groups = groupDuplicates(items);
    expect(groups).toHaveLength(1);
    expect(groups[0].ids).toEqual(["1", "2"]); // 3 no entra
    expect(groups[0].confidence).toBe("HIGH_CONFIDENCE");
  });
  it("no agrupa nada cuando no hay coincidencias", () => {
    const items = [base, make("2", { city: "Rosario", latitude: -32.95, longitude: -60.64, address: "X 1" })];
    expect(groupDuplicates(items)).toHaveLength(0);
  });
  it("es transitivo (A~B, B~C ⇒ un solo grupo A,B,C)", () => {
    const items = [
      make("1", { price: 100000 }),
      make("2", { price: 100500 }),
      make("3", { price: 101000 }),
    ];
    const groups = groupDuplicates(items);
    expect(groups).toHaveLength(1);
    expect(groups[0].ids).toEqual(["1", "2", "3"]);
  });
});
