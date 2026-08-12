import { describe, expect, it } from "vitest";
import { buildCursorClause, buildWhere, sortSpec, type CursorPayload } from "@/lib/property-sql";
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

describe("multi-ubicación (OR entre términos, AND con el resto)", () => {
  it("une varias ubicaciones con OR, cada una sobre provincia/ciudad/barrio/dirección", () => {
    const { where, params } = buildWhere(parsePropertyFilters({ ubicaciones: "Palermo,Belgrano" }));
    // dos bloques de 4 columnas cada uno, unidos por OR dentro de un paréntesis
    expect(where).toMatch(/\(\(p\.provincia ILIKE \$1 OR p\.ciudad ILIKE \$2 OR p\.barrio ILIKE \$3 OR p\.direccion ILIKE \$4\) OR \(p\.provincia ILIKE \$5/);
    expect(params).toEqual(["%Palermo%", "%Palermo%", "%Palermo%", "%Palermo%", "%Belgrano%", "%Belgrano%", "%Belgrano%", "%Belgrano%"]);
  });

  it("se combina con AND con otros filtros", () => {
    const { where } = buildWhere(parsePropertyFilters({ ubicaciones: "Rosario", operacion: "venta" }));
    expect(where).toMatch(/p\.operacion = /);
    expect(where).toMatch(/ AND \(\(p\.provincia ILIKE/);
  });
});

describe("multi-zona del mapa (OR entre zonas, AND con el resto)", () => {
  it("rectángulo → BETWEEN lat/lng", () => {
    const { where } = buildWhere(parsePropertyFilters({ zonas: "b:-34,-58,-35,-59" }));
    expect(where).toContain("p.latitud BETWEEN -35 AND -34");
    expect(where).toContain("p.longitud BETWEEN -59 AND -58");
  });
  it("radio → haversine en km con acos clampeado", () => {
    const { where } = buildWhere(parsePropertyFilters({ zonas: "r:-34.6,-58.4,5" }));
    expect(where).toContain("6371 * acos(least(1, greatest(-1,");
    expect(where).toContain(")) <= 5");
    expect(where).toContain("p.latitud IS NOT NULL");
  });
  it("varias zonas se combinan con OR y con AND respecto de otros filtros", () => {
    const { where } = buildWhere(parsePropertyFilters({ zonas: "b:-34,-58,-35,-59;r:-31.4,-64.2,3", operacion: "venta" }));
    expect(where).toMatch(/\(\(p\.latitud BETWEEN .* OR \(p\.latitud IS NOT NULL/);
    expect(where).toMatch(/p\.operacion = /);
  });
  it("sin zonas no agrega geometría", () => {
    expect(buildWhere(parsePropertyFilters({})).where).not.toMatch(/BETWEEN|haversine|acos/);
  });
});

describe("precio: con precio / a consultar / todas", () => {
  it("'todas' (default) no agrega condición de precio", () => {
    const { where } = buildWhere(parsePropertyFilters({}));
    expect(where).not.toMatch(/precio/);
  });
  it("'con precio' exige precio publicado", () => {
    const { where } = buildWhere(parsePropertyFilters({ precio: "with" }));
    expect(where).toContain("p.precio > 0 AND p.moneda IS NOT NULL");
  });
  it("'a consultar' incluye NULL/0/sin moneda", () => {
    const { where } = buildWhere(parsePropertyFilters({ precio: "consult" }));
    expect(where).toContain("(p.precio IS NULL OR p.precio <= 0 OR p.moneda IS NULL)");
  });
});

describe("tri-state NULL-safe (apto crédito)", () => {
  it("'sí' exige TRUE; 'no' exige FALSE explícito; 'sininfo' exige NULL", () => {
    expect(buildWhere(parsePropertyFilters({ credito: "si" })).where).toContain("p.apto_credito IS TRUE");
    expect(buildWhere(parsePropertyFilters({ credito: "no" })).where).toContain("p.apto_credito IS FALSE");
    expect(buildWhere(parsePropertyFilters({ credito: "sininfo" })).where).toContain("p.apto_credito IS NULL");
  });
  it("NULL nunca cae en 'no': 'no' no toca las filas NULL", () => {
    // IS FALSE excluye tanto TRUE como NULL; una fila sin dato (NULL) no es "no".
    expect(buildWhere(parsePropertyFilters({ credito: "no" })).where).not.toContain("IS NULL");
  });
  it("default (cualquiera) no agrega condición de crédito", () => {
    expect(buildWhere(parsePropertyFilters({})).where).not.toMatch(/apto_credito/);
  });
});

describe("orden por cercanía (cursor-safe, sin coordenadas al final)", () => {
  it("inlinea el punto validado y manda las filas sin coordenadas al final", () => {
    const spec = sortSpec("nearest", { lat: -34.6, lng: -58.4 });
    expect(spec.ascending).toBe(true);
    expect(spec.expression).toContain("(p.latitud - (-34.6))");
    expect(spec.expression).toContain("(p.longitud - (-58.4))");
    expect(spec.expression).toContain("1e30"); // sin coords → al final
  });
  it("sin punto de referencia cae al orden por recencia", () => {
    expect(sortSpec("nearest", null).expression).toContain("p.estado = 'activa'");
  });
});

describe("cursor keyset (orden total y estable, desempate único por ID)", () => {
  const cur = (value: number, id: string): CursorPayload => ({ version: 1, sort: "recent", value, id });

  it("sin cursor no agrega cláusula", () => {
    const params: unknown[] = [];
    expect(buildCursorClause(params, null, "p.id", false, "next")).toBe("");
    expect(params).toEqual([]);
  });

  it("usa el operador correcto y SIEMPRE incluye el desempate por id en las 4 combinaciones", () => {
    const cases: Array<[boolean, "next" | "prev", string]> = [
      [false, "next", "<"], // DESC hacia adelante
      [false, "prev", ">"], // DESC hacia atrás
      [true, "next", ">"],  // ASC hacia adelante
      [true, "prev", "<"],  // ASC hacia atrás
    ];
    for (const [ascending, direction, op] of cases) {
      const params: unknown[] = [];
      const clause = buildCursorClause(params, cur(10, "500"), "p.id", ascending, direction);
      // frontera por valor con el operador correcto…
      expect(clause).toContain(`p.id ${op} $1`);
      // …y desempate único por id con EL MISMO operador (orden total)
      expect(clause).toContain(`(p.id = $1 AND p.id ${op} $2)`);
      expect(params).toEqual([10, 500]);
    }
  });

  // Simula la paginación keyset (espejo del SQL) y prueba 0 solapamientos y 0 omisiones.
  it("pagina un dataset sin solapamientos ni omisiones (orden total)", () => {
    // rows con VALOR repetido a propósito, para forzar el desempate por id
    const rows = Array.from({ length: 97 }, (_, i) => ({ value: Math.floor(i / 5), id: 1000 - i }));
    // orden DESC por (value, id) — el mismo que ORDER BY expr DESC, id DESC
    const sorted = [...rows].sort((a, b) => (b.value - a.value) || (b.id - a.id));
    const PAGE = 24;
    const seen = new Set<number>();
    let cursor: { value: number; id: number } | null = null;
    let pages = 0;
    const collected: number[] = [];
    while (pages < 20) {
      const page = sorted.filter((r) =>
        cursor === null ? true : (r.value < cursor!.value || (r.value === cursor!.value && r.id < cursor!.id)),
      ).slice(0, PAGE);
      if (page.length === 0) break;
      for (const r of page) { collected.push(r.id); seen.add(r.id); }
      const last = page[page.length - 1];
      cursor = { value: last.value, id: last.id };
      pages += 1;
      if (page.length < PAGE) break;
    }
    // 0 duplicados (sin solapamientos) y cobertura completa (sin omisiones)
    expect(collected.length).toBe(new Set(collected).size);
    expect(seen.size).toBe(rows.length);
    // el orden recorrido es exactamente el orden total esperado
    expect(collected).toEqual(sorted.map((r) => r.id));
  });
});
