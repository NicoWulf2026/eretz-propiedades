// Búsquedas guardadas y alertas.
//
// No envía nada. No hay cron, ni email, ni proveedor. Son los contratos y el
// emparejador puro, que es la parte que se puede construir y verificar hoy.
//
// ---------------------------------------------------------------------------
// NO SE DUPLICA LA SEMÁNTICA DE LOS FILTROS
// ---------------------------------------------------------------------------
//
// Una búsqueda guardada ES un `PropertyFilters`, el mismo tipo que ya usa el
// buscador y que `parsePropertyFilters` produce desde la URL. No se inventa un
// formato paralelo: dos definiciones de "qué es una búsqueda" se contradicen en
// cuanto alguien agregue un filtro a una sola de las dos.
//
// ---------------------------------------------------------------------------
// EL PROBLEMA DE EVALUAR EN JAVASCRIPT LO QUE SE APLICA EN SQL
// ---------------------------------------------------------------------------
//
// Los filtros hoy se aplican en la base (`property-sql.ts`). Reimplementarlos
// acá crea dos implementaciones de la misma regla que van a divergir, y la
// divergencia en una alerta es silenciosa: la persona simplemente no recibe
// avisos que esperaba, o recibe los que no.
//
// Por eso este módulo NO finge poder evaluar todo. Declara explícitamente qué
// filtros sabe evaluar y cuáles necesitan al servidor. Una búsqueda que use uno
// de los no soportados devuelve `INDETERMINADO`, nunca `false`: decir "no
// coincide" cuando no se sabe es lo que produce alertas que nunca llegan.
//
// El caso claro es `q`, la búsqueda de texto: la base normaliza acentos, parte
// términos y busca en varias columnas. Cualquier aproximación en JavaScript
// acierta el 90% de las veces, y ese 10% es imposible de detectar desde afuera.

import type { PropertyFilters } from "@/types/property";
import type { ListingId, OrganizationId, SavedSearchId, UserId } from "./ids";

// --- qué se puede evaluar acá ----------------------------------------------

/**
 * Filtros que este módulo sabe evaluar sin la base.
 *
 * Todos son comparaciones directas sobre un valor de la propiedad. Nada que
 * dependa de normalización de texto, geometría o del conjunto completo.
 */
export const FILTROS_EVALUABLES = [
  "operation",
  "propertyType",
  "province",
  "city",
  "neighborhood",
  "minPrice",
  "maxPrice",
  "currency",
  "minRooms",
  "minBedrooms",
  "minBathrooms",
  "minGarages",
  "minArea",
  "maxArea",
  "minCoveredArea",
  "minLandArea",
  "maxExpenses",
  "maxAge",
  "hasImages",
  "priceMode",
  "hasLocation",
  "hasVideo",
  "hasFloorPlan",
  "mortgageState",
] as const;
export type FiltroEvaluable = (typeof FILTROS_EVALUABLES)[number];

/**
 * Filtros que necesitan al servidor, con el motivo.
 *
 * Están enumerados y no sólo omitidos para que agregar un filtro nuevo obligue
 * a decidir en cuál de las dos listas va, en vez de que caiga en un limbo.
 */
export const FILTROS_NO_EVALUABLES: Readonly<Record<string, string>> = Object.freeze({
  q: "la búsqueda de texto se normaliza en la base y no es reproducible acá",
  locations: "combina varios niveles geográficos con la normalización de la base",
  zones: "requiere geometría sobre el conjunto",
  near: "ordena por distancia sobre el conjunto, no evalúa una propiedad sola",
  publisher: "depende de la resolución de identidad del publicador",
  recentDays: "depende de la fecha de corrida, no de la propiedad",
});

/** Campos de presentación: no participan del emparejamiento. */
const IGNORADOS = new Set(["sort", "page", "cursor", "direction", "mode", "viewport", "selectedId"]);

/** Qué filtros de esta búsqueda no se pueden evaluar sin la base. */
export function filtrosNoEvaluables(f: Partial<PropertyFilters>): string[] {
  const problemas: string[] = [];
  for (const [clave, valor] of Object.entries(f)) {
    if (IGNORADOS.has(clave)) continue;
    if (!(clave in FILTROS_NO_EVALUABLES)) continue;
    // Sólo cuenta si está efectivamente en uso: un `q: ""` no filtra nada.
    const enUso = Array.isArray(valor) ? valor.length > 0 : valor !== "" && valor !== null && valor !== undefined;
    if (enUso) problemas.push(clave);
  }
  return problemas;
}

