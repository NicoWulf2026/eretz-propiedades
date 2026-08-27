import { describe, expect, it } from "vitest";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";
import type { SupabaseProperty } from "@/types/property";
import {
  UMBRALES_DIAGNOSTICOS,
  advertencias,
  aplanarResumen,
  evaluarLote,
  type ParaEvaluar,
  type ResumenShadow,
} from "./evaluate";
import type { ConfiguracionShadow } from "./flag";

const ENCENDIDO: ConfiguracionShadow = { activo: true, fraccion: 1 };
const APAGADO: ConfiguracionShadow = { activo: false, fraccion: 0 };

function entrada(o: Partial<SupabaseProperty> = {}): ParaEvaluar {
  const item = { ...completeRow, ...o };
  return { property: mapSupabasePropertyToProperty(item), item };
}

/** n propiedades sanas con ids distintos. */
const lote = (n: number, o: Partial<SupabaseProperty> = {}): ParaEvaluar[] =>
  Array.from({ length: n }, (_, i) => entrada({ ...o, id: 1000 + i }));

describe("la flag manda", () => {
  it("apagada no evalúa nada", () => {
    expect(evaluarLote(lote(5), APAGADO)).toBeNull();
  });

  it("con lote vacío tampoco produce resumen", () => {
    expect(evaluarLote([], ENCENDIDO)).toBeNull();
  });

  it("encendida evalúa", () => {
    const r = evaluarLote(lote(5), ENCENDIDO);
    expect(r?.evaluadas).toBe(5);
  });

  it("respeta el muestreo y cuenta lo omitido", () => {
    const r = evaluarLote(lote(200), { activo: true, fraccion: 0.3 });
    expect(r).not.toBeNull();
    expect((r as ResumenShadow).evaluadas + (r as ResumenShadow).omitidas).toBe(200);
    expect((r as ResumenShadow).evaluadas).toBeLessThan(200);
  });

  it("con fracción 0 no evalúa ninguna", () => {
    const r = evaluarLote(lote(20), { activo: true, fraccion: 0 });
    expect(r?.evaluadas).toBe(0);
    expect(r?.omitidas).toBe(20);
    expect(r?.puntaje).toBeNull();
  });
});

describe("no muta lo que evalúa", () => {
  it("las propiedades y las filas quedan intactas", () => {
    // Es la garantía central del modo sombra.
    const l = lote(5);
    const copia = structuredClone(l);
    evaluarLote(l, ENCENDIDO);
    expect(l).toEqual(copia);
  });

  it("el resumen no contiene ninguna propiedad", () => {
    // Estructuralmente imposible usarlo para decidir: no hay por dónde.
    const r = evaluarLote(lote(3), ENCENDIDO) as ResumenShadow;
    const json = JSON.stringify(r);
    expect(json).not.toContain("Casa luminosa");
    expect(json).not.toContain("descripción");
    expect(r).not.toHaveProperty("properties");
    expect(r).not.toHaveProperty("items");
  });
});

describe("determinismo", () => {
  it("el mismo lote da el mismo resumen", () => {
    const l = lote(10);
    expect(evaluarLote(l, ENCENDIDO)).toEqual(evaluarLote(l, ENCENDIDO));
  });

  it("la muestra es estable entre corridas", () => {
    const l = lote(100);
    const a = evaluarLote(l, { activo: true, fraccion: 0.4 }) as ResumenShadow;
    const b = evaluarLote(l, { activo: true, fraccion: 0.4 }) as ResumenShadow;
    expect(a.evaluadas).toBe(b.evaluadas);
  });
});

describe("distribuciones", () => {
  it("los conteos de moderación suman lo evaluado", () => {
    const r = evaluarLote(lote(12), ENCENDIDO) as ResumenShadow;
    const { ALLOW, REVIEW, REJECT } = r.moderacion;
    expect(ALLOW + REVIEW + REJECT).toBe(r.evaluadas);
  });

  it("los conteos de calidad de datos también", () => {
    const r = evaluarLote(lote(12), ENCENDIDO) as ResumenShadow;
    const { VALID, SUSPICIOUS, INVALID, QUARANTINE } = r.calidadDeDatos;
    expect(VALID + SUSPICIOUS + INVALID + QUARANTINE).toBe(r.evaluadas);
  });

  it("los percentiles del puntaje están ordenados y en rango", () => {
    const r = evaluarLote(lote(20), ENCENDIDO) as ResumenShadow;
    const p = r.puntaje as NonNullable<ResumenShadow["puntaje"]>;
    expect(p.p10).toBeLessThanOrEqual(p.p50);
    expect(p.p50).toBeLessThanOrEqual(p.p90);
    for (const v of [p.p10, p.p50, p.p90, ...Object.values(p.dimensiones)]) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
  });

  it("segmenta por origen", () => {
    const mezcla = [
      ...lote(3, { fuente_extraccion: "public" }),
      ...Array.from({ length: 2 }, (_, i) =>
        entrada({ id: 5000 + i, fuente_extraccion: null, cms_origen: null }),
      ),
    ];
    const r = evaluarLote(mezcla, ENCENDIDO) as ResumenShadow;
    expect(r.porOrigen.SCRAPED.evaluadas).toBe(3);
    expect(r.porOrigen.UNKNOWN.evaluadas).toBe(2);
  });

  it("acumula razones con ejemplos acotados", () => {
    const sinFotos = lote(10, { imagenes: null });
    const r = evaluarLote(sinFotos, ENCENDIDO) as ResumenShadow;
    const razon = r.razones.find((x) => x.code === "SIN_IMAGENES");
    expect(razon?.count).toBe(10);
    expect(razon?.ejemplos.length).toBeLessThanOrEqual(3);
  });

  it("ordena las razones de mayor a menor y desempata estable", () => {
    const r = evaluarLote(lote(10, { imagenes: null, agente_telefono: null, publisher_phone: null, publisher_email: null, publisher_website: null, agente_nombre: null, publisher_name: null }), ENCENDIDO) as ResumenShadow;
    const counts = r.razones.map((x) => x.count);
    expect([...counts].sort((a, b) => b - a)).toEqual(counts);
  });
});

