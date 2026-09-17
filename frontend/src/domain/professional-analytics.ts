// Taxonomía de eventos para la analítica de inmobiliarias.
//
// No instrumenta nada y no hay colector. Son los contratos y el saneador, que
// es la parte que conviene tener escrita ANTES de empezar a recolectar: una vez
// que los eventos se emiten, cambiarles la forma implica migrar lo ya guardado,
// y sacar un dato que no debía estar ahí implica borrarlo de donde haya llegado.
//
// ---------------------------------------------------------------------------
// RELACIÓN CON `lib/analytics.ts`
// ---------------------------------------------------------------------------
//
// Ese módulo existe y se conserva: es la taxonomía de INTERACCIÓN —qué hizo
// alguien en la interfaz— y hoy sólo emite un CustomEvent local.
//
// Esto es otra cosa: qué le pasó a la PUBLICACIÓN de una inmobiliaria. Los dos
// pueden originarse en el mismo click y significan cosas distintas:
// `property_opened` dice que alguien abrió una ficha; `listing_view` dice que
// una inmobiliaria recibió una visita. El primero es de producto; el segundo,
// de la organización, y va a mostrarse en su panel.
//
// ---------------------------------------------------------------------------
// LO QUE NO SE GUARDA
// ---------------------------------------------------------------------------
//
// Sin cuentas, el identificador es de sesión y anónimo: nunca un id de usuario,
// un email ni un teléfono.
//
// Y no se guarda el texto de búsqueda completo. La tentación es fuerte —"¿qué
// buscan?" es la primera pregunta de cualquier inmobiliaria— pero una búsqueda
// libre puede contener el nombre de una calle con altura, un nombre propio, o
// lo que alguien tipeó por error. Guardado y expuesto en un panel, eso es un
// dato personal de un tercero que nadie consintió. Se guarda la FORMA de la
// búsqueda —qué filtros se usaron— y no su contenido.

import type { AgentId, ListingId, OrganizationId } from "./ids";

export const PROFESSIONAL_EVENTS = [
  /** Alguien abrió la ficha de una publicación. */
  "listing_view",
  /** Apareció entre resultados de una búsqueda. */
  "search_result_impression",
  /** Alguien abrió el panel de contacto. Intención, no contacto todavía. */
  "contact_intent",
  /** Alguien usó efectivamente un canal de contacto. */
  "contact_channel_used",
  "favorite",
  "compare",
  "share",
  /** Alguien abrió el perfil de la inmobiliaria o del agente. */
  "profile_view",
  /** Un contacto que la inmobiliaria puede responder. Todavía no existe. */
  "lead_future",
] as const;
export type ProfessionalEvent = (typeof PROFESSIONAL_EVENTS)[number];

/** Desde dónde ocurrió. Permite distinguir el tráfico del buscador del directo. */
export const SURFACES = [
  "SEARCH_RESULTS",
  "MAP",
  "LISTING_DETAIL",
  "RELATED",
  "ORGANIZATION_PROFILE",
  "AGENT_PROFILE",
  "SAVED",
  "DIRECT",
] as const;
export type Surface = (typeof SURFACES)[number];

/**
 * Identidad de quien generó el evento.
 *
 * Sólo un id de sesión anónimo y efímero. No hay variante con usuario: cuando
 * existan cuentas habrá que decidir explícitamente si se atribuye, y esa
 * decisión no debe poder tomarse por omisión agregando un campo opcional.
 */
export type ContextoAnonimo = {
  sessionId: string;
  /** Primera visita de esta sesión. No identifica a la persona. */
  isNewSession: boolean;
};

/**
 * Forma de la búsqueda que originó el evento, sin su contenido.
 *
 * `filterNames` son NOMBRES de filtro, nunca sus valores. `hadFreeText` dice si
 * hubo texto libre, no cuál.
 */
export type FormaDeBusqueda = {
  filterNames: readonly string[];
  hadFreeText: boolean;
  resultCount: number | null;
};

export type EventoProfesional = {
  name: ProfessionalEvent;
  occurredAt: string;
  context: ContextoAnonimo;
  surface: Surface;
  listingId: ListingId | null;
  organizationId: OrganizationId | null;
  agentId: AgentId | null;
  search: FormaDeBusqueda | null;
};

// --- saneamiento -----------------------------------------------------------

/**
 * Claves que nunca pueden viajar en un evento.
 *
 * Lista explícita además de la validación de forma: es la que documenta la
 * intención y la que hace fallar un test si alguien agrega el campo.
 */
export const CLAVES_PROHIBIDAS = Object.freeze([
  "query",
  "q",
  "searchText",
  "email",
  "phone",
  "telefono",
  "userId",
  "name",
  "nombre",
  "ip",
  "address",
  "direccion",
  "password",
  "token",
]);

/**
 * Campos legítimos del evento.
 *
 * Existe porque `name` está a la vez en la lista de prohibidas —por el nombre
 * de una persona— y es un campo propio del evento. Sin esta distinción, todo
 * evento válido quedaría marcado. Se comprueban las claves EXTRA: las que
 * alguien agregó al objeto y no pertenecen al contrato.
 */
