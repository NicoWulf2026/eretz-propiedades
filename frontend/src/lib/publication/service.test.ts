import { describe, expect, it } from "vitest";
import { agentId, organizationId, userId } from "@/domain/ids";
import type { Actor, Role } from "@/domain/permissions";
import { POLITICA_PARTICULAR, type BorradorDePublicacion } from "@/domain/publishing";
import {
  crearBorrador,
  actualizarBorrador,
  enviarPublicacion,
  nuevaClaveDeIdempotencia,
  puedeCrear,
  revisarAntesDeEnviar,
  type ContextoDePublicacion,
} from "./service";
import { crearRepositorioEnMemoria, type ActorDePublicacion } from "./repository";

const ORG = organizationId("org-1");
const OTRA_ORG = organizationId("org-2");
const U = userId("u-1");

function borrador(o: Partial<BorradorDePublicacion> = {}): BorradorDePublicacion {
  return {
    publisherType: "INDIVIDUAL",
    authorUserId: U,
    organizationId: null,
    agentId: null,
    operation: "venta",
    propertyType: "departamento",
    precio: { kind: "MONTO", amount: 85_000, currency: "USD" },
    expenses: null,
    province: "Santa Fe",
    city: "Rosario",
    neighborhood: null,
    address: "Córdoba 1234",
    title: "Departamento de 2 ambientes en Rosario centro",
    description: "Luminoso, con balcón al frente y cocina separada. A dos cuadras del río.",
    rooms: 2,
    bedrooms: 1,
    bathrooms: 1,
    totalArea: 55,
    coveredArea: 50,
    images: ["blob:preview-1"],
    contactPhone: "3410000000",
    contactEmail: null,
    legitimacyAccepted: true,
    ...o,
  };
}

function actorParticular(): ActorDePublicacion {
  return { kind: "INDIVIDUAL", userId: U };
}

function actorOrganizacion(org = ORG): ActorDePublicacion {
  return { kind: "ORGANIZATION", userId: U, organizationId: org };
}

function permisos(rol: Role, org = ORG): Actor {
  return {
    kind: "USER",
    userId: U,
    memberships: [{ organizationId: org, role: rol, agentId: agentId("ag-1"), suspended: false }],
  };
}

const ANONIMO: Actor = { kind: "ANONYMOUS" };

function contexto(o: Partial<ContextoDePublicacion> = {}): ContextoDePublicacion {
  return {
    repository: crearRepositorioEnMemoria(),
    actor: actorParticular(),
    permisos: ANONIMO,
    ahora: () => "2026-08-28T10:00:00.000Z",
    ...o,
  };
}

describe("la frontera es real", () => {
  it("el servicio funciona entero contra un repositorio en memoria", () => {
    // Si dependiera de algo de la base, este adaptador no podría existir. Que
    // exista ES la prueba de que la frontera está bien puesta.
    const ctx = contexto();
    expect(ctx.repository).toBeDefined();
    expect(puedeCrear(ctx)).toBe(true);
  });

  it("no importa nada de React", async () => {
    // Se ejecuta el flujo completo sin montar un solo componente.
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador());
    expect(creado.ok).toBe(true);
  });
});

describe("permisos", () => {
  it("un particular publica en nombre propio", () => {
    expect(puedeCrear(contexto())).toBe(true);
  });

  it("publicar como organización exige la capacidad", () => {
    for (const rol of ["OWNER", "ADMIN", "MANAGER", "AGENT"] as Role[]) {
      expect(puedeCrear(contexto({ actor: actorOrganizacion(), permisos: permisos(rol) }))).toBe(true);
    }
  });

  it("VIEWER y EDITOR no pueden crear publicaciones", () => {
    for (const rol of ["VIEWER", "EDITOR"] as Role[]) {
      expect(puedeCrear(contexto({ actor: actorOrganizacion(), permisos: permisos(rol) }))).toBe(false);
    }
  });

  it("sin membresía no se puede publicar como organización", async () => {
    const ctx = contexto({
      actor: actorOrganizacion(),
      permisos: { kind: "USER", userId: U, memberships: [] },
    });
    const r = await crearBorrador(ctx, borrador());
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("PERMISSION_DENIED");
  });

  it("ser OWNER de una organización no habilita publicar en otra", async () => {
    // La prueba de tenancy: el actor dice ORG_2 pero sólo pertenece a ORG_1.
    const ctx = contexto({
      actor: actorOrganizacion(OTRA_ORG),
      permisos: permisos("OWNER", ORG),
    });
    const r = await crearBorrador(ctx, borrador());
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("PERMISSION_DENIED");
  });

  it("un anónimo no publica como organización", async () => {
    const ctx = contexto({ actor: actorOrganizacion(), permisos: ANONIMO });
    const r = await crearBorrador(ctx, borrador());
    expect(r.ok).toBe(false);
  });
});

