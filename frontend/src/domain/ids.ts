// Identificadores del dominio, tipados por marca (branded types).
//
// Por qué no alcanza con `string`: en un sistema multi-tenant el accidente más
// caro no es un tipo mal escrito, es pasar un id donde iba otro. Un
// `organizationId` y un `listingId` son ambos `string`, así que el compilador
// deja pasar `getListing(organizationId)` sin una palabra. Con marcas, eso es
// un error de compilación.
//
// La marca existe sólo en tipos: en runtime siguen siendo strings, sin costo
// ni envoltorio. Lo único que hay que respetar es que la ÚNICA forma de crear
// un id marcado sea a través de estos constructores, que validan.

/** Marca de tipo. El campo nunca existe en runtime. */
declare const marca: unique symbol;
type Marcado<T extends string> = string & { readonly [marca]: T };

// --- entidades del dominio -------------------------------------------------

/** Una propiedad física del mundo real. Puede tener varias publicaciones. */
export type PropertyEntityId = Marcado<"PropertyEntity">;

/** Una publicación concreta de una propiedad, con un origen. */
export type ListingId = Marcado<"Listing">;

/** Una inmobiliaria como tenant administrable. */
export type OrganizationId = Marcado<"Organization">;

/** Una sucursal dentro de una organización. */
export type BranchId = Marcado<"Branch">;

/** Una persona que usa la plataforma. */
export type UserId = Marcado<"User">;

/** Un profesional inmobiliario, exista o no como usuario. */
export type AgentId = Marcado<"Agent">;

/** La pertenencia de un usuario a una organización. */
export type MembershipId = Marcado<"Membership">;

/** Una solicitud de reclamación de organización o publicación. */
export type ClaimId = Marcado<"Claim">;

/** Un reporte o solicitud de corrección enviado por alguien. */
export type ReportId = Marcado<"Report">;

/** Un caso de moderación abierto sobre una publicación. */
export type ModerationCaseId = Marcado<"ModerationCase">;

/** Una entrada del registro de auditoría. */
export type AuditEventId = Marcado<"AuditEvent">;

/** Una colección de propiedades guardada por una persona. */
export type CollectionId = Marcado<"Collection">;

/** Una búsqueda guardada, base de las alertas futuras. */
export type SavedSearchId = Marcado<"SavedSearch">;

export type AnyId =
  | PropertyEntityId
  | ListingId
  | OrganizationId
  | BranchId
  | UserId
  | AgentId
  | MembershipId
  | ClaimId
  | ReportId
  | ModerationCaseId
  | AuditEventId
  | CollectionId
  | SavedSearchId;

// --- construcción y validación ---------------------------------------------

/**
 * Qué se acepta como identificador.
 *
 * Deliberadamente permisivo en forma —hay ids numéricos heredados de la base
 * (`propiedades.id`), slugs, y habrá UUID— pero estricto en lo que importa:
 * no vacío, sin espacios, y acotado. Un id con espacios o de 5.000 caracteres
 * viene de un bug o de un intento de inyección, nunca de un dato legítimo.
 */
const FORMA_VALIDA = /^[A-Za-z0-9_.:-]{1,128}$/;

export function esIdValido(valor: unknown): valor is string {
  return typeof valor === "string" && FORMA_VALIDA.test(valor);
}

/**
 * Convierte un valor externo en un id marcado, o falla.
 *
 * Se usa en el borde del sistema: lo que llega de la base, de la URL o de un
 * formulario. Adentro del dominio los ids ya vienen marcados y no se revalida.
 *
 * Acepta `number` porque la base tiene ids numéricos y convertirlos en el
 * borde es más simple que arrastrar `string | number` por todo el dominio.
 */
export function comoId<T extends AnyId>(valor: unknown, queEs: string): T {
  const texto = typeof valor === "number" && Number.isFinite(valor) ? String(valor) : valor;
  if (!esIdValido(texto)) {
    // No se incluye el valor recibido en el mensaje: puede venir de una URL
    // pública y terminar en un log.
    throw new TypeError(`Identificador de ${queEs} inválido`);
  }
  return texto as T;
}

/** Variante que devuelve null en vez de fallar, para campos opcionales. */
export function comoIdOpcional<T extends AnyId>(valor: unknown): T | null {
  if (valor === null || valor === undefined || valor === "") return null;
  const texto = typeof valor === "number" && Number.isFinite(valor) ? String(valor) : valor;
  return esIdValido(texto) ? (texto as T) : null;
}

// Constructores concretos. Existen para que el sitio de llamada se lea solo y
// para que el mensaje de error diga qué se esperaba.
export const propertyEntityId = (v: unknown) => comoId<PropertyEntityId>(v, "propiedad");
export const listingId = (v: unknown) => comoId<ListingId>(v, "publicación");
export const organizationId = (v: unknown) => comoId<OrganizationId>(v, "organización");
export const branchId = (v: unknown) => comoId<BranchId>(v, "sucursal");
export const userId = (v: unknown) => comoId<UserId>(v, "usuario");
export const agentId = (v: unknown) => comoId<AgentId>(v, "agente");
export const membershipId = (v: unknown) => comoId<MembershipId>(v, "membresía");
export const claimId = (v: unknown) => comoId<ClaimId>(v, "reclamación");
export const reportId = (v: unknown) => comoId<ReportId>(v, "reporte");
export const moderationCaseId = (v: unknown) => comoId<ModerationCaseId>(v, "caso de moderación");
export const auditEventId = (v: unknown) => comoId<AuditEventId>(v, "evento de auditoría");
export const collectionId = (v: unknown) => comoId<CollectionId>(v, "colección");
export const savedSearchId = (v: unknown) => comoId<SavedSearchId>(v, "búsqueda guardada");
