import { describe, expect, it } from "vitest";
import { type PublicacionAnalizable, analizarCalidad } from "./data-quality";
import {
  BANDAS,
  FOTOS_PARA_PUNTAJE_PLENO,
  PESOS,
  type EntradaDeScore,
  bandaDeScore,
  calcularScore,
} from "./quality-score";

function publicacion(o: Partial<PublicacionAnalizable> = {}): PublicacionAnalizable {
  return {
    title: "Departamento 2 ambientes",
    description: "Luminoso y bien ubicado.",
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
    images: ["1.jpg"],
    ...o,
  };
}

function entrada(o: Partial<EntradaDeScore> = {}): EntradaDeScore {
  return {
    quality: analizarCalidad(publicacion()),
    locationConfidence: "high",
    imageCount: 8,
    hasDescription: true,
    descriptionLength: 250,
    hasPrice: true,
    hasContact: true,
    presentAttributes: {
      propertyType: true,
      operation: true,
      totalArea: true,
      rooms: true,
      bedrooms: true,
      bathrooms: true,
    },
    publisherIdentified: true,
    publisherVerified: true,
    ...o,
  };
}

describe("puntaje perfecto", () => {
  it("una publicación impecable llega a 1", () => {
    expect(calcularScore(entrada()).overall).toBeCloseTo(1, 6);
  });

  it("los pesos suman 1", () => {
    const suma = Object.values(PESOS).reduce((a, b) => a + b, 0);
    expect(suma).toBeCloseTo(1, 10);
  });

  it("el resultado siempre queda entre 0 y 1", () => {
    const casos = [
      entrada(),
      entrada({ locationConfidence: "none", imageCount: 0, hasDescription: false, descriptionLength: 0 }),
      entrada({ quality: analizarCalidad(publicacion({ coveredArea: 900, rooms: 99, bedrooms: 1 })) }),
    ];
    for (const c of casos) {
      const s = calcularScore(c);
      expect(s.overall).toBeGreaterThanOrEqual(0);
      expect(s.overall).toBeLessThanOrEqual(1);
    }
  });
});

describe("explicabilidad", () => {
  it("nunca devuelve sólo un número", () => {
    const s = calcularScore(entrada({ imageCount: 0 }));
    for (const dim of [s.completeness, s.consistency, s.location, s.media, s.publisherConfidence]) {
      expect(dim.reasons.length).toBeGreaterThan(0);
      expect(dim.score).toBeGreaterThanOrEqual(0);
      expect(dim.score).toBeLessThanOrEqual(1);
    }
  });

  it("señala la dimensión más floja, que es lo accionable", () => {
    const s = calcularScore(entrada({ locationConfidence: "none" }));
    expect(s.explanation).toMatch(/ubicación/);
  });

  it("cuando todo está bien, lo dice", () => {
    expect(calcularScore(entrada()).explanation).toMatch(/todas las dimensiones/);
  });
});

describe("completitud", () => {
  it("sin operación o sin tipo cae a cero: la publicación no se puede ni filtrar", () => {
    const s = calcularScore(
      entrada({ presentAttributes: { ...entrada().presentAttributes, operation: false } }),
    );
    expect(s.completeness.score).toBe(0);
    expect(s.completeness.reasons[0]).toMatch(/imprescindibles/);
  });

  it("nombra qué falta", () => {
    const s = calcularScore(entrada({ hasPrice: false, hasContact: false }));
    expect(s.completeness.reasons.join(" ")).toMatch(/precio/);
    expect(s.completeness.reasons.join(" ")).toMatch(/contacto/);
  });

  it("baja proporcionalmente con lo ausente", () => {
    const completa = calcularScore(entrada()).completeness.score;
    const incompleta = calcularScore(entrada({ hasPrice: false })).completeness.score;
    expect(incompleta).toBeLessThan(completa);
  });
});

describe("coherencia pesa más que completitud", () => {
  it("una contradicción hunde más el puntaje que un campo ausente", () => {
    // Un dato que se contradice es peor que un dato que falta: hace desconfiar
    // del resto.
    const faltaUnCampo = calcularScore(entrada({ hasPrice: false })).overall;
    const contradictoria = calcularScore({
      ...entrada(),
      quality: analizarCalidad(publicacion({ coveredArea: 900, totalArea: 55 })),
    }).overall;
    expect(contradictoria).toBeLessThan(faltaUnCampo);
    expect(PESOS.consistency).toBeGreaterThan(PESOS.completeness);
  });

  it("una rareza penaliza mucho menos que una contradicción", () => {
    const rara = calcularScore({
      ...entrada(),
      quality: analizarCalidad(publicacion({ age: 999 })),
    }).consistency.score;
    const rota = calcularScore({
      ...entrada(),
      quality: analizarCalidad(publicacion({ coveredArea: 900, totalArea: 55 })),
    }).consistency.score;
    expect(rara).toBeGreaterThan(rota);
    expect(rara).toBeGreaterThan(0.8);
  });

  it("dos contradicciones dejan la coherencia en cero", () => {
    const s = calcularScore({
      ...entrada(),
      quality: analizarCalidad(publicacion({ coveredArea: 900, totalArea: 55, rooms: 2, bedrooms: 9 })),
    });
    expect(s.consistency.score).toBe(0);
  });

  it("lista las anomalías que la penalizaron", () => {
    const s = calcularScore({
      ...entrada(),
      quality: analizarCalidad(publicacion({ coveredArea: 900, totalArea: 55 })),
    });
    expect(s.consistency.reasons.join(" ")).toMatch(/CUBIERTA_MAYOR_QUE_TOTAL/);
  });
});