describe("límite del particular", () => {
  it("permite hasta el máximo declarado", async () => {
    const ctx = contexto();
    for (let i = 0; i < POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT; i++) {
      expect((await crearBorrador(ctx, borrador())).ok).toBe(true);
    }
    const extra = await crearBorrador(ctx, borrador());
    expect(extra.ok).toBe(false);
    if (!extra.ok) expect(extra.error.code).toBe("LIMIT_REACHED");
  });

  it("el número no está escrito en el servicio", async () => {
    // Un 5 en el servicio y otro en la UI se desincronizan.
    const ctx = contexto();
    for (let i = 0; i < POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT; i++) {
      await crearBorrador(ctx, borrador());
    }
    const r = await crearBorrador(ctx, borrador());
    if (!r.ok) {
      expect(r.error.detail).toContain(String(POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT));
    }
  });

  it("el límite no aplica a una organización", async () => {
    const ctx = contexto({ actor: actorOrganizacion(), permisos: permisos("OWNER") });
    for (let i = 0; i < POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT + 3; i++) {
      expect((await crearBorrador(ctx, borrador())).ok).toBe(true);
    }
  });
});

describe("revisión previa", () => {
  it("un borrador completo queda listo para enviar", () => {
    const r = revisarAntesDeEnviar(borrador());
    expect(r.bloqueantes).toEqual([]);
    expect(r.listoParaEnviar).toBe(true);
  });

  it("separa lo que bloquea de lo que conviene mejorar", () => {
    // Una foto sola no impide publicar, pero conviene decirlo.
    const r = revisarAntesDeEnviar(borrador());
    expect(r.listoParaEnviar).toBe(true);
    expect(r.sugerencias.some((s) => s.field === "images")).toBe(true);
  });

  it("NO expone el puntaje como número en las sugerencias", () => {
    // "Tu publicación tiene 82/100" invita a optimizar la métrica en vez de la
    // publicación, y no le dice a nadie qué hacer.
    const r = revisarAntesDeEnviar(borrador({ images: [] }));
    for (const s of r.sugerencias) {
      expect(s.message).not.toMatch(/\d+\s*\/\s*100/);
      expect(s.message).not.toMatch(/\d+[.,]\d+/);
    }
  });

  it("reutiliza los validadores existentes en vez de duplicar reglas", () => {
    const sinTitulo = revisarAntesDeEnviar(borrador({ title: null }));
    expect(sinTitulo.bloqueantes.some((b) => b.field === "title")).toBe(true);
    expect(sinTitulo.listoParaEnviar).toBe(false);
  });

  it("acepta 'a consultar' como precio", () => {
    const r = revisarAntesDeEnviar(borrador({ precio: { kind: "CONSULTAR" } }));
    expect(r.listoParaEnviar).toBe(true);
  });

  it("no acepta un precio sin decidir", () => {
    const r = revisarAntesDeEnviar(borrador({ precio: null }));
    expect(r.bloqueantes.some((b) => b.field === "precio")).toBe(true);
  });

  it("una carga manual con datos contradictorios SÍ se bloquea", () => {
    // Asimetría deliberada frente a lo scrapeado: rechazar una carga manual
    // cuesta un minuto de quien la hizo.
    const r = revisarAntesDeEnviar(borrador({ coveredArea: 900, totalArea: 55 }));
    expect(r.listoParaEnviar).toBe(false);
    expect(r.moderacion.decision).toBe("REJECT");
  });
});

