// Una INMOBILIARIA como tenant administrable.
//
// Hoy hay miles de inmobiliarias en el catálogo y ninguna es administrable: son
// filas derivadas del scraping, con nombre y algún dato de contacto. Nadie las
// controla porque nadie demostró todavía que sean suyas.
//
// Este archivo modela ese salto sin darlo: qué es una organización cuando exista
// alguien detrás. No agrega campos a la base ni cambia la presentación actual.
//
// ---------------------------------------------------------------------------
// LOS TRES ESTADOS, Y POR QUÉ EL DEL MEDIO NO ES UN TRÁMITE
// ---------------------------------------------------------------------------
//
//   PUBLIC_PROFILE  Existe porque la scrapeamos. Nadie la reclamó. Es el estado
//                   de las miles de hoy.
//   CLAIMED         Alguien dijo "es mía" y lo demostró lo suficiente para
//                   administrarla.
//   VERIFIED        Además comprobamos su identidad con evidencia fuerte.
//
// La diferencia entre CLAIMED y VERIFIED no es cosmética: CLAIMED ya otorga
// poder de edición sobre contenido público. Si el listón de CLAIMED queda bajo,
// cualquiera edita la ficha de una inmobiliaria ajena. Por eso la evidencia
// vive en el modelo de reclamación (`claim.ts`) y no como un booleano acá.
//
// Y un tercer estado importa tanto como los otros: `verified` en el perfil
// público actual puede ser `null`. No verificada y "no sabemos" son cosas
// distintas, y la UI ya lo respeta. El modelo lo conserva.

import type { BranchId, OrganizationId, UserId } from "./ids";

export const ORGANIZATION_STATUSES = ["PUBLIC_PROFILE", "CLAIMED", "VERIFIED"] as const;
export type OrganizationStatus = (typeof ORGANIZATION_STATUSES)[number];

/**
 * ¿Este estado habilita administrar la organización?
 *
 * Deny by default: sólo los dos estados reclamados. Un perfil público no lo
 * administra nadie, por definición.
 */
export function permiteAdministracion(s: OrganizationStatus): boolean {
  return s === "CLAIMED" || s === "VERIFIED";
}

/**
 * Datos de contacto. Todos opcionales porque el scraping consigue lo que
 * consigue, y un teléfono ausente es ausente, no vacío.
 */
export type OrganizationContact = {
  phone: string | null;
  email: string | null;
  website: string | null;
  address: string | null;
  city: string | null;
  province: string | null;
};

/**
 * Identidad visual. Ver `miniportal.ts` para la configuración completa: acá
 * están sólo los datos que ya existen o que la organización sube, no el diseño.
 */
export type OrganizationIdentity = {
  displayName: string;
  slug: string;
  legalName: string | null;
  description: string | null;
  logoUrl: string | null;
  coverUrl: string | null;
};

export type Branch = {
  id: BranchId;
  organizationId: OrganizationId;
  name: string;
  contact: OrganizationContact;
  isPrimary: boolean;
};

/**
 * Quién controla la organización. `null` mientras nadie la reclamó, que es el
 * caso de todas las de hoy.
 */
export type OrganizationOwnership = {
  ownerUserId: UserId;
  claimedAt: string;
  /** Verificada, y con qué método. Ver `claim.ts`. */
  verifiedAt: string | null;
};

export type Organization = {
  id: OrganizationId;
  status: OrganizationStatus;
  identity: OrganizationIdentity;
  contact: OrganizationContact;
  branches: readonly Branch[];
  ownership: OrganizationOwnership | null;
  /**
   * Verificación heredada del perfil público actual.
   *
   * Tres valores a propósito: `null` es "no evaluada", que es distinto de
   * `false` ("evaluada y no verificada"). Colapsarlo a booleano perdería esa
   * distinción y presentaría como negativo un dato que no tenemos.
   */
  publicVerified: boolean | null;
};

/**
 * ¿El modelo es coherente?
 *
 * El caso que importa: `status` y `ownership` tienen que contar la misma
 * historia. Una organización CLAIMED sin dueño, o un perfil público con dueño,
 * son estados que sólo pueden venir de un bug de escritura, y son justamente
 * los que decidirían mal un permiso.
 */
export function problemasDeOrganizacion(o: Organization): string[] {
  const problemas: string[] = [];

  if (permiteAdministracion(o.status) && o.ownership === null) {
    problemas.push(`estado ${o.status} exige un dueño y no lo tiene`);
  }
  if (o.status === "PUBLIC_PROFILE" && o.ownership !== null) {
    problemas.push("un perfil público no puede tener dueño");
  }
  if (o.status === "VERIFIED" && o.ownership?.verifiedAt == null) {
    problemas.push("una organización verificada necesita fecha de verificación");
  }
  if (o.branches.filter((b) => b.isPrimary).length > 1) {
    problemas.push("no puede haber más de una sucursal principal");
  }
  for (const b of o.branches) {
    if (b.organizationId !== o.id) {
      problemas.push(`la sucursal ${b.id} pertenece a otra organización`);
    }
  }
  return problemas;
}

/** La sucursal principal, o null si no se designó ninguna. */
export function sucursalPrincipal(o: Organization): Branch | null {
  return o.branches.find((b) => b.isPrimary) ?? null;
}
