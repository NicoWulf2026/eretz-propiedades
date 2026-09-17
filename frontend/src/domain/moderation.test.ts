import { describe, expect, it } from "vitest";
import { type PublicacionAnalizable, analizarCalidad } from "./data-quality";
import type { ListingOrigin } from "./listing";
import {
  MEDIAS_PARA_ESCALAR,
  UMBRALES_TEXTO,
  type DuplicateSignal,
  type EntradaDeModeracion,
  analizarTexto,
  moderar,
  permiteMostrar,
} from "./moderation";

function publicacion(o: Partial<PublicacionAnalizable> = {}): PublicacionAnalizable {
  return {
    title: "Departamento 2 ambientes en Rosario",
    description: "Luminoso, con balcón al frente y cocina separada. A dos cuadras del río.",
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
    ...o,
  };
}

function entrada(o: Partial<EntradaDeModeracion> = {}): EntradaDeModeracion {
  const pub = o.quality ? null : publicacion();
  return {
    origin: "SCRAPED",
    publisher: "IDENTIFIED",
    quality: analizarCalidad(pub ?? publicacion()),
    duplicate: "NO_MATCH",
    title: "Departamento 2 ambientes en Rosario",
    description: "Luminoso, con balcón al frente y cocina separada. A dos cuadras del río.",
    sourceHost: "inmobiliaria.com.ar",
    hasContact: true,
    imageCount: 4,
    ...o,
  };
}

const codigos = (e: EntradaDeModeracion) => moderar(e).signals.map((s) => s.code);

describe("publicación sana", () => {
  it("una publicación completa y válida se permite", () => {
    const r = moderar(entrada());
    expect(r.decision).toBe("ALLOW");
    expect(r.signals).toEqual([]);
  });

  it("precio ausente con 'a consultar' sigue siendo válida", () => {
    // Es una decisión comercial legítima y frecuente.
    const q = analizarCalidad(publicacion({ price: null, priceUsd: null, currency: null }));
    expect(moderar(entrada({ quality: q })).decision).toBe("ALLOW");
  });

  it("siempre explica la decisión", () => {
    expect(moderar(entrada()).explanation.length).toBeGreaterThan(0);
  });
});

describe("la misma señal, distinta acción según el origen", () => {
  // Es la decisión central del módulo.
  const rota = () => analizarCalidad(publicacion({ coveredArea: 900, totalArea: 55 }));

  it("una carga manual con datos contradictorios se rechaza", () => {
    // Cuesta poco: quien la cargó lo corrige y vuelve a enviar.
    expect(moderar(entrada({ origin: "MANUAL", quality: rota() })).decision).toBe("REJECT");
    expect(moderar(entrada({ origin: "API", quality: rota() })).decision).toBe("REJECT");
  });

  it("la misma publicación scrapeada va a revisión, no se bloquea", () => {
    // Bloquearla escondería una propiedad que existe y está publicada en su
    // fuente, y nadie se entera de lo que falta.
    const r = moderar(entrada({ origin: "SCRAPED", quality: rota() }));
    expect(r.decision).toBe("REVIEW");
    expect(r.explanation).toMatch(/escondería una propiedad que existe/);
  });

  it("lo importado se trata como lo scrapeado", () => {
    expect(moderar(entrada({ origin: "IMPORTED", quality: rota() })).decision).toBe("REVIEW");
  });

  it("las señales son idénticas: lo que cambia es la acción", () => {
    const manual = moderar(entrada({ origin: "MANUAL", quality: rota() }));
    const scraped = moderar(entrada({ origin: "SCRAPED", quality: rota() }));
    expect(manual.signals.map((s) => s.code)).toEqual(scraped.signals.map((s) => s.code));
    expect(manual.decision).not.toBe(scraped.decision);
  });
});