const CLAVES_DEL_CONTRATO: readonly string[] = Object.freeze([
  "name",
  "occurredAt",
  "context",
  "surface",
  "listingId",
  "organizationId",
  "agentId",
  "search",
]);

export type ProblemaDeEvento = { campo: string; motivo: string };

/**
 * ¿Este evento es seguro de emitir?
 *
 * Se valida en el borde, antes de emitir. Validar al recibir sería tarde: el
 * dato ya viajó.
 */
export function problemasDeEvento(e: EventoProfesional): ProblemaDeEvento[] {
  const problemas: ProblemaDeEvento[] = [];

  if (!(PROFESSIONAL_EVENTS as readonly string[]).includes(e.name)) {
    problemas.push({ campo: "name", motivo: "evento desconocido" });
  }
  if (!(SURFACES as readonly string[]).includes(e.surface)) {
    problemas.push({ campo: "surface", motivo: "superficie desconocida" });
  }
  if (!e.context?.sessionId) {
    problemas.push({ campo: "context.sessionId", motivo: "falta el identificador de sesión" });
  }

  // Un evento sobre una publicación sin publicación no le sirve a nadie.
  const exigenListing: ProfessionalEvent[] = [
    "listing_view",
    "search_result_impression",
    "contact_intent",
    "contact_channel_used",
    "favorite",
    "compare",
    "share",
  ];
  if (exigenListing.includes(e.name) && !e.listingId) {
    problemas.push({ campo: "listingId", motivo: `${e.name} necesita una publicación` });
  }

  for (const nombre of e.search?.filterNames ?? []) {
    // Un "filtro" con un igual o dos puntos adentro es un valor disfrazado de
    // nombre: `precio=250000` identifica una búsqueda concreta.
    if (/[=:]/.test(nombre)) {
      problemas.push({ campo: "search.filterNames", motivo: "parece contener valores, no nombres" });
      break;
    }
  }

  // Sólo las claves EXTRA: `name` es del contrato y también está en la lista de
  // prohibidas (por el nombre de una persona), así que comprobar todas marcaría
  // cualquier evento válido.
  for (const clave of Object.keys(e as unknown as Record<string, unknown>)) {
    if (CLAVES_DEL_CONTRATO.includes(clave)) continue;
    if (CLAVES_PROHIBIDAS.includes(clave)) {
      problemas.push({ campo: clave, motivo: "no puede viajar en un evento" });
    } else {
      // Un campo que nadie declaró es la vía por la que se cuela un dato
      // personal sin que ninguna lista lo prevea.
      problemas.push({ campo: clave, motivo: "campo no declarado en el contrato" });
    }
  }

  return problemas;
}

/**
 * Reduce un `PropertyFilters` a su forma, descartando los valores.
 *
 * Devuelve los nombres de los filtros efectivamente usados. `q` se reporta como
 * `hadFreeText` y su contenido se descarta acá, en el único lugar por donde
 * pasa: si el descarte estuviera repartido, alguna ruta lo dejaría pasar.
 */
export function formaDeBusqueda(
  filtros: Record<string, unknown>,
  resultCount: number | null = null,
): FormaDeBusqueda {
  const ignorados = new Set(["sort", "page", "cursor", "direction", "mode", "viewport", "selectedId"]);
  const filterNames: string[] = [];
  let hadFreeText = false;

  for (const [clave, valor] of Object.entries(filtros)) {
    if (ignorados.has(clave)) continue;
    const enUso = Array.isArray(valor)
      ? valor.length > 0
      : valor !== "" && valor !== null && valor !== undefined && valor !== false;
    if (!enUso) continue;
    if (clave === "q") {
      hadFreeText = true;
      continue;
    }
    filterNames.push(clave);
  }

  filterNames.sort();
  return { filterNames, hadFreeText, resultCount };
}

/**
 * ¿Qué evento profesional corresponde a una interacción de la UI?
 *
 * `null` cuando la interacción no le dice nada a una inmobiliaria: mover el
 * mapa o cambiar el orden son datos de producto, no de la organización, y
 * meterlos en su panel sería ruido.
 */
export function eventoProfesionalDe(interaccion: string): ProfessionalEvent | null {
  const mapa: Record<string, ProfessionalEvent> = {
    property_opened: "listing_view",
    contact_started: "contact_intent",
    whatsapp_clicked: "contact_channel_used",
    phone_clicked: "contact_channel_used",
    email_clicked: "contact_channel_used",
    favorite_added: "favorite",
    compare_added: "compare",
    share_clicked: "share",
    real_estate_opened: "profile_view",
  };
  return mapa[interaccion] ?? null;
}

/**
 * Intención de contacto y contacto efectivo son eventos distintos.
 *
 * Abrir el panel y apretar WhatsApp no es lo mismo, y la diferencia entre los
 * dos es exactamente la tasa de conversión que a una inmobiliaria le interesa.
 * Colapsarlos haría el dato inútil.
 */
export function esContacto(e: ProfessionalEvent): boolean {
  return e === "contact_intent" || e === "contact_channel_used";
}
