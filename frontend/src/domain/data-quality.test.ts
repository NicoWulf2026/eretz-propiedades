import { describe, expect, it } from "vitest";
import {
  SUSPICIOSAS_PARA_CUARENTENA,
  UMBRALES,
  type PublicacionAnalizable,
  analizarCalidad,
} from "./data-quality";

/** Una publicación sana: completa, coherente y con valores normales. */
function sana(overrides: Partial<PublicacionAnalizable> = {}): PublicacionAnalizable {
  return {
    title: "Departamento 2 ambientes en Rosario",
    description: "Luminoso, a estrenar.",
    operation: "venta",
    propertyType: "departamento",
    price: 85_000,
    currency: "USD",
    priceUsd: 85_000,
    expenses: null,
    totalArea: 55,
    coveredArea: 50,
    landArea: null,
    rooms: 2,
    bedrooms: 1,
    bathrooms: 1,
    garages: 0,
    age: 5,
    latitude: -32.95,
    longitude: -60.66,
    city: "Rosario",
    province: "Santa Fe",
    images: ["https://ejemplo.com/1.jpg"],
    ...overrides,
  };
}

const codigos = (p: PublicacionAnalizable) => analizarCalidad(p).anomalies.map((a) => a.code);

describe("publicación sana", () => {
  it("no reporta anomalías", () => {
    const r = analizarCalidad(sana());
    expect(r.verdict).toBe("VALID");
    expect(r.anomalies).toEqual([]);
  });

  it("nunca modifica la entrada", () => {
    // Detectar, no corregir: si se corrigiera, nadie podría distinguir después
    // el dato real del inventado.
    const p = sana({ coveredArea: 900 });
    const copia = structuredClone(p);
    analizarCalidad(p);
    expect(p).toEqual(copia);
  });
});

describe("incoherencias internas: no dependen de suposiciones de mercado", () => {
  it("detecta cubierta mayor que total", () => {
    const r = analizarCalidad(sana({ coveredArea: 80, totalArea: 55 }));
    expect(r.verdict).toBe("INVALID");
    expect(codigos(sana({ coveredArea: 80, totalArea: 55 }))).toContain("CUBIERTA_MAYOR_QUE_TOTAL");
  });

  it("detecta más dormitorios que ambientes", () => {
    const r = analizarCalidad(sana({ rooms: 2, bedrooms: 4 }));
    expect(r.verdict).toBe("INVALID");
    expect(r.anomalies[0].code).toBe("DORMITORIOS_MAYOR_QUE_AMBIENTES");
  });

  it("acepta cubierta igual a total", () => {
    // Frecuente y perfectamente válido en departamentos.
    expect(analizarCalidad(sana({ coveredArea: 55, totalArea: 55 })).verdict).toBe("VALID");
  });

  it("acepta tantos dormitorios como ambientes", () => {
    expect(analizarCalidad(sana({ rooms: 2, bedrooms: 2 })).verdict).toBe("VALID");
  });

  it("los negativos son imposibles, no atípicos", () => {
    for (const campo of ["price", "totalArea", "rooms", "age", "expenses"] as const) {
      const r = analizarCalidad(sana({ [campo]: -5 } as Partial<PublicacionAnalizable>));
      expect(r.verdict).toBe("INVALID");
      expect(r.anomalies.some((a) => a.code === "VALOR_NEGATIVO")).toBe(true);
    }
  });
});

describe("ubicación", () => {
  it("detecta coordenadas fuera de la Argentina", () => {
    const r = analizarCalidad(sana({ latitude: 40.7, longitude: -74 }));
    expect(r.verdict).toBe("INVALID");
    expect(r.anomalies[0].code).toBe("COORDENADAS_FUERA_DE_RANGO");
  });

  it("detecta el (0,0) como caso propio, no como fuera de rango", () => {
    // Tiene causa conocida —un geocoding fallido— y accionable.
    const c = codigos(sana({ latitude: 0, longitude: 0 }));
    expect(c).toContain("COORDENADAS_CERO");
    expect(c).not.toContain("COORDENADAS_FUERA_DE_RANGO");
  });

  it("no reporta nada cuando no hay coordenadas", () => {
    // Ausencia no es error: el 74,7% del catálogo no tiene coordenadas.
    const r = analizarCalidad(sana({ latitude: null, longitude: null }));
    expect(r.anomalies.filter((a) => a.field === "latitude")).toEqual([]);
    expect(r.verdict).toBe("VALID");
  });
});

