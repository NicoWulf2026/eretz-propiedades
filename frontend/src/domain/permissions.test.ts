import { describe, expect, it } from "vitest";
import { agentId, branchId, listingId, organizationId, userId } from "./ids";
import {
  CAPABILITIES,
  ROLES,
  type Actor,
  type Capability,
  type RecursoContext,
  type Role,
  can,
  canConMotivo,
  capacidadesDeRol,
  membresiaEn,
} from "./permissions";

const ORG_A = organizationId("org-a");
const ORG_B = organizationId("org-b");
const AGENTE_1 = agentId("ag-1");
const AGENTE_2 = agentId("ag-2");

function usuario(rol: Role, org = ORG_A, ag: string | null = null): Actor {
  return {
    kind: "USER",
    userId: userId("u-1"),
    memberships: [
      { organizationId: org, role: rol, agentId: ag ? agentId(ag) : null, suspended: false },
    ],
  };
}

const ANONIMO: Actor = { kind: "ANONYMOUS" };

function publicacionDe(org = ORG_A, asignadaA: string | null = null): RecursoContext {
  return {
    kind: "LISTING",
    organizationId: org,
    listingId: listingId("l-1"),
    assignedAgentId: asignadaA ? agentId(asignadaA) : null,
  };
}

const ORGANIZACION_A: RecursoContext = { kind: "ORGANIZATION", organizationId: ORG_A };

describe("aislamiento entre tenants", () => {
  it("permite actuar dentro de la propia organización", () => {
    expect(can(usuario("ADMIN"), "listing.edit", publicacionDe(ORG_A))).toBe(true);
  });

  it("deniega actuar sobre otra organización, aunque sea OWNER de la suya", () => {
    // La prueba central de multi-tenancy. Ser dueño de A no da nada sobre B.
    const duenoDeA = usuario("OWNER", ORG_A);
    expect(can(duenoDeA, "listing.edit", publicacionDe(ORG_B))).toBe(false);
    expect(can(duenoDeA, "organization.edit", { kind: "ORGANIZATION", organizationId: ORG_B })).toBe(false);
  });

  it("deniega TODA capacidad cruzando el tenant, sin excepciones", () => {
    // Recorre la matriz completa rol × capacidad contra un recurso ajeno. Si
    // alguien agrega una capacidad y olvida el chequeo de tenant, esto lo caza.
    for (const rol of ROLES) {
      for (const cap of CAPABILITIES) {
        expect(can(usuario(rol, ORG_A), cap, publicacionDe(ORG_B))).toBe(false);
      }
    }
  });
});

describe("sin membresía", () => {
  it("el anónimo no puede nada, sobre ningún recurso", () => {
    for (const cap of CAPABILITIES) {
      expect(can(ANONIMO, cap, publicacionDe(ORG_A))).toBe(false);
      expect(can(ANONIMO, cap, ORGANIZACION_A)).toBe(false);
    }
  });

  it("un usuario sin ninguna membresía no puede nada", () => {
    const suelto: Actor = { kind: "USER", userId: userId("u-2"), memberships: [] };
    for (const cap of CAPABILITIES) {
      expect(can(suelto, cap, publicacionDe(ORG_A))).toBe(false);
    }
  });

  it("una membresía suspendida no habilita nada, ni siquiera mirar", () => {
    const suspendido: Actor = {
      kind: "USER",
      userId: userId("u-3"),
      memberships: [{ organizationId: ORG_A, role: "OWNER", agentId: null, suspended: true }],
    };
    for (const cap of CAPABILITIES) {
      expect(can(suspendido, cap, publicacionDe(ORG_A))).toBe(false);
    }
    expect(membresiaEn(suspendido, ORG_A)).toBeNull();
  });
});

describe("recursos sin dueño", () => {
  it("nadie administra una publicación scrapeada no reclamada", () => {
    // Es el estado de las 257k de hoy. Si esto diera true, reclamar una
    // inmobiliaria cualquiera daría poder sobre catálogo ajeno.
    const huerfana: RecursoContext = {
      kind: "LISTING",
      organizationId: null,
      listingId: listingId("l-9"),
      assignedAgentId: null,
    };
    for (const rol of ROLES) {
      for (const cap of CAPABILITIES) {
        expect(can(usuario(rol), cap, huerfana)).toBe(false);
      }
    }
  });
});