describe("una publicación sana no dispara nada", () => {
  it("el fixture completo pasa como ALLOW y VALID", () => {
    const r = evaluarLote(lote(1), ENCENDIDO) as ResumenShadow;
    expect(r.moderacion.ALLOW).toBe(1);
    expect(r.calidadDeDatos.VALID).toBe(1);
    expect(r.razones).toEqual([]);
  });
});

describe("aplanado para el log", () => {
  it("todo campo del aplanado es escalar", () => {
    // `logEvent` descarta en silencio lo que no sea string, número o booleano:
    // un objeto anidado no da error, simplemente no aparece.
    const r = evaluarLote(lote(6, { imagenes: null }), ENCENDIDO) as ResumenShadow;
    for (const [clave, valor] of Object.entries(aplanarResumen(r))) {
      expect(["string", "number"], `${clave} no es escalar`).toContain(typeof valor);
    }
  });

  it("conserva los conteos", () => {
    const r = evaluarLote(lote(6), ENCENDIDO) as ResumenShadow;
    const plano = aplanarResumen(r);
    expect(plano.evaluadas).toBe(6);
    expect(plano.mod_allow).toBe(r.moderacion.ALLOW);
    expect(plano.dq_valid).toBe(r.calidadDeDatos.VALID);
  });

  it("codifica razones y orígenes de forma legible", () => {
    const r = evaluarLote(lote(4, { imagenes: null }), ENCENDIDO) as ResumenShadow;
    const plano = aplanarResumen(r);
    expect(String(plano.razon_1)).toMatch(/^SIN_IMAGENES:4:/);
    expect(String(plano.origen_SCRAPED)).toBe("4/0/0");
  });

  it("omite el puntaje cuando no se evaluó nada", () => {
    const r = evaluarLote(lote(4), { activo: true, fraccion: 0 }) as ResumenShadow;
    expect(aplanarResumen(r)).not.toHaveProperty("score_p50");
  });
});

describe("umbrales de diagnóstico", () => {
  it("no disparan con una muestra sana", () => {
    const r = evaluarLote(lote(10), ENCENDIDO) as ResumenShadow;
    expect(advertencias(r)).toEqual([]);
  });

  it("avisan cuando demasiadas van a revisión", () => {
    // Sin contacto, todas caen en REVIEW.
    const r = evaluarLote(
      lote(10, {
        publisher_name: null, publisher_phone: null, publisher_email: null,
        publisher_website: null, agente_nombre: null, agente_telefono: null,
      }),
      ENCENDIDO,
    ) as ResumenShadow;
    expect(r.moderacion.REVIEW).toBe(10);
    expect(advertencias(r).map((a) => a.code)).toContain("REVIEW_ALTO");
  });

  it("avisan cuando una sola razón domina", () => {
    const r = evaluarLote(lote(10, { imagenes: null }), ENCENDIDO) as ResumenShadow;
    expect(advertencias(r).map((a) => a.code)).toContain("RAZON_DOMINANTE");
  });

  it("son diagnósticos: no cambian el resumen ni ocultan nada", () => {
    const r = evaluarLote(lote(10, { imagenes: null }), ENCENDIDO) as ResumenShadow;
    const copia = structuredClone(r);
    advertencias(r);
    expect(r).toEqual(copia);
  });

  it("con nada evaluado no inventa advertencias", () => {
    const r = evaluarLote(lote(5), { activo: true, fraccion: 0 }) as ResumenShadow;
    expect(advertencias(r)).toEqual([]);
  });

  it("los umbrales son explícitos y revisables", () => {
    expect(UMBRALES_DIAGNOSTICOS.fraccionRejectMaxima).toBeLessThan(
      UMBRALES_DIAGNOSTICOS.fraccionReviewMaxima,
    );
  });
});
