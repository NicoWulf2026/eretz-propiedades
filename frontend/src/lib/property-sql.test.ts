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
