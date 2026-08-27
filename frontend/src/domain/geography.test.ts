import { describe, expect, it } from "vitest";
import {
  GEO_PRECISIONS,
  PROCEDENCIA_DESCONOCIDA,
  PROVINCIAS,
  type GeoProvenance,
  capitalizarUbicacion,
  claveDeComparacion,
  limpiarTexto,
  precisionPermitePunto,
  presentacionDe,
  problemasDeProcedencia,
  resolverProvincia,
} from "./geography";

describe("procedencia", () => {
  it("distingue precisión de confianza", () => {
    // La precisión dice a qué nivel se resolvió; la confianza, cuánto le
    // creemos. Son ejes independientes.
    expect(GEO_PRECISIONS).toContain("ROOFTOP");
    expect(GEO_PRECISIONS).toContain("LOCALITY");
  });

  it("sólo la precisión de calle o mejor justifica un punto", () => {
    for (const p of ["ROOFTOP", "STREET_NUMBER", "STREET"] as const) {
      expect(precisionPermitePunto(p)).toBe(true);
    }
    for (const p of ["NEIGHBORHOOD", "LOCALITY", "UNKNOWN"] as const) {
      expect(precisionPermitePunto(p)).toBe(false);
    }
  });

  it("la procedencia de lo que hay hoy es honesta: sin historia", () => {
    expect(PROCEDENCIA_DESCONOCIDA.provider).toBeNull();
    expect(PROCEDENCIA_DESCONOCIDA.geocodedAt).toBeNull();
    expect(PROCEDENCIA_DESCONOCIDA.precision).toBe("UNKNOWN");
  });

  it("exige proveedor y fecha en lo geocodificado", () => {
    const base: GeoProvenance = {
      source: "GEOCODED",
      provider: null,
      geocodedAt: null,
      precision: "STREET",
      confidence: "high",
      manualOverride: false,
      evidence: null,
    };
    const problemas = problemasDeProcedencia(base);
    expect(problemas.some((p) => /proveedor/.test(p))).toBe(true);
    expect(problemas.some((p) => /cuándo/.test(p))).toBe(true);
  });

  it("una corrección manual queda marcada", () => {
    const p: GeoProvenance = {
      ...PROCEDENCIA_DESCONOCIDA,
      source: "MANUAL",
      manualOverride: false,
      precision: "ROOFTOP",
      confidence: "high",
    };
    expect(problemasDeProcedencia(p)[0]).toMatch(/marcada como tal/);
  });

  it("sin confianza no puede haber precisión declarada", () => {
    const p: GeoProvenance = { ...PROCEDENCIA_DESCONOCIDA, precision: "ROOFTOP" };
    expect(problemasDeProcedencia(p)[0]).toMatch(/sin confianza/);
  });

  it("acepta una procedencia bien formada", () => {
    const p: GeoProvenance = {
      source: "GEOCODED",
      provider: "proveedor-x",
      geocodedAt: "2026-08-01",
      precision: "STREET_NUMBER",
      confidence: "high",
      manualOverride: false,
      evidence: { inputText: "Av. Siempreviva 742", matchedText: "Av. Siempreviva 742, Rosario" },
    };
    expect(problemasDeProcedencia(p)).toEqual([]);
  });
});

describe("limpieza mecánica", () => {
  it("colapsa espacios y recorta puntuación de los bordes", () => {
    expect(limpiarTexto("  Rosario ,  ")).toBe("Rosario");
    expect(limpiarTexto("San   Lorenzo")).toBe("San Lorenzo");
  });

  it("no cambia el significado: preserva acentos y mayúsculas internas", () => {
    expect(limpiarTexto("Río Cuarto")).toBe("Río Cuarto");
    expect(limpiarTexto("CABA")).toBe("CABA");
  });

  it("normaliza comillas tipográficas y guiones repetidos", () => {
    expect(limpiarTexto("Villa ‘La Ñata’")).toBe("Villa 'La Ñata'");
    expect(limpiarTexto("Bahía -- Blanca")).toBe("Bahía-Blanca");
  });

  it("un texto vacío es ausencia, no cadena vacía", () => {
    for (const v of ["", "   ", ",", null, undefined, 5 as unknown as string]) {
      expect(limpiarTexto(v)).toBeNull();
    }
  });
});

