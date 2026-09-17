// Validación de una publicación cargada a mano.
//
// ---------------------------------------------------------------------------
// ESTO NO SE ENLAZA DESDE LA NAVEGACIÓN PÚBLICA
// ---------------------------------------------------------------------------
//
// No hay persistencia de publicaciones manuales. Un formulario público sin
// dónde guardar es una persona cargando veinte campos y ocho fotos para que se
// pierdan al recargar. El módulo existe para estar listo y testeado; exponerlo
// es una decisión posterior, y depende de que exista la persistencia.
//
// El límite de publicaciones gratuitas para particulares vive acá como política
// declarada (`POLITICA_PARTICULAR`), no como número suelto en un `if`.

import type { AgentId, OrganizationId, UserId } from "./ids";

export const PUBLISHER_TYPES = ["INDIVIDUAL", "AGENT", "ORGANIZATION"] as const;
export type PublisherType = (typeof PUBLISHER_TYPES)[number];

/**
 * Política de publicaciones gratuitas para particulares.
 *
 * Declarada, no aplicada: sin cuentas no hay a quién contarle publicaciones.
 * Está acá para que el día que se aplique haya un solo lugar donde cambiarla.
 */
export const POLITICA_PARTICULAR = Object.freeze({
  FREE_INDIVIDUAL_LISTING_LIMIT: 5,
});

/**
 * El precio, como unión y no como número opcional.
 *
 * "A consultar" es una decisión comercial legítima y frecuente, y es distinta
 * de "todavía no lo cargué". Con `price: number | null` las dos se ven igual, y
 * después la ficha no puede mostrar "Consultar" sin adivinar cuál era.
 */
export type PrecioDeclarado =
  | { kind: "CONSULTAR" }
  | { kind: "MONTO"; amount: number; currency: "USD" | "ARS" };

export type BorradorDePublicacion = {
  publisherType: PublisherType;
  authorUserId: UserId;
  organizationId: OrganizationId | null;
  agentId: AgentId | null;

  operation: string | null;
  propertyType: string | null;
  precio: PrecioDeclarado | null;
  expenses: number | null;

  province: string | null;
  city: string | null;
  neighborhood: string | null;
  address: string | null;

  title: string | null;
  description: string | null;

  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  totalArea: number | null;
  coveredArea: number | null;

  images: readonly string[];
  contactPhone: string | null;
  contactEmail: string | null;

  /** Declaración de que tiene derecho a publicarla. Sin esto no se publica. */
  legitimacyAccepted: boolean;
};

export type ErrorDeValidacion = {
  field: string;
  code: string;
  message: string;
};

const OPERACIONES = ["venta", "alquiler", "temporario"];
const TIPOS = [
  "departamento", "casa", "ph", "terreno", "oficina", "local",
  "cochera", "galpon", "campo", "otro",
];

export const LARGO_MINIMO_TITULO = 10;
export const LARGO_MINIMO_DESCRIPCION = 30;
export const IMAGENES_MINIMAS = 1;

const err = (field: string, code: string, message: string): ErrorDeValidacion => ({ field, code, message });

/**
 * Valida un borrador completo.
 *
 * Devuelve TODOS los errores, no el primero: un formulario que revela un
 * problema por vez obliga a enviar seis veces, y la gente abandona.
 */
