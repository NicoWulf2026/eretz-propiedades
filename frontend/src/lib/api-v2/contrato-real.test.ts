import { describe, expect, it } from "vitest";
import contrato from "@/test/api-v2-contrato-real.json";
import {
  parseApiV2Agency, parseApiV2Areas, parseApiV2Batch, parseApiV2Filters, parseApiV2Map,
  parseApiV2Neighborhoods, parseApiV2Page, parseApiV2Property, parseApiV2Suggestions,
} from "./schemas";
import { adaptApiV2Property } from "./adapters";

// Respuestas REALES de la API v2 (api/v2.py sobre la snapshot sintetica), generadas por
// scripts/exportar_contrato_api.py. Si la API cambia la forma de una respuesta, este test
// lo ve antes que el navegador. tests/test_contrato_api_frontend.py vigila que el archivo
// no quede viejo respecto de la API.
type Caso = { parser: string; ruta: string; respuesta: unknown };
const casos = Object.entries(contrato as Record<string, Caso>);

const parsers: Record<string, (value: unknown) => { success: boolean; issues: { path: string; message: string }[] }> = {
  search_page: (v) => parseApiV2Page(v, true),
  page: (v) => parseApiV2Page(v, false),
  map: parseApiV2Map,
  areas: parseApiV2Areas,
  neighborhoods: parseApiV2Neighborhoods,
  suggestions: parseApiV2Suggestions,
  filters: parseApiV2Filters,
  property: (v) => parseApiV2Property(v),
  agency: parseApiV2Agency,
  batch: parseApiV2Batch,
};

describe("contrato real API v2 -> esquemas del frontend", () => {
  it("cubre todos los parsers que consume el cliente", () => {
    expect(new Set(casos.map(([, c]) => c.parser))).toEqual(new Set(Object.keys(parsers)));
  });

  it.each(casos)("%s: el frontend acepta la respuesta sin observaciones", (_nombre, caso) => {
    const resultado = parsers[caso.parser](caso.respuesta);
    expect(resultado.issues).toEqual([]);
    expect(resultado.success).toBe(true);
  });

  it("los casos borde se adaptan sin inventar datos", () => {
    const sinTitulo = parseApiV2Property((contrato as Record<string, Caso>).detalle_sin_titulo.respuesta);
    expect(sinTitulo.success).toBe(true);
    if (!sinTitulo.success) return;
    const adaptada = adaptApiV2Property(sinTitulo.data);
    expect(adaptada.title).toBeNull();
    const sinMoneda = parseApiV2Property((contrato as Record<string, Caso>).detalle_sin_moneda.respuesta);
    if (!sinMoneda.success) throw new Error("sin_moneda no parsea");
    expect(adaptApiV2Property(sinMoneda.data).price.currency).toBeNull();
  });
});
