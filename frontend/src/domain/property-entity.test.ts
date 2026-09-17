import { describe, expect, it } from "vitest";
import { listingId, propertyEntityId } from "./ids";
import {
  type EntityLink,
  type EntityLinkConfidence,
  type PropertyEntity,
  agrupaAutomaticamente,
  estaHuerfana,
  listingsAgrupados,
  listingsPorRevisar,
  pesoEnOferta,
} from "./property-entity";

function link(id: string, confidence: EntityLinkConfidence): EntityLink {
  return {
    listingId: listingId(id),
    confidence,
    evidence: ["misma dirección normalizada", "superficie idéntica"],
    decidedBy: "SCORER",
    decidedAt: "2026-08-01",
  };
}

function entidad(links: EntityLink[]): PropertyEntity {
  return {
    id: propertyEntityId("pe-1"),
    location: {
      address: "Av. Siempreviva 742",
      neighborhood: null,
      city: "Rosario",
      province: "Santa Fe",
      country: "AR",
      latitude: -32.95,
      longitude: -60.66,
      confidence: "high",
    },
    attributes: {
      propertyType: "departamento",
      totalArea: 70,
      coveredArea: 65,
      landArea: null,
      rooms: 3,
      bedrooms: 2,
      bathrooms: 1,
      garages: 0,
      age: 12,
    },
    links,
  };
}

describe("agrupamiento por confianza", () => {
  it("agrupa lo confirmado y lo de alta confianza", () => {
    expect(agrupaAutomaticamente("CONFIRMED")).toBe(true);
    expect(agrupaAutomaticamente("HIGH_CONFIDENCE")).toBe(true);
  });

  it("no agrupa lo posible, porque agrupar de más borra oferta real", () => {
    // Asimetría deliberada: un duplicado visible molesta; una propiedad
    // desaparecida por una fusión errónea no la ve nadie.
    expect(agrupaAutomaticamente("POSSIBLE_MATCH")).toBe(false);
  });

  it("separa lo agrupado de lo que espera revisión humana", () => {
    const e = entidad([link("1", "HIGH_CONFIDENCE"), link("2", "POSSIBLE_MATCH"), link("3", "CONFIRMED")]);
    expect(listingsAgrupados(e)).toEqual(["1", "3"]);
    expect(listingsPorRevisar(e).map((l) => l.listingId)).toEqual(["2"]);
  });

  it("conserva la evidencia de cada decisión", () => {
    // Sin evidencia no se puede auditar por qué se agrupó algo ni mejorar el
    // scorer con casos reales.
    const e = entidad([link("1", "HIGH_CONFIDENCE")]);
    expect(e.links[0].evidence.length).toBeGreaterThan(0);
    expect(e.links[0].decidedBy).toBe("SCORER");
  });
});

describe("métricas de oferta", () => {
  it("una propiedad física cuenta una sola vez, tenga los avisos que tenga", () => {
    // Es lo que evita que Mercado infle la oferta contando publicaciones.
    expect(pesoEnOferta()).toBe(1);
    const conTres = entidad([
      link("1", "CONFIRMED"),
      link("2", "HIGH_CONFIDENCE"),
      link("3", "HIGH_CONFIDENCE"),
    ]);
    expect(listingsAgrupados(conTres)).toHaveLength(3);
    expect(pesoEnOferta()).toBe(1);
  });
});

describe("entidades huérfanas", () => {
  it("detecta una entidad sin publicaciones agrupadas", () => {
    expect(estaHuerfana(entidad([]))).toBe(true);
  });

  it("una entidad con sólo vínculos dudosos también está huérfana", () => {
    // No tiene ni un aviso confirmado que la respalde: no debería mostrarse
    // como propiedad.
    expect(estaHuerfana(entidad([link("1", "POSSIBLE_MATCH")]))).toBe(true);
  });

  it("con un vínculo firme deja de estarlo", () => {
    expect(estaHuerfana(entidad([link("1", "HIGH_CONFIDENCE")]))).toBe(false);
  });
});
