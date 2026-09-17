import { describe, expect, it } from "vitest";
import { agentId, organizationId, userId } from "./ids";
import {
  IMAGENES_MINIMAS,
  LARGO_MINIMO_DESCRIPCION,
  LARGO_MINIMO_TITULO,
  POLITICA_PARTICULAR,
  type BorradorDePublicacion,
  esBorradorValido,
  puedePublicarGratis,
  validarBorrador,
} from "./publishing";

function borrador(overrides: Partial<BorradorDePublicacion> = {}): BorradorDePublicacion {
  return {
    publisherType: "INDIVIDUAL",
    authorUserId: userId("u-1"),
    organizationId: null,
    agentId: null,
    operation: "venta",
    propertyType: "departamento",
    precio: { kind: "MONTO", amount: 85_000, currency: "USD" },
    expenses: null,
    province: "Santa Fe",
    city: "Rosario",
    neighborhood: null,
    address: null,
    title: "Departamento de 2 ambientes en Rosario centro",
    description: "Luminoso, con balcón al frente y cocina separada. A dos cuadras del río.",
    rooms: 2,
    bedrooms: 1,
    bathrooms: 1,
    totalArea: 55,
    coveredArea: 50,
    images: ["https://ejemplo.com/1.jpg"],
    contactPhone: "3410000000",
    contactEmail: null,
    legitimacyAccepted: true,
    ...overrides,
  };
}

const codigos = (b: BorradorDePublicacion) => validarBorrador(b).map((e) => `${e.field}:${e.code}`);

describe("borrador completo", () => {
  it("un borrador bien cargado no tiene errores", () => {
    expect(validarBorrador(borrador())).toEqual([]);
    expect(esBorradorValido(borrador())).toBe(true);
  });

  it("devuelve TODOS los errores de una vez", () => {
    // Un formulario que revela un problema por vez obliga a enviar seis veces.
    const vacio = borrador({
      operation: null, propertyType: null, precio: null, province: null,
      city: null, title: null, description: null, images: [],
      contactPhone: null, contactEmail: null, legitimacyAccepted: false,
    });
    expect(validarBorrador(vacio).length).toBeGreaterThanOrEqual(9);
  });

  it("cada error nombra su campo y trae un mensaje para la persona", () => {
    for (const e of validarBorrador(borrador({ title: null, images: [] }))) {
      expect(e.field.length).toBeGreaterThan(0);
      expect(e.code.length).toBeGreaterThan(0);
      expect(e.message.length).toBeGreaterThan(0);
    }
  });
});

describe("precio: decisión explícita, no campo opcional", () => {
  it("acepta 'a consultar' como decisión válida", () => {
    expect(validarBorrador(borrador({ precio: { kind: "CONSULTAR" } }))).toEqual([]);
  });

  it("no acepta dejarlo sin decidir", () => {
    // "A consultar" y "todavía no lo cargué" son cosas distintas.
    expect(codigos(borrador({ precio: null }))).toContain("precio:REQUERIDO");
  });

  it("rechaza un monto no positivo", () => {
    for (const amount of [0, -1]) {
      expect(codigos(borrador({ precio: { kind: "MONTO", amount, currency: "USD" } }))).toContain(
        "precio:INVALIDO",
      );
    }
  });
});

describe("mínimos de contenido", () => {
  it("exige un título con sustancia", () => {
    expect(codigos(borrador({ title: "Depto" }))).toContain("title:MUY_CORTO");
    expect(codigos(borrador({ title: "x".repeat(LARGO_MINIMO_TITULO) }))).not.toContain("title:MUY_CORTO");
  });

  it("exige una descripción con sustancia", () => {
    expect(codigos(borrador({ description: "Lindo" }))).toContain("description:MUY_CORTA");
    expect(codigos(borrador({ description: "x".repeat(LARGO_MINIMO_DESCRIPCION) }))).not.toContain(
      "description:MUY_CORTA",
    );
  });

  it("no confunde espacios con contenido", () => {
    expect(codigos(borrador({ title: "   ", description: "   " }))).toContain("title:REQUERIDO");
  });

  it("exige al menos una foto", () => {
    expect(codigos(borrador({ images: [] }))).toContain("images:REQUERIDO");
    expect(borrador().images.length).toBeGreaterThanOrEqual(IMAGENES_MINIMAS);
  });
});

describe("contacto", () => {
  it("alcanza con teléfono o con email", () => {
    expect(validarBorrador(borrador({ contactPhone: null, contactEmail: "a@b.com" }))).toEqual([]);
    expect(validarBorrador(borrador({ contactPhone: "3410000000", contactEmail: null }))).toEqual([]);
  });

  it("no se publica sin ninguna vía de contacto", () => {
    // Una publicación que nadie puede contactar no le sirve a nadie.
    expect(codigos(borrador({ contactPhone: null, contactEmail: null }))).toContain("contactPhone:REQUERIDO");
  });
});

describe("legitimidad", () => {
  it("sin la declaración no se publica", () => {
    expect(codigos(borrador({ legitimacyAccepted: false }))).toContain("legitimacyAccepted:REQUERIDO");
  });
});

describe("coherencia física", () => {
  it("rechaza cubierta mayor que total", () => {
    expect(codigos(borrador({ coveredArea: 80, totalArea: 55 }))).toContain("coveredArea:INCOHERENTE");
  });

  it("rechaza más dormitorios que ambientes", () => {
    expect(codigos(borrador({ rooms: 2, bedrooms: 4 }))).toContain("bedrooms:INCOHERENTE");
  });

  it("rechaza negativos", () => {
    expect(codigos(borrador({ rooms: -1 }))).toContain("rooms:INVALIDO");
  });

  it("no bloquea lo raro, sólo lo contradictorio", () => {
    // Un monoambiente de 12 m² existe; bloquear una carga legítima por rara es
    // peor que revisarla después.
    expect(validarBorrador(borrador({ totalArea: 12, coveredArea: 12 }))).toEqual([]);
  });
});

describe("atribución", () => {
  it("una publicación de organización necesita la organización", () => {
    expect(codigos(borrador({ publisherType: "ORGANIZATION" }))).toContain("organizationId:REQUERIDO");
    expect(
      validarBorrador(borrador({ publisherType: "ORGANIZATION", organizationId: organizationId("org-1") })),
    ).toEqual([]);
  });

  it("un particular no publica en nombre de una organización", () => {
    expect(codigos(borrador({ organizationId: organizationId("org-1") }))).toContain(
      "organizationId:INVALIDO",
    );
  });

  it("una publicación de agente necesita el agente", () => {
    expect(codigos(borrador({ publisherType: "AGENT" }))).toContain("agentId:REQUERIDO");
    expect(
      validarBorrador(borrador({ publisherType: "AGENT", agentId: agentId("ag-1") })),
    ).toEqual([]);
  });
});

describe("límite de publicaciones gratuitas", () => {
  it("permite hasta el límite declarado", () => {
    const tope = POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT;
    expect(tope).toBe(5);
    expect(puedePublicarGratis(0)).toBe(true);
    expect(puedePublicarGratis(tope - 1)).toBe(true);
    expect(puedePublicarGratis(tope)).toBe(false);
    expect(puedePublicarGratis(tope + 10)).toBe(false);
  });
});
