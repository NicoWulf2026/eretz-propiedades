import { describe, expect, it } from "vitest";
import {
  MUESTRA_MINIMA,
  type Observacion,
  calcularZona,
  confianzaPorTamano,
  diagnosticarMercado,
} from "./market";

/** n observaciones de propiedades distintas, con el valor que se indique. */
function serie(valores: number[], prefijo = "e"): Observacion[] {
  return valores.map((value, i) => ({ propertyEntityId: `${prefijo}-${i}`, value }));
}

/** Una serie homogénea de tamaño n. */
function homogenea(n: number, valor = 100_000): Observacion[] {
  return serie(Array.from({ length: n }, () => valor));
}

describe("muestra insuficiente", () => {
  it("no publica por debajo del mínimo", () => {
    const r = calcularZona(homogenea(MUESTRA_MINIMA - 1));
    expect(r.publicable).toBe(false);
    if (!r.publicable) expect(r.motivo).toMatch(/al menos 30/);
  });

  it("no publica con una serie vacía", () => {
    expect(calcularZona([]).publicable).toBe(false);
  });

  it("el mínimo se exige sobre la muestra final, no sobre la de entrada", () => {
    // Con recorte del 5% por cola, 30 de entrada dejan 28 y no alcanzan. Lo
    // que importa es sobre cuántas observaciones se calculó la cifra que se
    // publica, no cuántas entraron.
    expect(calcularZona(homogenea(MUESTRA_MINIMA)).publicable).toBe(false);
    expect(calcularZona(homogenea(34)).publicable).toBe(true);
  });

  it("sin recorte, el mínimo de entrada alcanza", () => {
    expect(calcularZona(homogenea(MUESTRA_MINIMA), { recorte: 0 }).publicable).toBe(true);
  });

  it("no ofrece un número igual con una advertencia al pie", () => {
    // Una advertencia al lado de un número grande no protege a nadie.
    const r = calcularZona(homogenea(5));
    expect(r.publicable).toBe(false);
    expect(r).not.toHaveProperty("estadistica");
  });
});

describe("se cuentan propiedades, no avisos", () => {
  it("descarta el mismo inmueble publicado varias veces", () => {
    // Tres avisos de la misma propiedad son un inmueble.
    const obs: Observacion[] = [
      ...homogenea(40),
      { propertyEntityId: "e-0", value: 100_000 },
      { propertyEntityId: "e-0", value: 105_000 },
    ];
    const r = calcularZona(obs, { recorte: 0 });
    expect(r.publicable).toBe(true);
    if (r.publicable) {
      expect(r.estadistica.duplicadasDescartadas).toBe(2);
      expect(r.estadistica.n).toBe(40);
    }
  });

  it("una zona con muchos avisos de pocas propiedades no se publica", () => {
    // Es el caso que más engaña: 90 filas que parecen mercado y son 3 inmuebles.
    const obs: Observacion[] = [];
    for (let i = 0; i < 90; i++) obs.push({ propertyEntityId: `e-${i % 3}`, value: 100_000 });
    const r = calcularZona(obs);
    expect(r.publicable).toBe(false);
    if (!r.publicable) expect(r.n).toBe(3);
  });
});

describe("mediana frente a promedio", () => {
  it("un valor extremo mueve el promedio y no la mediana", () => {
    const valores = Array.from({ length: 39 }, () => 90_000);
    valores.push(3_000_000);
    const r = calcularZona(serie(valores), { recorte: 0 });
    expect(r.publicable).toBe(true);
    if (r.publicable) {
      expect(r.estadistica.mediana).toBe(90_000);
      expect(r.estadistica.promedio).toBeGreaterThan(90_000);
    }
  });

  it("informa el promedio igual, para quien lo pida", () => {
    const r = calcularZona(homogenea(40, 100_000));
    if (r.publicable) expect(r.estadistica.promedio).toBeCloseTo(100_000, 6);
    else expect.unreachable("debería publicar");
  });

  it("calcula cuartiles y extremos", () => {
    const r = calcularZona(serie(Array.from({ length: 100 }, (_, i) => i + 1)), { recorte: 0 });
    if (!r.publicable) expect.unreachable("debería publicar");
    else {
      expect(r.estadistica.mediana).toBeCloseTo(50.5, 6);
      expect(r.estadistica.p25).toBeCloseTo(25.75, 6);
      expect(r.estadistica.p75).toBeCloseTo(75.25, 6);
      expect(r.estadistica.minimo).toBe(1);
      expect(r.estadistica.maximo).toBe(100);
    }
  });
});

