import { describe, expect, it } from "vitest";
import { agentId, branchId, organizationId, userId } from "./ids";
import {
  AGENT_IDENTITY_STATUSES,
  type Agent,
  type AgentIdentityStatus,
  esIdentidadInferida,
  pareceEtiquetaFuncional,
  permitePerfilPublico,
  problemasDeAgente,
} from "./agent";

function agente(status: AgentIdentityStatus, overrides: Partial<Agent> = {}): Agent {
  const reclamado = status === "CLAIMED" || status === "VERIFIED";
  return {
    id: agentId("ag-1"),
    identityStatus: status,
    displayName: "Juan Pérez",
    contact: { phone: null, email: null },
    photoUrl: null,
    license:
      status === "VERIFIED"
        ? { number: "1234", jurisdiction: "Santa Fe", verifiedAt: "2026-08-01" }
        : null,
    organizationId: organizationId("org-1"),
    branchId: null,
    userId: reclamado ? userId("u-1") : null,
    zones: [],
    ...overrides,
  };
}

describe("identidad inferida vs reclamada", () => {
  it("lo extraído y lo emparejado son inferencias nuestras", () => {
    expect(esIdentidadInferida("EXTRACTED")).toBe(true);
    expect(esIdentidadInferida("MATCHED")).toBe(true);
    expect(esIdentidadInferida("CLAIMED")).toBe(false);
    expect(esIdentidadInferida("VERIFIED")).toBe(false);
  });

  it("no se publica un perfil de alguien que no lo pidió", () => {
    // Un nombre scrapeado no autoriza a construir y publicar un perfil suyo.
    expect(permitePerfilPublico("EXTRACTED")).toBe(false);
    expect(permitePerfilPublico("MATCHED")).toBe(false);
    expect(permitePerfilPublico("CLAIMED")).toBe(true);
    expect(permitePerfilPublico("VERIFIED")).toBe(true);
  });

  it("inferida y publicable son exactamente complementarias", () => {
    for (const s of AGENT_IDENTITY_STATUSES) {
      expect(permitePerfilPublico(s)).toBe(!esIdentidadInferida(s));
    }
  });
});

describe("etiquetas que no son personas", () => {
  it("detecta casillas funcionales", () => {
    for (const t of ["Ventas", "contacto", "INFORMES", "Administración", "Alquileres"]) {
      expect(pareceEtiquetaFuncional(t)).toBe(true);
    }
  });

  it("detecta la etiqueta acompañada", () => {
    expect(pareceEtiquetaFuncional("Ventas Rosario")).toBe(true);
    expect(pareceEtiquetaFuncional("Departamento ventas")).toBe(true);
  });

  it("ignora acentos, porque las fuentes escriben de las dos formas", () => {
    expect(pareceEtiquetaFuncional("Atencion")).toBe(true);
    expect(pareceEtiquetaFuncional("Atención")).toBe(true);
  });

  it("no marca nombres de personas", () => {
    for (const t of ["Juan Pérez", "María López", "Ana"]) {
      expect(pareceEtiquetaFuncional(t)).toBe(false);
    }
  });

  it("es conservador: ante la duda no marca", () => {
    // Marcar de más excluiría a personas reales del emparejamiento.
    expect(pareceEtiquetaFuncional("Ventura Gómez")).toBe(false);
    expect(pareceEtiquetaFuncional(null)).toBe(false);
    expect(pareceEtiquetaFuncional("")).toBe(false);
  });
});

describe("coherencia", () => {
  it("acepta las cuatro formas válidas", () => {
    for (const s of AGENT_IDENTITY_STATUSES) {
      expect(problemasDeAgente(agente(s))).toEqual([]);
    }
  });

  it("rechaza un perfil reclamado sin cuenta", () => {
    expect(problemasDeAgente(agente("CLAIMED", { userId: null }))[0]).toMatch(/exige una cuenta/);
  });

  it("rechaza una identidad inferida con cuenta asociada", () => {
    expect(problemasDeAgente(agente("EXTRACTED", { userId: userId("u-1") }))[0]).toMatch(
      /identidad inferida no puede tener cuenta/,
    );
  });

  it("rechaza un verificado sin matrícula verificada", () => {
    expect(problemasDeAgente(agente("VERIFIED", { license: null }))[0]).toMatch(/matrícula verificada/);
  });

  it("rechaza sucursal sin organización", () => {
    const roto = agente("CLAIMED", { organizationId: null, branchId: branchId("b-1") });
    expect(problemasDeAgente(roto).some((p) => /sucursal sin organización/.test(p))).toBe(true);
  });

  it("no deja que se deduzcan las zonas de trabajo", () => {
    // Deducirlas de dónde publica las convertiría en una afirmación suya que
    // nunca hizo.
    const roto = agente("EXTRACTED", { zones: ["Centro", "Fisherton"] });
    expect(problemasDeAgente(roto).some((p) => /zonas sólo puede declararlas/.test(p))).toBe(true);
    expect(problemasDeAgente(agente("CLAIMED", { zones: ["Centro"] }))).toEqual([]);
  });
});
