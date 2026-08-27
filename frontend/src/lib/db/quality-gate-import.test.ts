import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CLASIFICACIONES_VISIBLES,
  MOTIVOS_NO_ACTIVAR,
  decidirActivacion,
  enLotes,
  esVisible,
  parsearManifiesto,
  planDeImportacion,
  versionDeManifiesto,
} from "../../../scripts/import-quality-gate.mjs";

const ENCABEZADO = "property_id,classification,preview_visible";

const csv = (...filas: string[]) => [ENCABEZADO, ...filas].join("\n");

const valido = csv(
  "1,PUBLICABLE_COMPLETE,true",
  "2,PUBLICABLE_INCOMPLETE,true",
  "3,REVIEW_REQUIRED,false",
  "4,INVALID,false",
);

describe("importación del Quality Gate", () => {
  it("sólo dos clasificaciones hacen visible una publicación", () => {
    expect(CLASIFICACIONES_VISIBLES).toEqual(["PUBLICABLE_COMPLETE", "PUBLICABLE_INCOMPLETE"]);
    expect(esVisible("PUBLICABLE_INCOMPLETE")).toBe(true);
    expect(esVisible("REVIEW_REQUIRED")).toBe(false);
    expect(esVisible("SOURCE_UNAVAILABLE")).toBe(false);
  });

  it("la versión es el hash del contenido, igual que en el runtime", () => {
    expect(versionDeManifiesto(valido)).toMatch(/^[a-f0-9]{16}$/);
    expect(versionDeManifiesto(valido)).toBe(versionDeManifiesto(valido));
    expect(versionDeManifiesto(valido)).not.toBe(versionDeManifiesto(valido + "\n5,INVALID,false"));
  });

  // --- el manifiesto se rechaza entero, no por fila ------------------------

  it("rechaza el manifiesto entero ante una fila inválida", () => {
    // Un manifiesto al que le falta una fila no es un manifiesto con una fila
    // menos: es uno del que no sabemos qué más le falta.
    expect(() => parsearManifiesto(csv("1,NO_EXISTE,false"))).toThrow(/Fila inválida/);
    expect(() => parsearManifiesto(csv("x,INVALID,false"))).toThrow(/Fila inválida/);
    expect(() => parsearManifiesto(csv("1,INVALID,false,sobra"))).toThrow(/Fila inválida/);
  });

  it("rechaza una visibilidad que contradice su clasificación", () => {
    // Es la protección que impide marcar visible algo que la clasificación
    // excluye editando el CSV a mano.
    expect(() => parsearManifiesto(csv("1,REVIEW_REQUIRED,true"))).toThrow(/incoherente/);
    expect(() => parsearManifiesto(csv("1,PUBLICABLE_COMPLETE,false"))).toThrow(/incoherente/);
  });

  it("rechaza ids duplicados y encabezado distinto", () => {
    expect(() => parsearManifiesto(csv("1,INVALID,false", "1,INVALID,false")))
      .toThrow(/duplicada/);
    expect(() => parsearManifiesto("otro,encabezado\n1,INVALID,false")).toThrow(/Encabezado/);
  });

  it("rechaza un manifiesto vacío", () => {
    expect(() => parsearManifiesto(csv())).toThrow(/vacío/);
  });

  it("resume el plan sin tocar la base", () => {
    const plan = planDeImportacion(valido);
    expect(plan.totalFilas).toBe(4);
    expect(plan.totalVisibles).toBe(2);
    expect(plan.lotes).toBe(1);
  });

  it("parte en lotes conservando el orden y sin perder filas", () => {
    const filas = Array.from({ length: 12_003 }, (_, i) => ({ propertyId: String(i) }));
    const lotes = enLotes(filas, 5_000);
    expect(lotes.map((l) => l.length)).toEqual([5_000, 5_000, 2_003]);
    expect(lotes.flat()).toHaveLength(12_003);
    expect(lotes[2][2_002].propertyId).toBe("12002");
  });

  // --- la decisión de activar ---------------------------------------------

  const base = { esperadoFilas: 100, esperadoVisibles: 60, cargadoFilas: 100, cargadoVisibles: 60 };

  it("activa cuando lo cargado coincide con lo esperado", () => {
    expect(decidirActivacion(base).activar).toBe(true);
  });

  it("no activa una carga incompleta", () => {
    expect(decidirActivacion({ ...base, cargadoFilas: 99 }))
      .toMatchObject({ activar: false, motivo: MOTIVOS_NO_ACTIVAR.FALTAN_FILAS });
  });

  it("tampoco activa si sobran filas", () => {
    // Sobrar es tan sospechoso como faltar: significa que quedó algo de un
    // intento anterior mezclado.
    expect(decidirActivacion({ ...base, cargadoFilas: 101 }))
      .toMatchObject({ activar: false, motivo: MOTIVOS_NO_ACTIVAR.SOBRAN_FILAS });
  });

  it("no activa si la cantidad de visibles no coincide", () => {
    expect(decidirActivacion({ ...base, cargadoVisibles: 59 }))
      .toMatchObject({ activar: false, motivo: MOTIVOS_NO_ACTIVAR.VISIBLES_DISTINTOS });
  });

  it("no activa un manifiesto que dejaría el catálogo vacío", () => {
    expect(decidirActivacion({ ...base, esperadoVisibles: 0, cargadoVisibles: 0 }))
      .toMatchObject({ activar: false, motivo: MOTIVOS_NO_ACTIVAR.SIN_VISIBLES });
  });

  it("no activa ante una caída brusca de visibles", () => {
    // Suele ser un manifiesto mal generado aguas arriba. Técnicamente no falló
    // nada, y activarlo vaciaría medio catálogo. La versión anterior sigue
    // sirviendo, que es un estado correcto y conocido.
    const v = decidirActivacion({
      esperadoFilas: 100, esperadoVisibles: 10, cargadoFilas: 100, cargadoVisibles: 10,
      visiblesPrevios: 60,
    });
    expect(v).toMatchObject({ activar: false, motivo: MOTIVOS_NO_ACTIVAR.CAIDA_SOSPECHOSA });
  });

  it("una caída dentro de lo tolerado sí activa", () => {
    expect(decidirActivacion({
      esperadoFilas: 100, esperadoVisibles: 50, cargadoFilas: 100, cargadoVisibles: 50,
      visiblesPrevios: 60,
    }).activar).toBe(true);
  });

  it("un aumento de visibles no se frena", () => {
    expect(decidirActivacion({
      esperadoFilas: 200, esperadoVisibles: 150, cargadoFilas: 200, cargadoVisibles: 150,
      visiblesPrevios: 60,
    }).activar).toBe(true);
  });

  it("la primera importación no tiene con qué comparar y activa igual", () => {
    expect(decidirActivacion({ ...base, visiblesPrevios: null }).activar).toBe(true);
  });

  it("el importador corre la guarda de destino antes que nada", () => {
    // Importar contra la base equivocada es exactamente el accidente que la
    // guarda existe para impedir.
    const src = readFileSync(
      join(process.cwd(), "scripts/import-quality-gate.mjs"),
      "utf8",
    );
    const cuerpo = src.slice(src.indexOf("export async function importar"));
    expect(cuerpo.indexOf("exigirDestinoSeguro")).toBeLessThan(cuerpo.indexOf("await sql"));
  });
});
