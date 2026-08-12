import { operationLabels, propertyLocation, propertyPrice, typeLabels } from "@/lib/property-presenter";
import type { Property } from "@/types/property";

export function propertyShareMessage(property: Property, url: string) {
  const facts = [
    `${typeLabels[property.propertyType]} en ${operationLabels[property.operation].toLowerCase()}`,
    propertyPrice(property),
    property.rooms ? `${property.rooms} ambiente${property.rooms === 1 ? "" : "s"}` : null,
    property.bedrooms ? `${property.bedrooms} dormitorio${property.bedrooms === 1 ? "" : "s"}` : null,
    property.totalArea ? `${Intl.NumberFormat("es-AR").format(property.totalArea)} m²` : null,
    propertyLocation(property),
    property.publisher?.name ? `Publica ${property.publisher.name}` : null,
  ].filter(Boolean);
  return `${facts.join(" · ")} — ${url}`;
}

export function contactMessage(property: Property, url: string) {
  return `Hola, consulto por esta propiedad que vi en ERETZ: ${propertyShareMessage(property, url)}`;
}

// Compositor de intención: el usuario elige temas y se arma un mensaje útil
// SÓLO con lo seleccionado (nunca inventa temas). Ver secciones 49–51 del brief.
export const CONTACT_TOPICS = [
  { id: "disponibilidad", phrase: "disponibilidad" },
  { id: "expensas", phrase: "expensas" },
  { id: "requisitos", phrase: "requisitos" },
  { id: "mascotas", phrase: "si aceptan mascotas" },
  { id: "visita", phrase: "coordinar una visita" },
  { id: "ingreso", phrase: "fecha de ingreso" },
] as const;
export type ContactTopicId = (typeof CONTACT_TOPICS)[number]["id"];

const TOPIC_LABELS: Record<ContactTopicId, string> = {
  disponibilidad: "Disponibilidad",
  expensas: "Expensas",
  requisitos: "Requisitos",
  mascotas: "Mascotas",
  visita: "Coordinar visita",
  ingreso: "Fecha de ingreso",
};
export const contactTopicLabel = (id: ContactTopicId): string => TOPIC_LABELS[id];

function joinNatural(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

export function contactMessageWithTopics(
  property: Property,
  url: string,
  topicIds: ContactTopicId[],
  freeText = "",
): string {
  const phrases = CONTACT_TOPICS.filter((t) => topicIds.includes(t.id)).map((t) => t.phrase);
  let msg = `Hola, consulto por la propiedad ID ERETZ ${property.id}`;
  if (phrases.length) msg += `. Quisiera consultar ${joinNatural(phrases)}`;
  const extra = freeText.trim().slice(0, 400);
  if (extra) msg += `. ${extra}`;
  return `${msg}. ${url}`;
}