export function validarBorrador(b: BorradorDePublicacion): ErrorDeValidacion[] {
  const e: ErrorDeValidacion[] = [];

  if (!b.operation) e.push(err("operation", "REQUERIDO", "Elegí si es venta, alquiler o temporario"));
  else if (!OPERACIONES.includes(b.operation)) {
    e.push(err("operation", "INVALIDO", "Operación no reconocida"));
  }

  if (!b.propertyType) e.push(err("propertyType", "REQUERIDO", "Elegí el tipo de propiedad"));
  else if (!TIPOS.includes(b.propertyType)) {
    e.push(err("propertyType", "INVALIDO", "Tipo de propiedad no reconocido"));
  }

  // El precio tiene que ser una decisión explícita: un monto o "a consultar".
  if (b.precio === null) {
    e.push(err("precio", "REQUERIDO", "Indicá un precio o marcá 'a consultar'"));
  } else if (b.precio.kind === "MONTO") {
    if (!Number.isFinite(b.precio.amount) || b.precio.amount <= 0) {
      e.push(err("precio", "INVALIDO", "El precio tiene que ser mayor que cero"));
    }
  }

  if (!b.province?.trim()) e.push(err("province", "REQUERIDO", "Indicá la provincia"));
  if (!b.city?.trim()) e.push(err("city", "REQUERIDO", "Indicá la ciudad"));

  const titulo = b.title?.trim() ?? "";
  if (!titulo) e.push(err("title", "REQUERIDO", "Poné un título"));
  else if (titulo.length < LARGO_MINIMO_TITULO) {
    e.push(err("title", "MUY_CORTO", `El título necesita al menos ${LARGO_MINIMO_TITULO} caracteres`));
  }

  const desc = b.description?.trim() ?? "";
  if (!desc) e.push(err("description", "REQUERIDO", "Escribí una descripción"));
  else if (desc.length < LARGO_MINIMO_DESCRIPCION) {
    e.push(
      err("description", "MUY_CORTA", `La descripción necesita al menos ${LARGO_MINIMO_DESCRIPCION} caracteres`),
    );
  }

  if (b.images.length < IMAGENES_MINIMAS) {
    e.push(err("images", "REQUERIDO", "Subí al menos una foto"));
  }

  // Al menos una vía de contacto: una publicación que nadie puede contactar no
  // le sirve a nadie.
  if (!b.contactPhone?.trim() && !b.contactEmail?.trim()) {
    e.push(err("contactPhone", "REQUERIDO", "Dejá un teléfono o un email de contacto"));
  }

  if (!b.legitimacyAccepted) {
    e.push(err("legitimacyAccepted", "REQUERIDO", "Confirmá que estás autorizado a publicarla"));
  }

  e.push(...validarCoherenciaFisica(b));
  e.push(...validarAtribucion(b));
  return e;
}

/**
 * Incoherencias físicas, con el mismo criterio que `data-quality`: sólo las
 * contradicciones aritméticas se rechazan. Lo raro no se bloquea acá, porque
 * bloquear una carga legítima por rara es peor que revisarla después.
 */
function validarCoherenciaFisica(b: BorradorDePublicacion): ErrorDeValidacion[] {
  const e: ErrorDeValidacion[] = [];
  const pos = (n: number | null): n is number => n !== null && Number.isFinite(n) && n > 0;

  if (pos(b.coveredArea) && pos(b.totalArea) && b.coveredArea > b.totalArea) {
    e.push(err("coveredArea", "INCOHERENTE", "La superficie cubierta no puede superar la total"));
  }
  if (pos(b.bedrooms) && pos(b.rooms) && b.bedrooms > b.rooms) {
    e.push(err("bedrooms", "INCOHERENTE", "No puede haber más dormitorios que ambientes"));
  }
  for (const [campo, valor] of [
    ["rooms", b.rooms], ["bedrooms", b.bedrooms], ["bathrooms", b.bathrooms],
    ["totalArea", b.totalArea], ["coveredArea", b.coveredArea], ["expenses", b.expenses],
  ] as const) {
    if (valor !== null && Number.isFinite(valor) && valor < 0) {
      e.push(err(campo, "INVALIDO", "No puede ser un número negativo"));
    }
  }
  return e;
}

/**
 * La atribución tiene que cerrar con el tipo de publicador.
 *
 * Es lo que impide que alguien publique "en nombre de" una organización a la
 * que no pertenece: acá se comprueba la forma; que además TENGA permiso sobre
 * esa organización lo decide `permissions.can`, y las dos cosas se aplican.
 */
function validarAtribucion(b: BorradorDePublicacion): ErrorDeValidacion[] {
  const e: ErrorDeValidacion[] = [];

  if (b.publisherType === "ORGANIZATION" && !b.organizationId) {
    e.push(err("organizationId", "REQUERIDO", "Falta la organización que publica"));
  }
  if (b.publisherType === "INDIVIDUAL" && b.organizationId) {
    e.push(err("organizationId", "INVALIDO", "Un particular no publica en nombre de una organización"));
  }
  if (b.publisherType === "AGENT" && !b.agentId) {
    e.push(err("agentId", "REQUERIDO", "Falta el agente que publica"));
  }
  return e;
}

export function esBorradorValido(b: BorradorDePublicacion): boolean {
  return validarBorrador(b).length === 0;
}

/**
 * ¿Puede este particular publicar una más?
 *
 * Función pura: recibe cuántas tiene. No consulta nada, porque no hay nada que
 * consultar todavía.
 */
export function puedePublicarGratis(publicacionesActivas: number): boolean {
  return publicacionesActivas < POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT;
}
