import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  COLUMNAS_PROPIEDADES,
  EXTENSIONES_REQUERIDAS,
  FALTA,
  RELACIONES_GATE,
  describirFaltas,
  verificarContrato,
} from "../../../scripts/db-schema-contract.mjs";

type Col = { schema: string; nombre: string; columna: string };

/** Una base que cumple todo, para partir de ahí y quitarle cosas. */
function baseCompleta(): { columnas: Col[]; extensiones: string[] } {
  const columnas: Col[] = COLUMNAS_PROPIEDADES.map((columna: string) => ({
    schema: "public", nombre: "propiedades", columna,
  }));
  for (const columna of ["id", "nombre"]) {
    columnas.push({ schema: "public", nombre: "inmobiliarias_main", columna });
  }
  return { columnas, extensiones: ["postgis", "pg_trgm"] };
}

describe("contrato de esquema", () => {
  it("acepta una base que tiene todo", () => {
    expect(verificarContrato(baseCompleta())).toEqual({ cumple: true, faltas: [] });
  });

  it("detecta una columna que la aplicación lee y la base no tiene", () => {
    const b = baseCompleta();
    b.columnas = b.columnas.filter((c) => c.columna !== "moneda");
    const r = verificarContrato(b);
    expect(r.cumple).toBe(false);
    expect(r.faltas).toContainEqual({
      tipo: FALTA.COLUMNA, relacion: "public.propiedades", columna: "moneda",
    });
  });

  it("no lista treinta columnas cuando lo que falta es la tabla entera", () => {
    // Un informe con 30 líneas cuando el problema es uno solo hace que nadie
    // lea el informe.
    const b = baseCompleta();
    b.columnas = b.columnas.filter((c) => c.nombre !== "propiedades");
    const r = verificarContrato(b);
    expect(r.faltas).toEqual([{ tipo: FALTA.RELACION, relacion: "public.propiedades" }]);
  });

  it("detecta PostGIS ausente", () => {
    const b = baseCompleta();
    b.extensiones = ["pg_trgm"];
    expect(verificarContrato(b).faltas).toContainEqual({
      tipo: FALTA.EXTENSION, extension: "postgis",
    });
    expect(EXTENSIONES_REQUERIDAS).toContain("postgis");
  });

  it("no exige el Quality Gate salvo que se le pida", () => {
    // Su ausencia no impide que la aplicación funcione: sigue filtrando en
    // Node. Sí impide el camino nuevo, y por eso se puede verificar aparte.
    expect(verificarContrato(baseCompleta()).cumple).toBe(true);
    const conGate = verificarContrato(baseCompleta(), true);
    expect(conGate.cumple).toBe(false);
    expect(conGate.faltas).toHaveLength(RELACIONES_GATE.length);
  });

  it("acepta el gate cuando está", () => {
    const b = baseCompleta();
    for (const rel of RELACIONES_GATE) {
      b.columnas.push({ schema: rel.schema, nombre: rel.nombre, columna: "property_id" });
    }
    expect(verificarContrato(b, true).cumple).toBe(true);
  });

  it("una base vacía no pasa por casualidad", () => {
    const r = verificarContrato({});
    expect(r.cumple).toBe(false);
    expect(r.faltas.length).toBeGreaterThan(0);
  });

  it("describe las faltas de forma legible", () => {
    const b = baseCompleta();
    b.columnas = b.columnas.filter((c) => c.columna !== "precio");
    const texto = describirFaltas(verificarContrato(b).faltas);
    expect(texto).toContain("public.propiedades.precio");
    expect(describirFaltas([])).toMatch(/cumple/);
  });

  // --- el contrato tiene que seguir al código -----------------------------

  it("cubre todas las columnas que el SQL de la aplicación menciona", () => {
    // Si el código empieza a leer una columna nueva y no se agrega al
    // contrato, el verificador deja de proteger contra su ausencia sin que
    // nada falle. Este test es lo que evita esa deriva silenciosa.
    const sql = readFileSync(join(process.cwd(), "src/lib/property-sql.ts"), "utf8");
    const mencionadas = new Set(
      Array.from(sql.matchAll(/\bp\.([a-z_]+)\b/g), (m) => m[1]),
    );
    const declaradas = new Set<string>(COLUMNAS_PROPIEDADES);
    const sinDeclarar = [...mencionadas].filter((c) => !declaradas.has(c));
    expect(sinDeclarar).toEqual([]);
  });

  it("no declara columnas que nadie usa", () => {
    // Un contrato inflado rechaza bases que servirían perfectamente.
    const sql = readFileSync(join(process.cwd(), "src/lib/property-sql.ts"), "utf8");
    const mapper = readFileSync(join(process.cwd(), "src/lib/property-mapper.ts"), "utf8");
    const texto = sql + mapper;
    const sinUsar = COLUMNAS_PROPIEDADES.filter(
      (c: string) => !new RegExp(`\\b${c}\\b`).test(texto),
    );
    expect(sinUsar).toEqual([]);
  });

  it("no inventa el esquema faltante", () => {
    // Escribir un CREATE TABLE a partir de lo que el codigo consulta seria
    // adivinar tipos, nulabilidad, defaults e indices. Una base "parecida" es
    // peor que no tener base: los benchmarks medirian otra cosa.
    const src = readFileSync(join(process.cwd(), "scripts/db-schema-contract.mjs"), "utf8");
    // Se miran las sentencias, no la prosa: el encabezado explica justamente
    // por que NO se escribe un CREATE TABLE, y esa mencion no es una.
    const sinComentarios = src
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split("\n")
      .filter((l) => !l.trimStart().startsWith("//") && !l.trimStart().startsWith("*"))
      .join("\n");
    expect(sinComentarios).not.toMatch(/create\s+table/i);
    expect(sinComentarios).not.toMatch(/\balter\s+table\b/i);
  });
});