describe("valores atípicos: raros, no imposibles", () => {
  it("marca un precio de venta muy bajo sin declararlo inválido", () => {
    const r = analizarCalidad(sana({ price: 500, priceUsd: 500 }));
    expect(r.verdict).toBe("SUSPICIOUS");
    expect(r.anomalies[0].code).toBe("PRECIO_VENTA_MUY_BAJO");
  });

  it("no aplica el mínimo de venta a un alquiler", () => {
    // Un alquiler de USD 500 es normal; el mismo número como venta, no.
    const r = analizarCalidad(sana({ operation: "alquiler", price: 500, priceUsd: 500 }));
    expect(r.verdict).toBe("VALID");
  });

  it("marca un alquiler desmesurado", () => {
    const alto = UMBRALES.precioAlquilerUsdMaximo + 1;
    const r = analizarCalidad(sana({ operation: "alquiler", price: alto, priceUsd: alto }));
    expect(r.anomalies[0].code).toBe("ALQUILER_MUY_ALTO");
  });

  it("no evalúa el rango de precio si no se conoce el valor en USD", () => {
    // Convertir con una cotización inventada sería peor que no mirar.
    const r = analizarCalidad(sana({ price: 100, currency: "ARS", priceUsd: null }));
    expect(r.anomalies.filter((a) => a.field === "price")).toEqual([]);
  });

  it("exceptúa al campo del máximo de superficie", () => {
    const enorme = UMBRALES.superficieMaximaM2 * 5;
    expect(codigos(sana({ propertyType: "campo", totalArea: enorme }))).not.toContain(
      "SUPERFICIE_MUY_GRANDE",
    );
    expect(codigos(sana({ propertyType: "casa", totalArea: enorme }))).toContain("SUPERFICIE_MUY_GRANDE");
  });

  it("marca superficies diminutas", () => {
    expect(codigos(sana({ totalArea: 4, coveredArea: 4 }))).toContain("SUPERFICIE_MUY_CHICA");
  });

  it("marca conteos desmesurados", () => {
    expect(codigos(sana({ rooms: 99, bedrooms: 1 }))).toContain("AMBIENTES_EXCESIVOS");
    expect(codigos(sana({ bathrooms: 99 }))).toContain("BANOS_EXCESIVOS");
    expect(codigos(sana({ age: 999 }))).toContain("ANTIGUEDAD_EXCESIVA");
  });

  it("respeta los umbrales exactos: el límite no es anomalía", () => {
    expect(codigos(sana({ rooms: UMBRALES.ambientesMaximo, bedrooms: 1 }))).not.toContain(
      "AMBIENTES_EXCESIVOS",
    );
    expect(codigos(sana({ rooms: UMBRALES.ambientesMaximo + 1, bedrooms: 1 }))).toContain(
      "AMBIENTES_EXCESIVOS",
    );
  });

  it("marca expensas desproporcionadas sólo en alquiler", () => {
    const p = { operation: "alquiler", price: 100_000, priceUsd: 100, expenses: 500_000 };
    expect(codigos(sana(p))).toContain("EXPENSAS_DESPROPORCIONADAS");
    expect(codigos(sana({ ...p, operation: "venta" }))).not.toContain("EXPENSAS_DESPROPORCIONADAS");
  });
});

describe("precio a consultar vs precio a medias", () => {
  it("acepta una publicación sin precio", () => {
    // "A consultar" es legítimo y frecuente.
    const r = analizarCalidad(sana({ price: null, priceUsd: null, currency: null }));
    expect(r.verdict).toBe("VALID");
  });

  it("marca un precio sin moneda", () => {
    expect(codigos(sana({ currency: null }))).toContain("PRECIO_SIN_MONEDA");
  });

  it("marca un precio en 0, que no es gratis sino un campo sin llenar", () => {
    expect(codigos(sana({ price: 0, priceUsd: null }))).toContain("PRECIO_CERO");
  });
});

describe("campos ausentes: incompleto no es erróneo", () => {
  it("no invalida una publicación por faltarle fotos", () => {
    // Tratarla como inválida sacaría del catálogo publicaciones reales.
    const r = analizarCalidad(sana({ images: [] }));
    expect(r.verdict).toBe("VALID");
    expect(r.anomalies[0].severity).toBe("INFO");
  });

  it("reporta cada campo esencial ausente", () => {
    const vacia = sana({ title: null, operation: null, propertyType: null, city: null, images: [] });
    const info = analizarCalidad(vacia).anomalies.filter((a) => a.severity === "INFO");
    expect(info).toHaveLength(5);
  });

  it("no confunde un título en blanco con un título presente", () => {
    expect(codigos(sana({ title: "   " }))).toContain("CAMPO_ESENCIAL_AUSENTE");
  });
});

describe("veredicto", () => {
  it("una incoherencia manda a INVALID aunque haya muchas sospechas", () => {
    const r = analizarCalidad(sana({ coveredArea: 900, rooms: 99, bedrooms: 1, age: 999 }));
    expect(r.verdict).toBe("INVALID");
  });

  it("varias señales atípicas a la vez mandan a cuarentena", () => {
    const r = analizarCalidad(sana({ price: 1, priceUsd: 1, totalArea: 2, coveredArea: 1, age: 999 }));
    expect(r.anomalies.filter((a) => a.severity === "SUSPICIOUS").length).toBeGreaterThanOrEqual(
      SUSPICIOSAS_PARA_CUARENTENA,
    );
    expect(r.verdict).toBe("QUARANTINE");
  });

  it("una sola señal atípica no llega a cuarentena", () => {
    expect(analizarCalidad(sana({ age: 999 })).verdict).toBe("SUSPICIOUS");
  });

  it("siempre explica el veredicto", () => {
    for (const p of [sana(), sana({ age: 999 }), sana({ coveredArea: 900 })]) {
      expect(analizarCalidad(p).reason.length).toBeGreaterThan(0);
    }
  });

  it("las anomalías viajan siempre con el veredicto", () => {
    // Un veredicto sin razones no se puede discutir ni corregir.
    const r = analizarCalidad(sana({ coveredArea: 900 }));
    expect(r.anomalies.length).toBeGreaterThan(0);
    expect(r.anomalies.every((a) => a.detail.length > 0 && a.code.length > 0)).toBe(true);
  });

  it("es determinista", () => {
    const p = sana({ age: 999, price: 1, priceUsd: 1 });
    expect(analizarCalidad(p)).toEqual(analizarCalidad(p));
  });
});