describe("raro no es inválido", () => {
  it("un valor atípico solo no bloquea ni siquiera en manual", () => {
    // 12 m² puede existir.
    const q = analizarCalidad(publicacion({ totalArea: 8, coveredArea: 8 }));
    const r = moderar(entrada({ origin: "MANUAL", quality: q }));
    expect(r.decision).toBe("REVIEW");
    expect(permiteMostrar(r.decision)).toBe(true);
  });

  it("varias rarezas a la vez sí escalan", () => {
    const q = analizarCalidad(publicacion({ totalArea: 2, coveredArea: 1, age: 999, price: 1, priceUsd: 1 }));
    const r = moderar(entrada({ origin: "MANUAL", quality: q }));
    expect(r.signals.filter((s) => s.severity === "MEDIUM").length).toBeGreaterThanOrEqual(
      MEDIAS_PARA_ESCALAR,
    );
    expect(r.decision).toBe("REJECT");
  });

  it("dormitorios y baños extremos se detectan sin bloquear una scrapeada", () => {
    const q = analizarCalidad(publicacion({ rooms: 99, bedrooms: 1, bathrooms: 99 }));
    const r = moderar(entrada({ quality: q }));
    expect(codigos(entrada({ quality: q }))).toContain("AMBIENTES_EXCESIVOS");
    expect(r.decision).not.toBe("REJECT");
  });
});

describe("duplicados", () => {
  it("un duplicado confirmado se bloquea venga de donde venga", () => {
    // No se pierde la propiedad: ya está en el catálogo bajo la otra publicación.
    for (const origin of ["SCRAPED", "MANUAL", "IMPORTED", "API"] as ListingOrigin[]) {
      const r = moderar(entrada({ origin, duplicate: "CONFIRMED" }));
      expect(r.decision).toBe("REJECT");
      expect(r.explanation).toMatch(/duplicado confirmado/);
    }
  });

  it("un duplicado probable va a revisión, no se bloquea", () => {
    const r = moderar(entrada({ duplicate: "HIGH_CONFIDENCE" }));
    expect(r.decision).toBe("REVIEW");
    expect(permiteMostrar(r.decision)).toBe(true);
  });

  it("un duplicado posible se anota pero no cambia la decisión", () => {
    const r = moderar(entrada({ duplicate: "POSSIBLE_MATCH" }));
    expect(r.decision).toBe("ALLOW");
    expect(r.signals.map((s) => s.code)).toContain("DUPLICADO_POSIBLE");
  });

  it("sin coincidencia no genera señal", () => {
    expect(codigos(entrada({ duplicate: "NO_MATCH" as DuplicateSignal }))).toEqual([]);
  });
});

describe("señales estructurales", () => {
  it("sin contacto es señal media", () => {
    const r = moderar(entrada({ hasContact: false }));
    expect(r.signals.find((s) => s.code === "SIN_CONTACTO")?.severity).toBe("MEDIUM");
    expect(r.decision).toBe("REVIEW");
  });

  it("sin imágenes es señal baja y no cambia la decisión", () => {
    // Reduce su utilidad, no la vuelve falsa.
    const r = moderar(entrada({ imageCount: 0 }));
    expect(r.signals.find((s) => s.code === "SIN_IMAGENES")?.severity).toBe("LOW");
    expect(r.decision).toBe("ALLOW");
  });

  it("una publicación sin ubicación no se bloquea", () => {
    // El 74,7% del catálogo no tiene coordenadas.
    const q = analizarCalidad(publicacion({ latitude: null, longitude: null }));
    expect(moderar(entrada({ quality: q })).decision).toBe("ALLOW");
  });
});

