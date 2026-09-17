import { describe, expect, it } from "vitest";
import { listingId, organizationId, userId } from "./ids";
import {
  MODERATION_STATUSES,
  PUBLICATION_STATUSES,
  TRANSICIONES_PUBLICACION,
  TransicionInvalida,
  type Listing,
  type PublicationStatus,
  disponibilidadConfirmada,
  esEstadoTerminal,
  esVisiblePublicamente,
  moderacionPermiteMostrar,
  observacionDesdeEstado,
  organizacionDePublicador,
  problemasDeCoherencia,
  puedeTransicionar,
  tieneCicloEditorial,
  transicionar,
} from "./listing";

/** Una publicación scrapeada típica: lo que hay hoy, 257k veces. */
function scrapeada(): Listing {
  return {
    id: listingId("1001"),
    propertyEntityId: null,
    origin: "SCRAPED",
    publisher: { kind: "UNIDENTIFIED", displayName: "Inmobiliaria X", sourceHost: "ejemplo.com" },
    observation: "ACTIVE",
    lifecycle: null,
    moderation: "NOT_ASSESSED",
    timestamps: { publishedAt: null, firstSeenAt: "2026-01-01", lastSeenAt: "2026-08-01", updatedAt: null },
    sourceUrl: "https://ejemplo.com/p/1",
  };
}

/** Una publicación cargada por alguien en ERETZ. Todavía no existe ninguna. */
function manual(lifecycle: PublicationStatus): Listing {
  return {
    ...scrapeada(),
    id: listingId("2002"),
    origin: "MANUAL",
    publisher: { kind: "INDIVIDUAL", userId: userId("u1") },
    lifecycle,
    sourceUrl: null,
  };
}

describe("origen", () => {
  it("sólo lo publicado en ERETZ tiene ciclo editorial", () => {
    // Es la distinción de la que cuelga todo el resto del modelo.
    expect(tieneCicloEditorial("MANUAL")).toBe(true);
    expect(tieneCicloEditorial("API")).toBe(true);
    expect(tieneCicloEditorial("SCRAPED")).toBe(false);
    expect(tieneCicloEditorial("IMPORTED")).toBe(false);
  });
});

describe("observación", () => {
  it("traduce el estado de la base sin reinterpretarlo", () => {
    expect(observacionDesdeEstado("activa")).toBe("ACTIVE");
    expect(observacionDesdeEstado("no_detectada_en_ultimo_scraping")).toBe("NOT_SEEN_LAST_SCRAPE");
    expect(observacionDesdeEstado("desconocida")).toBe("UNKNOWN");
  });

  it("cualquier valor inesperado cae en UNKNOWN, nunca en ACTIVE", () => {
    // Fail-closed: un estado nuevo en la base no debe volverse "disponible"
    // por omisión.
    for (const v of ["", null, undefined, "vendida", "ACTIVA", "otra_cosa"]) {
      expect(observacionDesdeEstado(v)).toBe("UNKNOWN");
    }
  });

  it("sólo ACTIVE confirma disponibilidad, y no-visto no es no-disponible", () => {
    expect(disponibilidadConfirmada("ACTIVE")).toBe(true);
    expect(disponibilidadConfirmada("NOT_SEEN_LAST_SCRAPE")).toBe(false);
    expect(disponibilidadConfirmada("UNKNOWN")).toBe(false);
    // Y son estados distintos entre sí: "no la vimos" ≠ "no sabemos".
    expect(observacionDesdeEstado("no_detectada_en_ultimo_scraping")).not.toBe(
      observacionDesdeEstado("desconocida"),
    );
  });
});

describe("ciclo de vida", () => {
  it("permite el camino normal de una publicación", () => {
    let s: PublicationStatus = "DRAFT";
    s = transicionar(s, "PENDING_REVIEW");
    s = transicionar(s, "PUBLISHED");
    s = transicionar(s, "PAUSED");
    s = transicionar(s, "PUBLISHED");
    expect(s).toBe("PUBLISHED");
  });

  it("no deja saltar la revisión", () => {
    expect(puedeTransicionar("DRAFT", "PUBLISHED")).toBe(false);
    // Y un rechazo tampoco se revierte a publicado de un salto.
    expect(puedeTransicionar("REJECTED", "PUBLISHED")).toBe(false);
    expect(puedeTransicionar("REJECTED", "DRAFT")).toBe(true);
  });

  it("REMOVED es terminal: rehacer es crear otra publicación", () => {
    expect(esEstadoTerminal("REMOVED")).toBe(true);
    for (const destino of PUBLICATION_STATUSES) {
      expect(puedeTransicionar("REMOVED", destino)).toBe(false);
    }
  });

  it("falla con un error que dice qué transición se intentó", () => {
    try {
      transicionar("DRAFT", "PUBLISHED");
      expect.unreachable("debería haber fallado");
    } catch (e) {
      expect(e).toBeInstanceOf(TransicionInvalida);
      expect((e as TransicionInvalida).desde).toBe("DRAFT");
      expect((e as TransicionInvalida).hacia).toBe("PUBLISHED");
    }
  });

  it("deny by default: ninguna transición fuera del mapa pasa", () => {
    // Recorre el producto cartesiano completo y comprueba que `puedeTransicionar`
    // no sea más permisivo que la tabla declarada. Si alguien agrega un estado
    // y olvida su fila, esto lo encuentra.
    for (const desde of PUBLICATION_STATUSES) {
      for (const hacia of PUBLICATION_STATUSES) {
        const declarado = TRANSICIONES_PUBLICACION[desde].includes(hacia);
        expect(puedeTransicionar(desde, hacia)).toBe(declarado);
      }
    }
  });

  it("ningún estado se declara transición hacia sí mismo", () => {
    // Una transición a sí mismo no es un cambio de estado; si algún flujo la
    // necesita, es que le falta un estado.
    for (const s of PUBLICATION_STATUSES) {
      expect(TRANSICIONES_PUBLICACION[s]).not.toContain(s);
    }
  });
});