describe("ubicación", () => {
  it("respeta la semántica de cuatro niveles ya existente", () => {
    const de = (c: EntradaDeScore["locationConfidence"]) =>
      calcularScore(entrada({ locationConfidence: c })).location.score;
    expect(de("high")).toBe(1);
    expect(de("approximate")).toBeCloseTo(0.6, 6);
    expect(de("doubtful")).toBeCloseTo(0.3, 6);
    expect(de("none")).toBe(0);
  });

  it("nunca presenta aproximada como exacta", () => {
    expect(calcularScore(entrada({ locationConfidence: "approximate" })).location.reasons[0]).toMatch(
      /aproximada/,
    );
  });
});

describe("fotos y texto", () => {
  it("el puntaje por fotos satura, para no premiar subir treinta iguales", () => {
    const seis = calcularScore(entrada({ imageCount: FOTOS_PARA_PUNTAJE_PLENO })).media.score;
    const treinta = calcularScore(entrada({ imageCount: 30 })).media.score;
    expect(treinta).toBe(seis);
  });

  it("la diferencia entre ninguna y algunas fotos es grande", () => {
    const cero = calcularScore(entrada({ imageCount: 0 })).media.score;
    const tres = calcularScore(entrada({ imageCount: 3 })).media.score;
    expect(tres - cero).toBeGreaterThan(0.3);
  });

  it("las fotos pesan más que el texto", () => {
    const soloFotos = calcularScore(
      entrada({ imageCount: 8, hasDescription: false, descriptionLength: 0 }),
    ).media.score;
    const soloTexto = calcularScore(entrada({ imageCount: 0, descriptionLength: 250 })).media.score;
    expect(soloFotos).toBeGreaterThan(soloTexto);
  });
});

describe("publicador", () => {
  it("no castiga fuerte al no identificado: es una carencia nuestra", () => {
    // Casi todo el catálogo actual lo es, y no por defecto de la publicación.
    const s = calcularScore(entrada({ publisherIdentified: false }));
    expect(s.publisherConfidence.score).toBeGreaterThan(0);
    expect(PESOS.publisherConfidence).toBeLessThan(PESOS.consistency);
  });

  it("distingue verificación no evaluada de verificación fallida", () => {
    // null no es false.
    const noEvaluada = calcularScore(entrada({ publisherVerified: null }));
    const sinVerificar = calcularScore(entrada({ publisherVerified: false }));
    expect(noEvaluada.publisherConfidence.reasons[0]).toMatch(/no evaluada/);
    expect(sinVerificar.publisherConfidence.reasons[0]).toMatch(/sin verificar/);
  });

  it("premia al verificado", () => {
    expect(calcularScore(entrada({ publisherVerified: true })).publisherConfidence.score).toBe(1);
  });
});

describe("bandas para operaciones", () => {
  it("clasifica en tres bandas", () => {
    expect(bandaDeScore(0.9)).toBe("ALTA");
    expect(bandaDeScore(0.6)).toBe("MEDIA");
    expect(bandaDeScore(0.2)).toBe("BAJA");
    expect(BANDAS).toHaveLength(3);
  });

  it("respeta los cortes exactos", () => {
    expect(bandaDeScore(0.75)).toBe("ALTA");
    expect(bandaDeScore(0.749)).toBe("MEDIA");
    expect(bandaDeScore(0.45)).toBe("MEDIA");
    expect(bandaDeScore(0.449)).toBe("BAJA");
  });
});

describe("determinismo", () => {
  it("la misma entrada da el mismo puntaje", () => {
    const e = entrada({ imageCount: 3, locationConfidence: "approximate" });
    expect(calcularScore(e)).toEqual(calcularScore(e));
  });

  it("no hay pesos aprendidos: están escritos y son inspeccionables", () => {
    expect(Object.keys(PESOS).sort()).toEqual([
      "completeness",
      "consistency",
      "location",
      "media",
      "publisherConfidence",
    ]);
  });
});
