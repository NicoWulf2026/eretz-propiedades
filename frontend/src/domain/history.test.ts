import { describe, expect, it } from "vitest";
import { listingId } from "./ids";
import {
  type ListingSnapshot,
  type MarcasDeTiempo,
  compararSnapshots,
  esFechaDePublicacionLegitima,
  fechaParaMostrar,
  historialDeCambios,
  resumirPrecio,
  tieneHistoria,
} from "./history";

const L = listingId("l-1");

function snap(observedAt: string, o: Partial<ListingSnapshot> = {}): ListingSnapshot {
  return {
    listingId: L,
    observedAt,
    price: 100_000,
    currency: "USD",
    expenses: null,
    availability: "ACTIVE",
    publisherKey: "lopez",
    source: "run-1",
    ...o,
  };
}

function marcas(o: Partial<MarcasDeTiempo> = {}): MarcasDeTiempo {
  return {
    publishedAt: null,
    sourceUpdatedAt: null,
    firstSeenAt: null,
    lastSeenAt: null,
    updatedAt: null,
    ...o,
  };
}

const tipos = (c: ReturnType<typeof compararSnapshots>) => c.map((x) => x.tipo);

describe("las seis fechas no son la misma", () => {
  it("usa la fecha de publicación cuando existe", () => {
    expect(fechaParaMostrar(marcas({ publishedAt: "2026-01-01" }))).toEqual({
      fecha: "2026-01-01",
      tipo: "PUBLICADA",
    });
  });

  it("NUNCA usa firstSeenAt como fecha de publicación", () => {
    // Que la hayamos visto el martes no dice cuándo se publicó: pudo estar
    // publicada dos años antes de que ERETZ existiera.
    const m = marcas({ firstSeenAt: "2026-03-01" });
    const r = fechaParaMostrar(m);
    expect(r.fecha).toBeNull();
    expect(r.tipo).toBe("SIN_FECHA");
  });

  it("prefiere la fecha de la fuente sobre la de nuestro registro", () => {
    // La de la fuente le dice algo a quien mira; la nuestra sólo a nosotros.
    const r = fechaParaMostrar(marcas({ sourceUpdatedAt: "2026-05-01", updatedAt: "2026-08-01" }));
    expect(r).toEqual({ fecha: "2026-05-01", tipo: "ACTUALIZADA" });
  });

  it("etiqueta el tipo para que la UI no adivine", () => {
    expect(fechaParaMostrar(marcas({ updatedAt: "2026-08-01" })).tipo).toBe("ACTUALIZADA");
  });

  it("detecta que se está usando firstSeenAt como publicación", () => {
    const m = marcas({ firstSeenAt: "2026-03-01" });
    expect(esFechaDePublicacionLegitima(m, "2026-03-01")).toBe(false);
    expect(esFechaDePublicacionLegitima(m, null)).toBe(true);
  });

  it("acepta que coincidan si la fuente realmente lo dice", () => {
    const m = marcas({ firstSeenAt: "2026-03-01", publishedAt: "2026-03-01" });
    expect(esFechaDePublicacionLegitima(m, "2026-03-01")).toBe(true);
  });
});

describe("un cambio tiene intervalo, no fecha", () => {
  it("acota entre las dos observaciones y no ofrece una fecha exacta", () => {
    // Con scraping semanal, poner la baja el viernes es un error de hasta
    // siete días en cada punto de la serie.
    const c = compararSnapshots(snap("2026-01-01"), snap("2026-01-08", { price: 90_000 }));
    expect(c).toHaveLength(1);
    expect(c[0].desde).toBe("2026-01-01");
    expect(c[0].hasta).toBe("2026-01-08");
    expect(c[0]).not.toHaveProperty("fecha");
  });
});

describe("cambios de precio", () => {
  it("detecta baja y suba", () => {
    expect(tipos(compararSnapshots(snap("1"), snap("2", { price: 90_000 })))).toEqual([
      "PRICE_DECREASED",
    ]);
    expect(tipos(compararSnapshots(snap("1"), snap("2", { price: 110_000 })))).toEqual([
      "PRICE_INCREASED",
    ]);
  });

  it("no reporta nada si el precio no cambió", () => {
    expect(compararSnapshots(snap("1"), snap("2"))).toEqual([]);
  });

  it("no compara precios de monedas distintas", () => {
    // Comparar 100.000 ARS con 100.000 USD y decir "sin cambios" sería peor
    // que no comparar.
    const c = compararSnapshots(snap("1"), snap("2", { currency: "ARS", price: 100_000 }));
    expect(tipos(c)).toEqual(["CURRENCY_CHANGED"]);
    expect(tipos(c)).not.toContain("PRICE_DECREASED");
  });

  it("registra el valor anterior y el nuevo", () => {
    const c = compararSnapshots(snap("1"), snap("2", { price: 90_000 }));
    expect(c[0].anterior).toBe(100_000);
    expect(c[0].nuevo).toBe(90_000);
  });

  it("ignora un precio ausente en cualquiera de los dos lados", () => {
    expect(tipos(compararSnapshots(snap("1", { price: null }), snap("2")))).not.toContain(
      "PRICE_INCREASED",
    );
  });
});