describe("clave de comparación", () => {
  it("iguala variantes de escritura", () => {
    expect(claveDeComparacion("Río Cuarto")).toBe(claveDeComparacion("RIO CUARTO"));
    expect(claveDeComparacion("Santa Fé")).toBe(claveDeComparacion("santa fe"));
  });

  it("no iguala lugares distintos", () => {
    expect(claveDeComparacion("San Lorenzo")).not.toBe(claveDeComparacion("San Martín"));
  });
});

describe("capitalización", () => {
  it("respeta las partículas del castellano", () => {
    expect(capitalizarUbicacion("SAN MIGUEL DE TUCUMAN")).toBe("San Miguel de Tucuman");
    expect(capitalizarUbicacion("mar del plata")).toBe("Mar del Plata");
  });

  it("capitaliza la primera palabra aunque sea partícula", () => {
    expect(capitalizarUbicacion("la plata")).toBe("La Plata");
  });

  it("devuelve null para lo vacío", () => {
    expect(capitalizarUbicacion("  ")).toBeNull();
  });
});

describe("provincias: lista oficial, no inferencia", () => {
  it("son las 24 jurisdicciones", () => {
    expect(PROVINCIAS).toHaveLength(24);
  });

  it("resuelve un nombre exacto sin importar acentos ni caja", () => {
    expect(resolverProvincia("santa fe")).toEqual({ estado: "RESUELTA", provincia: "Santa Fe" });
    expect(resolverProvincia("CORDOBA")).toEqual({ estado: "RESUELTA", provincia: "Córdoba" });
    expect(resolverProvincia("Tucumán")).toEqual({ estado: "RESUELTA", provincia: "Tucumán" });
  });

  it("resuelve las denominaciones de uso universal", () => {
    for (const v of ["CABA", "Capital Federal", "Ciudad de Buenos Aires"]) {
      expect(resolverProvincia(v)).toEqual({
        estado: "RESUELTA",
        provincia: "Ciudad Autónoma de Buenos Aires",
      });
    }
    expect(resolverProvincia("Provincia de Buenos Aires")).toEqual({
      estado: "RESUELTA",
      provincia: "Buenos Aires",
    });
  });

  it("NO resuelve 'Buenos Aires' a secas: es ambiguo de verdad", () => {
    // Elegir una haría que Bahía Blanca y Palermo terminaran en el mismo
    // cajón, y nadie lo notaría hasta ver una estadística absurda.
    const r = resolverProvincia("Buenos Aires");
    expect(r.estado).toBe("AMBIGUA");
    if (r.estado === "AMBIGUA") {
      expect(r.candidatas).toHaveLength(2);
      expect(r.motivo).toMatch(/jurisdicciones distintas/);
    }
  });

  it("no inventa: lo que no reconoce queda desconocido", () => {
    for (const v of ["Rosario", "Fisherton", "", null, "Provincia X"]) {
      expect(resolverProvincia(v).estado).toBe("DESCONOCIDA");
    }
  });

  it("es determinista", () => {
    expect(resolverProvincia("Mendoza")).toEqual(resolverProvincia("mendoza"));
  });
});

describe("presentación honesta en el mapa", () => {
  it("sin ubicación no aparece en el mapa", () => {
    expect(presentacionDe("none")).toEqual({ puntoExacto: false, area: false, fueraDelMapa: true });
  });

  it("alta confianza con precisión de calle da un punto", () => {
    expect(presentacionDe("high", "STREET_NUMBER").puntoExacto).toBe(true);
  });

  it("alta confianza sobre un centroide de ciudad NO da un punto", () => {
    // Estar seguros de la ciudad no acerca el punto al inmueble.
    const p = presentacionDe("high", "LOCALITY");
    expect(p.puntoExacto).toBe(false);
    expect(p.area).toBe(true);
  });

  it("lo aproximado y lo dudoso se muestran como área, nunca como punto", () => {
    for (const c of ["approximate", "doubtful"] as const) {
      const p = presentacionDe(c, "ROOFTOP");
      expect(p.puntoExacto).toBe(false);
      expect(p.area).toBe(true);
    }
  });

  it("nunca presenta lo aproximado como exacto", () => {
    for (const c of ["approximate", "doubtful", "none"] as const) {
      for (const pr of GEO_PRECISIONS) {
        expect(presentacionDe(c, pr).puntoExacto).toBe(false);
      }
    }
  });
});