describe("los roles limitan de verdad", () => {
  it("VIEWER mira pero no edita", () => {
    const v = usuario("VIEWER");
    expect(can(v, "listing.view", publicacionDe())).toBe(true);
    expect(can(v, "organization.view", ORGANIZACION_A)).toBe(true);
    expect(can(v, "listing.edit", publicacionDe())).toBe(false);
    expect(can(v, "organization.edit", ORGANIZACION_A)).toBe(false);
    expect(can(v, "listing.remove", publicacionDe())).toBe(false);
  });

  it("AGENT no administra miembros ni otros agentes", () => {
    const a = usuario("AGENT", ORG_A, "ag-1");
    expect(can(a, "organization.members.manage", ORGANIZACION_A)).toBe(false);
    expect(can(a, "agent.manage", { kind: "AGENT", organizationId: ORG_A, agentId: AGENTE_2 })).toBe(false);
    expect(can(a, "organization.roles.manage", ORGANIZACION_A)).toBe(false);
  });

  it("OWNER puede todo dentro de su organización", () => {
    const o = usuario("OWNER");
    for (const cap of CAPABILITIES) {
      expect(can(o, cap, ORGANIZACION_A)).toBe(true);
    }
  });

  it("sólo OWNER administra roles y facturación", () => {
    // Que un ADMIN pueda ascender a alguien a OWNER es escalada silenciosa.
    for (const rol of ROLES) {
      const esperado = rol === "OWNER";
      expect(can(usuario(rol), "organization.roles.manage", ORGANIZACION_A)).toBe(esperado);
      expect(can(usuario(rol), "billing.manage", ORGANIZACION_A)).toBe(esperado);
      expect(can(usuario(rol), "organization.delete", ORGANIZACION_A)).toBe(esperado);
    }
  });

  it("EDITOR toca contenido pero no ve leads: son datos de terceros", () => {
    const e = usuario("EDITOR");
    expect(can(e, "organization.branding.edit", ORGANIZACION_A)).toBe(true);
    expect(can(e, "listing.edit", publicacionDe())).toBe(true);
    expect(can(e, "lead.view", ORGANIZACION_A)).toBe(false);
    expect(can(e, "analytics.view", ORGANIZACION_A)).toBe(false);
    // Y no puede cambiar la identidad legal de la empresa.
    expect(can(e, "organization.edit", ORGANIZACION_A)).toBe(false);
  });

  it("dar de baja publicaciones requiere al menos MANAGER", () => {
    for (const rol of ["OWNER", "ADMIN", "MANAGER"] as const) {
      expect(can(usuario(rol), "listing.remove", publicacionDe())).toBe(true);
    }
    for (const rol of ["AGENT", "EDITOR", "VIEWER"] as const) {
      expect(can(usuario(rol, ORG_A, "ag-1"), "listing.remove", publicacionDe(ORG_A, "ag-1"))).toBe(false);
    }
  });
});

describe("el agente edita lo suyo, no lo ajeno", () => {
  it("edita y pausa la publicación que tiene asignada", () => {
    const a = usuario("AGENT", ORG_A, "ag-1");
    expect(can(a, "listing.edit", publicacionDe(ORG_A, "ag-1"))).toBe(true);
    expect(can(a, "listing.pause", publicacionDe(ORG_A, "ag-1"))).toBe(true);
  });

  it("no edita la publicación de un colega de la misma organización", () => {
    // Mismo tenant, misma capacidad en el rol, y aun así no: el acotamiento a
    // lo propio es lo que evita que un agente toque la cartera de otro.
    const a = usuario("AGENT", ORG_A, "ag-1");
    expect(can(a, "listing.edit", publicacionDe(ORG_A, "ag-2"))).toBe(false);
    expect(can(a, "listing.pause", publicacionDe(ORG_A, "ag-2"))).toBe(false);
  });

  it("no edita una publicación sin agente asignado", () => {
    expect(can(usuario("AGENT", ORG_A, "ag-1"), "listing.edit", publicacionDe(ORG_A, null))).toBe(false);
  });

  it("un agente sin ficha profesional no edita nada por asignación", () => {
    const sinFicha = usuario("AGENT", ORG_A, null);
    expect(can(sinFicha, "listing.edit", publicacionDe(ORG_A, "ag-1"))).toBe(false);
  });

  it("el acotamiento no afecta a los roles administrativos", () => {
    // Un MANAGER edita cualquier publicación de su organización, asignada o no.
    expect(can(usuario("MANAGER"), "listing.edit", publicacionDe(ORG_A, "ag-2"))).toBe(true);
  });
});