describe("recorte de colas", () => {
  it("recorta el 5% de cada cola por defecto", () => {
    const r = calcularZona(serie(Array.from({ length: 100 }, (_, i) => i + 1)));
    if (!r.publicable) expect.unreachable("debería publicar");
    else {
      expect(r.estadistica.recortadas).toBe(10);
      expect(r.estadistica.n).toBe(90);
      expect(r.estadistica.minimo).toBe(6);
      expect(r.estadistica.maximo).toBe(95);
    }
  });

  it("recorta después de deduplicar, no antes", () => {
    // Si recortara antes, un aviso repetido contaría varias veces para decidir
    // qué es extremo.
    const obs: Observacion[] = [
      ...serie(Array.from({ length: 60 }, (_, i) => i + 1)),
      { propertyEntityId: "e-0", value: 1 },
      { propertyEntityId: "e-0", value: 1 },
    ];
    const r = calcularZona(obs);
    if (r.publicable) expect(r.estadistica.duplicadasDescartadas).toBe(2);
    else expect.unreachable("debería publicar");
  });

  it("no publica si el recorte deja la muestra por debajo del mínimo", () => {
    const r = calcularZona(homogenea(31), { muestraMinima: 30 });
    expect(r.publicable).toBe(false);
    if (!r.publicable) expect(r.motivo).toMatch(/tras recortar/);
  });
});

describe("valores inválidos", () => {
  it("ignora ceros, negativos y no finitos", () => {
    const obs: Observacion[] = [
      ...homogenea(40),
      { propertyEntityId: "x-1", value: 0 },
      { propertyEntityId: "x-2", value: -5 },
      { propertyEntityId: "x-3", value: Number.NaN },
      { propertyEntityId: "x-4", value: Number.POSITIVE_INFINITY },
    ];
    const r = calcularZona(obs, { recorte: 0 });
    if (r.publicable) expect(r.estadistica.n).toBe(40);
    else expect.unreachable("debería publicar");
  });
});

describe("confianza", () => {
  it("es cualitativa y crece con la muestra", () => {
    expect(confianzaPorTamano(29)).toBe("INSUFICIENTE");
    expect(confianzaPorTamano(30)).toBe("BAJA");
    expect(confianzaPorTamano(60)).toBe("MEDIA");
    expect(confianzaPorTamano(180)).toBe("ALTA");
  });

  it("acompaña siempre a la estadística", () => {
    const r = calcularZona(homogenea(40));
    if (r.publicable) expect(r.estadistica.confianza).toBe("BAJA");
    else expect.unreachable("debería publicar");
  });
});

describe("determinismo", () => {
  it("la misma serie da el mismo resultado", () => {
    const s = serie(Array.from({ length: 80 }, (_, i) => i * 1_000 + 50_000));
    expect(calcularZona(s)).toEqual(calcularZona(s));
  });
});

describe("diagnóstico del catálogo actual", () => {
  it("hoy no se puede publicar Mercado, y dice por qué", () => {
    // Comprobación ejecutable en vez de una opinión en un documento que
    // envejece. Fracciones medidas sobre producción: 65.033/257.073 con
    // coordenadas.
    const d = diagnosticarMercado({
      resolucionDeEntidadesDisponible: false,
      fraccionConUbicacionFiable: 0.253,
      fraccionConPrecioUsd: 0.4,
    });
    expect(d.puedePublicar).toBe(false);
    expect(d.bloqueos).toHaveLength(3);
    expect(d.bloqueos[0]).toMatch(/avisos y no inmuebles/);
    expect(d.bloqueos[1]).toMatch(/25%/);
  });

  it("con las tres condiciones resueltas, habilita", () => {
    const d = diagnosticarMercado({
      resolucionDeEntidadesDisponible: true,
      fraccionConUbicacionFiable: 0.8,
      fraccionConPrecioUsd: 0.7,
    });
    expect(d.puedePublicar).toBe(true);
    expect(d.bloqueos).toEqual([]);
  });

  it("un solo bloqueo alcanza para no publicar", () => {
    const d = diagnosticarMercado({
      resolucionDeEntidadesDisponible: false,
      fraccionConUbicacionFiable: 0.9,
      fraccionConPrecioUsd: 0.9,
    });
    expect(d.puedePublicar).toBe(false);
    expect(d.bloqueos).toHaveLength(1);
  });
});