describe("spam determinista", () => {
  it("detecta texto todo en mayúsculas", () => {
    const s = analizarTexto("OPORTUNIDAD UNICA", "DEPARTAMENTO IMPERDIBLE EN ZONA PREMIUM LLAME YA", null);
    expect(s.map((x) => x.code)).toContain("TEXTO_EN_MAYUSCULAS");
  });

  it("no marca por mayúsculas un texto corto", () => {
    // "PH" o "USD" no son gritos.
    expect(analizarTexto("PH EN VENTA", null, null).map((x) => x.code)).not.toContain(
      "TEXTO_EN_MAYUSCULAS",
    );
  });

  it("detecta caracteres repetidos", () => {
    const s = analizarTexto("Depto", "Excelente!!!!!!!! oportunidad de inversión en el centro", null);
    expect(s.map((x) => x.code)).toContain("CARACTERES_REPETIDOS");
  });

  it("tolera el énfasis normal de la escritura comercial", () => {
    // Cada falso positivo esconde una publicación legítima.
    const s = analizarTexto("Depto", "¡Excelente oportunidad!! Muy luminoso y bien ubicado.", null);
    expect(s.map((x) => x.code)).not.toContain("CARACTERES_REPETIDOS");
  });

  it("detecta relleno de palabras clave", () => {
    const relleno = Array.from({ length: UMBRALES_TEXTO.repeticionDePalabra }, () => "rosario").join(" ");
    const s = analizarTexto("Depto", `Venta ${relleno} centro`, null);
    expect(s.map((x) => x.code)).toContain("RELLENO_DE_PALABRAS");
  });

  it("no marca la repetición natural de la zona", () => {
    const s = analizarTexto(
      "Depto en Rosario",
      "Ubicado en Rosario, a metros del centro de Rosario. Zona tranquila.",
      null,
    );
    expect(s.map((x) => x.code)).not.toContain("RELLENO_DE_PALABRAS");
  });

  it("no cuenta como externos los enlaces al propio sitio", () => {
    // Sin sourceHost no se puede distinguir el enlace propio del ajeno.
    const s = analizarTexto(
      "Depto",
      "Ver más en https://lopez.com.ar/p/1 y en https://www.lopez.com.ar/contacto",
      "lopez.com.ar",
    );
    expect(s.map((x) => x.code)).not.toContain("ENLACES_EXTERNOS");
  });

  it("detecta varios dominios ajenos", () => {
    const s = analizarTexto(
      "Depto",
      "Visitá https://otrositio.com y https://tercero.net para más ofertas",
      "lopez.com.ar",
    );
    expect(s.map((x) => x.code)).toContain("ENLACES_EXTERNOS");
  });

  it("un solo dominio ajeno no alcanza", () => {
    const s = analizarTexto("Depto", "Ver plano en https://planos.com/x", "lopez.com.ar");
    expect(s.map((x) => x.code)).not.toContain("ENLACES_EXTERNOS");
  });

  it("detecta una descripción que sólo repite el título", () => {
    const s = analizarTexto("Departamento 2 ambientes", "departamento 2 ambientes", null);
    expect(s.map((x) => x.code)).toContain("DESCRIPCION_REPITE_TITULO");
  });

  it("detecta una descripción demasiado breve", () => {
    expect(analizarTexto("Depto en venta", "Lindo", null).map((x) => x.code)).toContain(
      "DESCRIPCION_INSUFICIENTE",
    );
  });

  it("sin texto no inventa señales", () => {
    expect(analizarTexto(null, null, null)).toEqual([]);
    expect(analizarTexto("", "", null)).toEqual([]);
  });
});

describe("evidencia y explicación", () => {
  it("toda señal trae código, evidencia y explicación", () => {
    const q = analizarCalidad(publicacion({ coveredArea: 900 }));
    const r = moderar(entrada({ quality: q, hasContact: false, imageCount: 0 }));
    expect(r.signals.length).toBeGreaterThan(0);
    for (const s of r.signals) {
      expect(s.code.length).toBeGreaterThan(0);
      expect(s.evidence.length).toBeGreaterThan(0);
      expect(s.explanation.length).toBeGreaterThan(0);
    }
  });

  it("no convierte los campos ausentes en señales de moderación", () => {
    // Ya se cubren con señales estructurales propias; duplicarlos inflaría el
    // conteo que decide escalar.
    const q = analizarCalidad(publicacion({ images: [] }));
    expect(moderar(entrada({ quality: q, imageCount: 0 })).signals.map((s) => s.code)).not.toContain(
      "CAMPO_ESENCIAL_AUSENTE",
    );
  });

  it("es determinista", () => {
    const e = entrada({ duplicate: "HIGH_CONFIDENCE" });
    expect(moderar(e)).toEqual(moderar(e));
  });
});

describe("qué oculta cada decisión", () => {
  it("REVIEW muestra: significa 'que alguien la mire', no 'que no se vea'", () => {
    // Si REVIEW ocultara, cualquier señal media sacaría miles de publicaciones
    // reales del catálogo sin que nadie lo note.
    expect(permiteMostrar("REVIEW")).toBe(true);
    expect(permiteMostrar("ALLOW")).toBe(true);
    expect(permiteMostrar("REJECT")).toBe(false);
  });
});