describe("deny by default", () => {
  it("una capacidad desconocida nunca se concede, ni al OWNER", () => {
    // Protege contra un typo en el sitio de llamada.
    const inventada = "listing.destroy_everything" as Capability;
    expect(can(usuario("OWNER"), inventada, ORGANIZACION_A)).toBe(false);
    expect(canConMotivo(usuario("OWNER"), inventada, ORGANIZACION_A)).toEqual({
      permitido: false,
      motivo: "capacidad desconocida",
    });
  });

  it("todo rol declara sólo capacidades que existen", () => {
    for (const rol of ROLES) {
      for (const cap of capacidadesDeRol(rol)) {
        expect(CAPABILITIES).toContain(cap);
      }
    }
  });

  it("VIEWER es el rol mínimo y no concede ninguna escritura", () => {
    const escrituras = CAPABILITIES.filter((c) => !c.endsWith(".view"));
    for (const cap of escrituras) {
      expect(capacidadesDeRol("VIEWER")).not.toContain(cap);
    }
  });
});

describe("motivos de la negativa", () => {
  it("distingue anónimo, ajeno, suspendido y rol insuficiente", () => {
    expect(canConMotivo(ANONIMO, "listing.edit", publicacionDe())).toMatchObject({ motivo: /anónimo/ });
    expect(canConMotivo(usuario("OWNER", ORG_B), "listing.edit", publicacionDe(ORG_A))).toMatchObject({
      motivo: /sin membresía/,
    });
    expect(canConMotivo(usuario("VIEWER"), "listing.edit", publicacionDe())).toMatchObject({
      motivo: /VIEWER/,
    });
    expect(
      canConMotivo(usuario("AGENT", ORG_A, "ag-1"), "listing.edit", publicacionDe(ORG_A, "ag-2")),
    ).toMatchObject({ motivo: /asignado/ });
  });

  it("coincide siempre con `can`, para que no se separen con el tiempo", () => {
    const actores = [ANONIMO, usuario("OWNER"), usuario("VIEWER"), usuario("AGENT", ORG_A, "ag-1")];
    const recursos = [ORGANIZACION_A, publicacionDe(ORG_A, "ag-1"), publicacionDe(ORG_B)];
    for (const a of actores) {
      for (const r of recursos) {
        for (const cap of CAPABILITIES) {
          expect(canConMotivo(a, cap, r).permitido).toBe(can(a, cap, r));
        }
      }
    }
  });

  it("el motivo no revela el tenant dueño del recurso", () => {
    // Sería filtrar información a quien justamente no tiene acceso.
    const v = canConMotivo(ANONIMO, "listing.edit", publicacionDe(ORG_A));
    expect(v.permitido).toBe(false);
    if (!v.permitido) expect(v.motivo).not.toContain(ORG_A);
  });
});

describe("sucursales y agentes como recursos", () => {
  it("respetan el mismo aislamiento de tenant", () => {
    const sucursalAjena: RecursoContext = {
      kind: "BRANCH",
      organizationId: ORG_B,
      branchId: branchId("b-1"),
    };
    expect(can(usuario("OWNER", ORG_A), "branch.manage", sucursalAjena)).toBe(false);
    expect(can(usuario("OWNER", ORG_B), "branch.manage", sucursalAjena)).toBe(true);
  });

  it("un MANAGER administra agentes de su organización", () => {
    const suAgente: RecursoContext = { kind: "AGENT", organizationId: ORG_A, agentId: AGENTE_1 };
    expect(can(usuario("MANAGER"), "agent.manage", suAgente)).toBe(true);
  });
});