describe("disponibilidad", () => {
  it("detecta que dejó de verse", () => {
    const c = compararSnapshots(snap("1"), snap("2", { availability: "NOT_SEEN_LAST_SCRAPE" }));
    expect(tipos(c)).toContain("BECAME_UNAVAILABLE");
  });

  it("detecta que volvió", () => {
    const c = compararSnapshots(snap("1", { availability: "NOT_SEEN_LAST_SCRAPE" }), snap("2"));
    expect(tipos(c)).toContain("RETURNED");
  });

  it("no confunde 'no sabemos' con 'se fue'", () => {
    // Pasar de UNKNOWN a NOT_SEEN es seguir sin saber, no una baja.
    const c = compararSnapshots(
      snap("1", { availability: "UNKNOWN" }),
      snap("2", { availability: "NOT_SEEN_LAST_SCRAPE" }),
    );
    expect(tipos(c)).not.toContain("BECAME_UNAVAILABLE");
  });

  it("tampoco cuenta como retorno salir de un estado desconocido", () => {
    const c = compararSnapshots(snap("1", { availability: "UNKNOWN" }), snap("2"));
    expect(tipos(c)).not.toContain("RETURNED");
  });
});

describe("publicador y expensas", () => {
  it("detecta un cambio de publicador", () => {
    const c = compararSnapshots(snap("1"), snap("2", { publisherKey: "otra" }));
    expect(tipos(c)).toContain("PUBLISHER_CHANGED");
  });

  it("no reporta cambio si alguno de los dos es desconocido", () => {
    const c = compararSnapshots(snap("1", { publisherKey: null }), snap("2"));
    expect(tipos(c)).not.toContain("PUBLISHER_CHANGED");
  });

  it("detecta que aparecieron expensas", () => {
    const c = compararSnapshots(snap("1"), snap("2", { expenses: 50_000 }));
    expect(tipos(c)).toContain("EXPENSES_CHANGED");
  });

  it("no reporta expensas que siguen ausentes", () => {
    expect(tipos(compararSnapshots(snap("1"), snap("2")))).not.toContain("EXPENSES_CHANGED");
  });
});

describe("robustez de la comparación", () => {
  it("no compara publicaciones distintas", () => {
    const otro = { ...snap("2"), listingId: listingId("l-9") };
    expect(compararSnapshots(snap("1"), otro)).toEqual([]);
  });

  it("no inventa cambios si las observaciones vienen al revés", () => {
    expect(compararSnapshots(snap("2026-01-08"), snap("2026-01-01", { price: 90_000 }))).toEqual([]);
  });

  it("ordena la serie antes de recorrerla", () => {
    // Sin ordenar, observaciones de distintas corridas producirían subidas y
    // bajadas alternadas que nunca ocurrieron.
    const desordenada = [
      snap("2026-03-01", { price: 80_000 }),
      snap("2026-01-01", { price: 100_000 }),
      snap("2026-02-01", { price: 90_000 }),
    ];
    expect(tipos(historialDeCambios(desordenada))).toEqual(["PRICE_DECREASED", "PRICE_DECREASED"]);
  });

  it("es determinista", () => {
    const s = [snap("1"), snap("2", { price: 90_000 })];
    expect(historialDeCambios(s)).toEqual(historialDeCambios(s));
  });
});

describe("no fabricar historia", () => {
  it("con una sola observación no hay historia", () => {
    expect(tieneHistoria([snap("1")])).toBe(false);
    expect(tieneHistoria([])).toBe(false);
    expect(historialDeCambios([snap("1")])).toEqual([]);
  });

  it("no dice 'sin cambios' cuando lo que falta son observaciones", () => {
    // Sería afirmar estabilidad que no observamos.
    const r = resumirPrecio([snap("1")]);
    expect(r.disponible).toBe(false);
    if (!r.disponible) expect(r.motivo).toMatch(/dos observaciones/);
  });

  it("no resume una serie que cambia de moneda", () => {
    const r = resumirPrecio([snap("1"), snap("2", { currency: "ARS" })]);
    expect(r.disponible).toBe(false);
    if (!r.disponible) expect(r.motivo).toMatch(/moneda/);
  });

  it("no resume si faltan precios", () => {
    expect(resumirPrecio([snap("1", { price: null }), snap("2", { price: null })]).disponible).toBe(
      false,
    );
  });
});

describe("resumen de precio", () => {
  it("calcula la variación entre la primera y la última observación", () => {
    const r = resumirPrecio([
      snap("2026-01-01", { price: 100_000 }),
      snap("2026-02-01", { price: 90_000 }),
      snap("2026-03-01", { price: 80_000 }),
    ]);
    expect(r.disponible).toBe(true);
    if (r.disponible) {
      expect(r.precioInicial).toBe(100_000);
      expect(r.precioActual).toBe(80_000);
      expect(r.variacion).toBeCloseTo(-0.2, 10);
      expect(r.cambios).toBe(2);
    }
  });

  it("informa desde cuándo hay observaciones, no cuándo se publicó", () => {
    // Si existía antes de la primera observación, su precio original pudo ser
    // otro y no hay forma de saberlo.
    const r = resumirPrecio([snap("2026-05-01"), snap("2026-06-01", { price: 90_000 })]);
    if (r.disponible) expect(r.observadaDesde).toBe("2026-05-01");
    else expect.unreachable("debería estar disponible");
  });
});
