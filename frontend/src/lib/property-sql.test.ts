import { describe, expect, it } from "vitest";
import { buildWhere, sortSpec } from "@/lib/property-sql";
import { parsePropertyFilters } from "@/lib/property-query";

describe("cobertura del catálogo (Quality Gate como autoridad única)", () => {
  it("no filtra por estado: toda propiedad autorizada por el gate es alcanzable", () => {
    const { where, params } = buildWhere(parsePropertyFilters({}));
    // Sin filtros, la cláusula no restringe por estado (las no-activas autorizadas
    // por el gate quedan incluidas; el gate se aplica luego en la app).
    expect(where).toBe("TRUE");
    expect(where).not.toMatch(/estado/);
    expect(params).toEqual([]);
  });

  it("un filtro real sigue agregando condiciones sobre la cobertura completa", () => {
    const { where, params } = buildWhere(parsePropertyFilters({ operacion: "venta" }));
    expect(where).toMatch(/^TRUE AND /);
    expect(where).toMatch(/p\.operacion = \$1/);
    expect(where).not.toMatch(/estado/);
    expect(params).toEqual(["venta"]);
  });
});

describe("orden neutral (activas primero, no confirmadas por debajo)", () => {
  // Refleja en JS la expresión SQL del orden predeterminado para verificar la
  // propiedad de orden sin base de datos.
  const rank = (estado: string, id: number) => (estado === "activa" ? 1e10 : 0) + id;

  it("el orden predeterminado prioriza activas y luego id descendente", () => {
    const spec = sortSpec("recent");
    expect(spec.ascending).toBe(false);
    expect(spec.expression).toContain("p.estado = 'activa'");
    expect(spec.expression).toContain("1e10");
    expect(spec.expression).toContain("p.id");
  });

  it("una activa antigua ordena por encima de una no confirmada reciente", () => {
    const activaAntigua = rank("activa", 10);
    const desconocidaReciente = rank("desconocida", 999999);
    const noDetectada = rank("no_detectada_en_ultimo_scraping", 500000);
    // DESC: mayor valor primero. La activa (1e10+10) supera a cualquier no-activa.
    expect(activaAntigua).toBeGreaterThan(desconocidaReciente);
    expect(activaAntigua).toBeGreaterThan(noDetectada);
    // entre no-activas, ordena por id (recencia) descendente
    expect(desconocidaReciente).toBeGreaterThan(noDetectada);
  });

  it("no altera el orden de los sorts explícitos", () => {
    expect(sortSpec("price_asc")).toEqual({ expression: "COALESCE(p.precio, 1e30)", ascending: true });
    expect(sortSpec("price_desc")).toEqual({ expression: "COALESCE(p.precio, 0)", ascending: false });
  });
});