describe("moderación", () => {
  it("no evaluado no es lo mismo que aprobado", () => {
    expect(MODERATION_STATUSES).toContain("NOT_ASSESSED");
    expect(MODERATION_STATUSES).toContain("ALLOWED");
  });

  it("oculta lo bloqueado y lo que está en revisión", () => {
    expect(moderacionPermiteMostrar("BLOCKED")).toBe(false);
    expect(moderacionPermiteMostrar("UNDER_REVIEW")).toBe(false);
  });

  it("muestra lo no evaluado, porque es el estado de todo el catálogo actual", () => {
    // Decisión explícita, no descuido: tratar NOT_ASSESSED como oculto dejaría
    // el sitio vacío.
    expect(moderacionPermiteMostrar("NOT_ASSESSED")).toBe(true);
  });
});

describe("coherencia del modelo", () => {
  it("acepta una publicación scrapeada sin ciclo de vida", () => {
    expect(problemasDeCoherencia(scrapeada())).toEqual([]);
  });

  it("rechaza que lo scrapeado tenga ciclo de vida inventado", () => {
    // Es el error concreto que motiva separar los ejes: nadie apretó
    // "publicar" en una publicación scrapeada.
    const l = { ...scrapeada(), lifecycle: "PUBLISHED" as const };
    expect(problemasDeCoherencia(l)).toHaveLength(1);
    expect(problemasDeCoherencia(l)[0]).toMatch(/no tiene ciclo de vida/);
  });

  it("rechaza que una publicación manual no tenga ciclo de vida", () => {
    const l = { ...manual("DRAFT"), lifecycle: null };
    expect(problemasDeCoherencia(l)[0]).toMatch(/exige ciclo de vida/);
  });

  it("rechaza atribuir una publicación scrapeada a un particular identificado", () => {
    const l: Listing = { ...scrapeada(), publisher: { kind: "INDIVIDUAL", userId: userId("u1") } };
    expect(problemasDeCoherencia(l)[0]).toMatch(/particular/);
  });

  it("una publicación válida no reporta problemas", () => {
    expect(problemasDeCoherencia(manual("PUBLISHED"))).toEqual([]);
  });
});

describe("publicador", () => {
  it("identifica el tenant cuando lo hay", () => {
    const org = organizationId("org1");
    expect(
      organizacionDePublicador({ kind: "ORGANIZATION", organizationId: org, branchId: null, agentId: null }),
    ).toBe(org);
    expect(organizacionDePublicador({ kind: "AGENT", agentId: "a1" as never, organizationId: org })).toBe(org);
  });

  it("lo scrapeado no pertenece a ningún tenant", () => {
    // Importa para tenancy: nadie puede administrar lo que no está atribuido.
    expect(
      organizacionDePublicador({ kind: "UNIDENTIFIED", displayName: "X", sourceHost: "x.com" }),
    ).toBeNull();
    expect(organizacionDePublicador({ kind: "INDIVIDUAL", userId: userId("u1") })).toBeNull();
  });
});

describe("visibilidad pública", () => {
  it("muestra una publicación scrapeada activa y no evaluada", () => {
    expect(esVisiblePublicamente(scrapeada())).toBe(true);
  });

  it("oculta lo que no se vio en el último scraping", () => {
    expect(esVisiblePublicamente({ ...scrapeada(), observation: "NOT_SEEN_LAST_SCRAPE" })).toBe(false);
  });

  it("no oculta lo desconocido: no saber no es una negativa", () => {
    expect(esVisiblePublicamente({ ...scrapeada(), observation: "UNKNOWN" })).toBe(true);
  });

  it("oculta lo bloqueado por moderación aunque esté activa", () => {
    expect(esVisiblePublicamente({ ...scrapeada(), moderation: "BLOCKED" })).toBe(false);
    expect(esVisiblePublicamente({ ...scrapeada(), moderation: "UNDER_REVIEW" })).toBe(false);
  });

  it("con ciclo editorial exige estar efectivamente publicada", () => {
    expect(esVisiblePublicamente(manual("PUBLISHED"))).toBe(true);
    for (const s of ["DRAFT", "PENDING_REVIEW", "PAUSED", "REMOVED", "REJECTED"] as const) {
      expect(esVisiblePublicamente(manual(s))).toBe(false);
    }
  });
});
