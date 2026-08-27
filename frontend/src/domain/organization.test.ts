import { describe, expect, it } from "vitest";
import { branchId, organizationId, userId } from "./ids";
import {
  ORGANIZATION_STATUSES,
  type Branch,
  type Organization,
  type OrganizationStatus,
  permiteAdministracion,
  problemasDeOrganizacion,
  sucursalPrincipal,
} from "./organization";

const ORG = organizationId("org-1");

function sucursal(id: string, isPrimary = false, org = ORG): Branch {
  return {
    id: branchId(id),
    organizationId: org,
    name: `Sucursal ${id}`,
    contact: { phone: null, email: null, website: null, address: null, city: null, province: null },
    isPrimary,
  };
}

function organizacion(status: OrganizationStatus, overrides: Partial<Organization> = {}): Organization {
  const ownership =
    status === "PUBLIC_PROFILE"
      ? null
      : {
          ownerUserId: userId("u-1"),
          claimedAt: "2026-08-01",
          verifiedAt: status === "VERIFIED" ? "2026-08-02" : null,
        };
  return {
    id: ORG,
    status,
    identity: {
      displayName: "Inmobiliaria López",
      slug: "inmobiliaria-lopez",
      legalName: null,
      description: null,
      logoUrl: null,
      coverUrl: null,
    },
    contact: { phone: null, email: null, website: null, address: null, city: "Rosario", province: "Santa Fe" },
    branches: [],
    ownership,
    publicVerified: null,
    ...overrides,
  };
}

describe("estados de organización", () => {
  it("un perfil público no lo administra nadie", () => {
    // Es el estado de las miles de inmobiliarias de hoy.
    expect(permiteAdministracion("PUBLIC_PROFILE")).toBe(false);
  });

  it("reclamada y verificada sí habilitan administración", () => {
    expect(permiteAdministracion("CLAIMED")).toBe(true);
    expect(permiteAdministracion("VERIFIED")).toBe(true);
  });

  it("los tres estados existen y son distintos", () => {
    expect(new Set(ORGANIZATION_STATUSES).size).toBe(3);
  });
});

describe("verificación con tres valores", () => {
  it("distingue no evaluada de evaluada y no verificada", () => {
    // null ≠ false. Colapsarlo presentaría como negativo un dato que no tenemos.
    expect(organizacion("PUBLIC_PROFILE").publicVerified).toBeNull();
    expect(organizacion("PUBLIC_PROFILE", { publicVerified: false }).publicVerified).toBe(false);
    expect(organizacion("PUBLIC_PROFILE", { publicVerified: null }).publicVerified).not.toBe(false);
  });
});

describe("coherencia", () => {
  it("acepta las tres formas válidas", () => {
    for (const s of ORGANIZATION_STATUSES) {
      expect(problemasDeOrganizacion(organizacion(s))).toEqual([]);
    }
  });

  it("rechaza una organización administrable sin dueño", () => {
    const rota = organizacion("CLAIMED", { ownership: null });
    expect(problemasDeOrganizacion(rota)[0]).toMatch(/exige un dueño/);
  });

  it("rechaza un perfil público con dueño", () => {
    const rota = organizacion("PUBLIC_PROFILE", {
      ownership: { ownerUserId: userId("u-1"), claimedAt: "2026-08-01", verifiedAt: null },
    });
    expect(problemasDeOrganizacion(rota)[0]).toMatch(/perfil público no puede tener dueño/);
  });

  it("rechaza una verificada sin fecha de verificación", () => {
    const rota = organizacion("VERIFIED", {
      ownership: { ownerUserId: userId("u-1"), claimedAt: "2026-08-01", verifiedAt: null },
    });
    expect(problemasDeOrganizacion(rota)[0]).toMatch(/fecha de verificación/);
  });

  it("rechaza dos sucursales principales", () => {
    const rota = organizacion("CLAIMED", { branches: [sucursal("b1", true), sucursal("b2", true)] });
    expect(problemasDeOrganizacion(rota)[0]).toMatch(/más de una sucursal principal/);
  });

  it("rechaza una sucursal que pertenece a otra organización", () => {
    // El error de tenancy más fácil de cometer al escribir.
    const ajena = sucursal("b9", false, organizationId("org-2"));
    const rota = organizacion("CLAIMED", { branches: [ajena] });
    expect(problemasDeOrganizacion(rota)[0]).toMatch(/pertenece a otra organización/);
  });
});

describe("sucursales", () => {
  it("encuentra la principal", () => {
    const o = organizacion("CLAIMED", { branches: [sucursal("b1"), sucursal("b2", true)] });
    expect(sucursalPrincipal(o)?.id).toBe("b2");
  });

  it("devuelve null si no se designó ninguna", () => {
    expect(sucursalPrincipal(organizacion("CLAIMED", { branches: [sucursal("b1")] }))).toBeNull();
    expect(sucursalPrincipal(organizacion("CLAIMED"))).toBeNull();
  });
});
