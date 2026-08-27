import { describe, expect, it } from "vitest";
import { agentId, listingId, userId } from "./ids";
import {
  CAMPOS_CORREGIBLES,
  type EditorialLayer,
  type EstadoEditorial,
  type Override,
  aplicarOverrides,
  capaPermiteMostrar,
  correccionesRedundantes,
  esCampoCorregible,
  problemasDeOverride,
} from "./overrides";

const AUTOR = userId("u-1");

function ov(field: string, value: unknown): Override {
  return { field: field as Override["field"], value, authorUserId: AUTOR, at: "2026-08-01", reason: null };
}

function capa(overrides: Record<string, Override>, estado: EstadoEditorial = "NONE"): EditorialLayer {
  return { listingId: listingId("l-1"), overrides, estado, assignedAgentId: null };
}

const SNAPSHOT = {
  title: "Depto 2 amb",
  price: 90_000,
  currency: "USD",
  city: "Rosario",
  images: ["a.jpg", "b.jpg"],
  sourceUrl: "https://lopez.com.ar/p/1",
};

describe("la fuente no se toca", () => {
  it("aplicar overrides no muta el snapshot", () => {
    // Si se mutara, el dato original se perdería en la primera lectura.
    const copia = structuredClone(SNAPSHOT);
    aplicarOverrides(SNAPSHOT, capa({ price: ov("price", 85_000) }));
    expect(SNAPSHOT).toEqual(copia);
  });

  it("la URL de origen no es corregible: es la prueba de dónde salió el dato", () => {
    expect(esCampoCorregible("sourceUrl")).toBe(false);
    const v = aplicarOverrides(SNAPSHOT, capa({ sourceUrl: ov("sourceUrl", "https://otro.com") }));
    expect(v.sourceUrl).toBe(SNAPSHOT.sourceUrl);
    expect(v.overriddenFields).toEqual([]);
  });

  it("el id tampoco se corrige", () => {
    expect(esCampoCorregible("id")).toBe(false);
  });
});

describe("vista publicada", () => {
  it("sin capa editorial, es el snapshot tal cual", () => {
    const v = aplicarOverrides(SNAPSHOT, null);
    expect(v.price).toBe(90_000);
    expect(v.overriddenFields).toEqual([]);
  });

  it("aplica la corrección encima del snapshot", () => {
    const v = aplicarOverrides(SNAPSHOT, capa({ price: ov("price", 85_000) }));
    expect(v.price).toBe(85_000);
    expect(v.title).toBe("Depto 2 amb");
    expect(v.overriddenFields).toEqual(["price"]);
  });

  it("una corrección a null significa 'no hay dato', y se aplica", () => {
    // Distinto de no tener override, que significa "usá lo de la fuente".
    const v = aplicarOverrides(SNAPSHOT, capa({ price: ov("price", null) }));
    expect(v.price).toBeNull();
    expect(v.overriddenFields).toEqual(["price"]);
  });

  it("corrige arrays enteros, como las imágenes", () => {
    const v = aplicarOverrides(SNAPSHOT, capa({ images: ov("images", ["nueva.jpg"]) }));
    expect(v.images).toEqual(["nueva.jpg"]);
  });

  it("aplica varias correcciones a la vez y las lista ordenadas", () => {
    const v = aplicarOverrides(
      SNAPSHOT,
      capa({ price: ov("price", 1), title: ov("title", "x"), city: ov("city", "Funes") }),
    );
    expect(v.overriddenFields).toEqual(["city", "price", "title"]);
  });

  it("ignora un campo que el snapshot no tiene sin romper la ficha", () => {
    // Una fuente puede no traer ese campo; fallar ahí rompería todo por un
    // dato accesorio.
    const v = aplicarOverrides(SNAPSHOT, capa({ videoUrl: ov("videoUrl", "https://v.com/1") }));
    expect(v.videoUrl).toBe("https://v.com/1");
    expect(v.title).toBe("Depto 2 amb");
  });

  it("es determinista", () => {
    const c = capa({ price: ov("price", 85_000) });
    expect(aplicarOverrides(SNAPSHOT, c)).toEqual(aplicarOverrides(SNAPSHOT, c));
  });
});

describe("correcciones que dejaron de hacer falta", () => {
  it("detecta cuando la fuente ya trae el valor corregido", () => {
    // El scraper alcanzó al override: conviene ofrecer quitarlo en vez de
    // mantener una capa que ya no corrige nada.
    const r = correccionesRedundantes(SNAPSHOT, capa({ price: ov("price", 90_000) }));
    expect(r).toEqual(["price"]);
  });

  it("no marca las que siguen corrigiendo algo", () => {
    expect(correccionesRedundantes(SNAPSHOT, capa({ price: ov("price", 85_000) }))).toEqual([]);
  });

  it("compara arrays por contenido, no por identidad", () => {
    const igual = correccionesRedundantes(SNAPSHOT, capa({ images: ov("images", ["a.jpg", "b.jpg"]) }));
    expect(igual).toEqual(["images"]);
    const distinto = correccionesRedundantes(SNAPSHOT, capa({ images: ov("images", ["b.jpg", "a.jpg"]) }));
    expect(distinto).toEqual([]);
  });

  it("sin capa no hay redundancias", () => {
    expect(correccionesRedundantes(SNAPSHOT, null)).toEqual([]);
  });
});

describe("estado editorial y visibilidad", () => {
  it("pausar oculta de inmediato", () => {
    // Riesgo reversible: se ve menos oferta por un rato.
    expect(capaPermiteMostrar(capa({}, "PAUSED"))).toBe(false);
  });

  it("solicitar la baja NO oculta por sí solo", () => {
    // Dar de baja a pedido de quien dice ser dueño podría usarse para borrar
    // competencia. La solicitud abre un caso; la decisión es aparte.
    expect(capaPermiteMostrar(capa({}, "DELISTING_REQUESTED"))).toBe(true);
  });

  it("sin capa, se muestra", () => {
    expect(capaPermiteMostrar(null)).toBe(true);
    expect(capaPermiteMostrar(capa({}, "NONE"))).toBe(true);
  });
});

describe("validación al registrar", () => {
  it("acepta una corrección bien formada", () => {
    expect(problemasDeOverride(ov("price", 1))).toEqual([]);
  });

  it("rechaza un campo no corregible", () => {
    expect(problemasDeOverride(ov("sourceUrl", "x"))[0]).toMatch(/no es un campo corregible/);
  });

  it("exige autor y fecha en toda corrección", () => {
    // Sin autor no hay a quién preguntarle ante un reclamo.
    const sinAutor = { ...ov("price", 1), authorUserId: "" as never };
    expect(problemasDeOverride(sinAutor)).toContain("toda corrección necesita autor");
    const sinFecha = { ...ov("price", 1), at: "" };
    expect(problemasDeOverride(sinFecha)).toContain("toda corrección necesita fecha");
  });
});

describe("campos corregibles", () => {
  it("incluye la clasificación, que un scraper puede errar", () => {
    expect(CAMPOS_CORREGIBLES).toContain("operation");
    expect(CAMPOS_CORREGIBLES).toContain("propertyType");
  });

  it("permite reasignar el agente responsable", () => {
    expect(CAMPOS_CORREGIBLES).toContain("assignedAgentId");
    const v = aplicarOverrides(SNAPSHOT, capa({ assignedAgentId: ov("assignedAgentId", agentId("ag-2")) }));
    expect(v.assignedAgentId).toBe("ag-2");
  });

  it("no tiene duplicados", () => {
    expect(new Set(CAMPOS_CORREGIBLES).size).toBe(CAMPOS_CORREGIBLES.length);
  });
});