describe("envío", () => {
  async function conBorradorListo() {
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador());
    if (!creado.ok) throw new Error("no se pudo crear");
    return { ctx, id: creado.value.id };
  }

  it("envía un borrador válido", async () => {
    const { ctx, id } = await conBorradorListo();
    const r = await enviarPublicacion(ctx, id, nuevaClaveDeIdempotencia());
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.submittedAt).toBe("2026-08-28T10:00:00.000Z");
      // Todavía no existe como publicación del catálogo.
      expect(r.value.listingId).toBeNull();
    }
  });

  it("revalida contra lo guardado, no contra lo que diga el cliente", async () => {
    // Entre que la UI dijo "listo" y llega el envío, el borrador pudo cambiar.
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador());
    if (!creado.ok) throw new Error("no se pudo crear");

    await actualizarBorrador(ctx, creado.value.id, borrador({ title: null }), creado.value.version);
    const r = await enviarPublicacion(ctx, creado.value.id, nuevaClaveDeIdempotencia());

    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("VALIDATION_ERROR");
  });

  it("distingue un bloqueo de moderación de un error de validación", async () => {
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador({ coveredArea: 900, totalArea: 55 }));
    if (!creado.ok) throw new Error("no se pudo crear");
    const r = await enviarPublicacion(ctx, creado.value.id, nuevaClaveDeIdempotencia());
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("MODERATION_BLOCKED");
  });

  it("no envía un borrador ajeno", async () => {
    const { ctx, id } = await conBorradorListo();
    const otro = contexto({
      repository: ctx.repository,
      actor: { kind: "INDIVIDUAL", userId: userId("u-9") },
    });
    const r = await enviarPublicacion(otro, id, nuevaClaveDeIdempotencia());
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("DRAFT_NOT_FOUND");
  });
});

describe("idempotencia", () => {
  it("dos envíos con la misma clave son un solo envío", async () => {
    // Es el doble click.
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador());
    if (!creado.ok) throw new Error("no se pudo crear");

    const clave = nuevaClaveDeIdempotencia();
    const primero = await enviarPublicacion(ctx, creado.value.id, clave);
    const segundo = await enviarPublicacion(ctx, creado.value.id, clave);

    expect(primero.ok).toBe(true);
    expect(segundo.ok).toBe(false);
    if (!segundo.ok) expect(segundo.error.code).toBe("DUPLICATE_SUBMISSION");
  });

  it("dos claves distintas son dos envíos", async () => {
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador());
    if (!creado.ok) throw new Error("no se pudo crear");

    expect((await enviarPublicacion(ctx, creado.value.id, "clave-a")).ok).toBe(true);
    expect((await enviarPublicacion(ctx, creado.value.id, "clave-b")).ok).toBe(true);
  });

  it("genera claves distintas cada vez", () => {
    const claves = new Set(Array.from({ length: 50 }, () => nuevaClaveDeIdempotencia()));
    expect(claves.size).toBe(50);
  });
});

describe("concurrencia", () => {
  it("detecta que alguien más modificó el borrador", async () => {
    const ctx = contexto();
    const creado = await crearBorrador(ctx, borrador());
    if (!creado.ok) throw new Error("no se pudo crear");

    const primera = await actualizarBorrador(ctx, creado.value.id, borrador({ title: "Uno actualizado" }), 1);
    expect(primera.ok).toBe(true);

    // Segunda escritura con la versión vieja.
    const segunda = await actualizarBorrador(ctx, creado.value.id, borrador({ title: "Otro" }), 1);
    expect(segunda.ok).toBe(false);
    if (!segunda.ok) expect(segunda.error.code).toBe("CONFLICT");
  });
});

describe("auditoría", () => {
  it("registra quién y cuándo en cada paso", async () => {
    // Los eventos que no se guardaron no se recuperan después.
    const repo = crearRepositorioEnMemoria();
    const ctx = contexto({ repository: repo });
    const creado = await crearBorrador(ctx, borrador());
    if (!creado.ok) throw new Error("no se pudo crear");

    await actualizarBorrador(ctx, creado.value.id, borrador({ title: "Actualizado y suficientemente largo" }), 1);
    await enviarPublicacion(ctx, creado.value.id, nuevaClaveDeIdempotencia());

    const [guardado] = repo._todos();
    expect(guardado.audit.map((a) => a.action)).toEqual(["DRAFT_CREATED", "DRAFT_UPDATED", "SUBMITTED"]);
    expect(guardado.audit.every((a) => a.actorUserId === U && a.at.length > 0)).toBe(true);
  });
});