// --- contratos -------------------------------------------------------------

export type SavedSearch = {
  id: SavedSearchId;
  ownerUserId: UserId;
  /** Nombre que le puso la persona. */
  name: string;
  filters: PropertyFilters;
  createdAt: string;
};

export const ALERT_EVENT_TYPES = [
  "NEW_LISTING",
  "PRICE_CHANGED",
  "STATUS_CHANGED",
  "SIMILAR_LISTING",
] as const;
export type AlertEventType = (typeof ALERT_EVENT_TYPES)[number];

export const ALERT_FREQUENCIES = ["INSTANT", "DAILY", "WEEKLY"] as const;
export type AlertFrequency = (typeof ALERT_FREQUENCIES)[number];

export const DELIVERY_CHANNELS = ["EMAIL", "PUSH", "IN_APP"] as const;
export type DeliveryChannel = (typeof DELIVERY_CHANNELS)[number];

export type AlertRule = {
  savedSearchId: SavedSearchId;
  types: readonly AlertEventType[];
  frequency: AlertFrequency;
  /** Una alerta apagada se conserva; borrarla perdería la búsqueda. */
  enabled: boolean;
};

export type AlertDeliveryPreference = {
  userId: UserId;
  channels: readonly DeliveryChannel[];
  /** Horas locales en las que no se molesta. `null` = sin restricción. */
  quietHours: { from: number; to: number } | null;
};

export type AlertEvent = {
  type: AlertEventType;
  savedSearchId: SavedSearchId;
  listingId: ListingId;
  organizationId: OrganizationId | null;
  occurredAt: string;
  /** Qué cambió, cuando aplica. */
  detail: { anterior: string | number | null; nuevo: string | number | null } | null;
};

// --- emparejamiento --------------------------------------------------------

/** Lo que hace falta saber de una propiedad para evaluarla. */
export type PropiedadParaEmparejar = {
  operation: string | null;
  propertyType: string | null;
  province: string | null;
  city: string | null;
  neighborhood: string | null;
  price: number | null;
  currency: string | null;
  expenses: number | null;
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  garages: number | null;
  totalArea: number | null;
  coveredArea: number | null;
  landArea: number | null;
  age: number | null;
  hasImages: boolean;
  hasCoordinates: boolean;
  hasVideo: boolean;
  hasFloorPlan: boolean;
  mortgageEligible: boolean | null;
};

export type ResultadoDeEmparejamiento =
  | { resultado: "COINCIDE" }
  | { resultado: "NO_COINCIDE"; motivo: string }
  | { resultado: "INDETERMINADO"; motivo: string; filtros: string[] };

const clave = (v: string | null): string =>
  (v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

/**
 * ¿Esta propiedad satisface la búsqueda guardada?
 *
 * Devuelve tres resultados, no dos. `INDETERMINADO` aparece cuando la búsqueda
 * usa un filtro que necesita al servidor: en ese caso hay que evaluarla allá,
 * no descartarla.
 */
export function coincideConBusqueda(
  f: Partial<PropertyFilters>,
  p: PropiedadParaEmparejar,
): ResultadoDeEmparejamiento {
  const noEvaluables = filtrosNoEvaluables(f);
  if (noEvaluables.length) {
    return {
      resultado: "INDETERMINADO",
      motivo: "la búsqueda usa filtros que sólo la base puede evaluar",
      filtros: noEvaluables,
    };
  }

  const no = (motivo: string): ResultadoDeEmparejamiento => ({ resultado: "NO_COINCIDE", motivo });

  if (f.operation && clave(f.operation) !== clave(p.operation)) return no("otra operación");
  if (f.propertyType && clave(f.propertyType) !== clave(p.propertyType)) return no("otro tipo de propiedad");
  if (f.province && clave(f.province) !== clave(p.province)) return no("otra provincia");
  if (f.city && clave(f.city) !== clave(p.city)) return no("otra ciudad");
  if (f.neighborhood && clave(f.neighborhood) !== clave(p.neighborhood)) return no("otro barrio");

  // Moneda antes que precio: comparar montos de monedas distintas no significa
  // nada, y sin este orden un filtro de 100.000 USD dejaría pasar 100.000 ARS.
  if (f.currency && clave(f.currency) !== clave(p.currency)) return no("otra moneda");

  if (f.priceMode === "with" && !(p.price !== null && p.price > 0)) return no("no tiene precio publicado");
  if (f.priceMode === "consult" && p.price !== null && p.price > 0) return no("tiene precio publicado");

  if (f.minPrice != null || f.maxPrice != null) {
    // Sin precio no se puede afirmar que esté fuera de rango, pero un filtro de
    // precio expresa querer un precio: se descarta.
    if (p.price === null) return no("sin precio, no entra en un filtro de precio");
    if (f.minPrice != null && p.price < f.minPrice) return no("por debajo del precio mínimo");
    if (f.maxPrice != null && p.price > f.maxPrice) return no("por encima del precio máximo");
  }

  const minimos: Array<[number | null | undefined, number | null, string]> = [
    [f.minRooms, p.rooms, "ambientes"],
    [f.minBedrooms, p.bedrooms, "dormitorios"],
    [f.minBathrooms, p.bathrooms, "baños"],
    [f.minGarages, p.garages, "cocheras"],
    [f.minArea, p.totalArea, "superficie"],
    [f.minCoveredArea, p.coveredArea, "superficie cubierta"],
    [f.minLandArea, p.landArea, "superficie de terreno"],
  ];
  for (const [minimo, valor, nombre] of minimos) {
    if (minimo == null) continue;
    if (valor === null) return no(`sin dato de ${nombre}`);
    if (valor < minimo) return no(`menos ${nombre} de los pedidos`);
  }

  const maximos: Array<[number | null | undefined, number | null, string]> = [
    [f.maxArea, p.totalArea, "superficie"],
    [f.maxExpenses, p.expenses, "expensas"],
    [f.maxAge, p.age, "antigüedad"],
  ];
  for (const [maximo, valor, nombre] of maximos) {
    if (maximo == null) continue;
    if (valor === null) return no(`sin dato de ${nombre}`);
    if (valor > maximo) return no(`${nombre} por encima del máximo`);
  }

  if (f.hasImages && !p.hasImages) return no("sin fotos");
  if (f.hasLocation && !p.hasCoordinates) return no("sin ubicación en el mapa");
  if (f.hasVideo && !p.hasVideo) return no("sin video");
  if (f.hasFloorPlan && !p.hasFloorPlan) return no("sin plano");

  // Ternario NULL-safe, con la misma semántica que el filtro existente:
  // "sininfo" busca justamente el dato ausente, y null nunca es "no".
  if (f.mortgageState === "si" && p.mortgageEligible !== true) return no("no es apto crédito");
  if (f.mortgageState === "no" && p.mortgageEligible !== false) return no("no consta como no apto crédito");
  if (f.mortgageState === "sininfo" && p.mortgageEligible !== null) return no("tiene dato de apto crédito");

  return { resultado: "COINCIDE" };
}

/**
 * ¿Se puede evaluar esta búsqueda sin la base?
 *
 * Sirve para decidir, al guardar una alerta, si va a poder resolverse del lado
 * del cliente o va a necesitar al servidor.
 */
export function esEvaluableLocalmente(f: Partial<PropertyFilters>): boolean {
  return filtrosNoEvaluables(f).length === 0;
}

/** Tipos de evento que una regla habilitada realmente dispara. */
export function eventosActivos(r: AlertRule): readonly AlertEventType[] {
  return r.enabled ? r.types : [];
}

/**
 * ¿Se puede notificar a esta hora?
 *
 * El rango puede cruzar la medianoche (de 22 a 8), y por eso no alcanza con
 * comparar mayor y menor.
 */
export function enHorarioSilencioso(pref: AlertDeliveryPreference, hora: number): boolean {
  if (!pref.quietHours) return false;
  const { from, to } = pref.quietHours;
  if (from === to) return false;
  return from < to ? hora >= from && hora < to : hora >= from || hora < to;
}
